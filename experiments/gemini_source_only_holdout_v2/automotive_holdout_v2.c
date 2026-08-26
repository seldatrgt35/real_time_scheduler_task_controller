#include "automotive_holdout_v2.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;

#define STAR_NOINLINE __attribute__((noinline))
#define CONTACTOR_COUNT       (6U)
#define WHEEL_COUNT           (4U)
#define WHEEL_HISTORY_COUNT   (5U)
#define DTC_EVENT_COUNT       (12U)

static uint16_t s_pack_voltage[CONTACTOR_COUNT];
static uint16_t s_bus_voltage[CONTACTOR_COUNT];
static uint16_t s_coil_current[CONTACTOR_COUNT];
static uint8_t s_contactor_command[CONTACTOR_COUNT];
static uint8_t s_contactor_state[CONTACTOR_COUNT];
static uint16_t s_wheel_period[WHEEL_COUNT][WHEEL_HISTORY_COUNT];
static uint16_t s_wheel_pulse_count[WHEEL_COUNT];
static uint8_t s_dtc_active[DTC_EVENT_COUNT];
static uint8_t s_dtc_confirm_counter[DTC_EVENT_COUNT];
static uint8_t s_dtc_heal_counter[DTC_EVENT_COUNT];
static uint8_t s_dtc_status[DTC_EVENT_COUNT];
static volatile uint32_t s_holdout_sink;

static STAR_NOINLINE uint32_t AbsoluteDifferenceU16(uint16_t left, uint16_t right)
{
    return (left >= right) ? ((uint32_t)left - right) : ((uint32_t)right - left);
}

static STAR_NOINLINE uint32_t EvaluateVoltageAgreement(
    uint16_t pack_voltage, uint16_t bus_voltage)
{
    const uint32_t difference = AbsoluteDifferenceU16(pack_voltage, bus_voltage);
    return (difference <= 85U) ? 1U : 0U;
}

static STAR_NOINLINE uint32_t EvaluateCoilCurrent(uint16_t current)
{
    uint32_t result;
    if (current < 90U)
    {
        result = 1U;
    }
    else if (current > 680U)
    {
        result = 2U;
    }
    else
    {
        result = 0U;
    }
    return result;
}

static STAR_NOINLINE uint32_t NextContactorState(
    uint32_t state, uint32_t command, uint32_t voltage_agrees,
    uint32_t current_fault)
{
    uint32_t next = state;
    switch (state)
    {
        case 0U:
            if ((command != 0U) && (current_fault == 0U))
            {
                next = 1U;
            }
            break;
        case 1U:
            if ((voltage_agrees != 0U) && (current_fault == 0U))
            {
                next = 2U;
            }
            else if (current_fault != 0U)
            {
                next = 3U;
            }
            break;
        case 2U:
            if ((command == 0U) || (current_fault != 0U))
            {
                next = (current_fault != 0U) ? 3U : 0U;
            }
            break;
        default:
            if (command == 0U)
            {
                next = 0U;
            }
            break;
    }
    return next;
}

static STAR_NOINLINE uint32_t MixContactorDiagnostic(
    uint32_t diagnostic, uint32_t state, uint32_t channel)
{
    uint32_t result = diagnostic ^ (state << (channel + 1U));
    result = (result << 3U) | (result >> 29U);
    return result + (channel * 17U);
}

static STAR_NOINLINE uint32_t MedianOfFiveU16(
    uint16_t first, uint16_t second, uint16_t third,
    uint16_t fourth, uint16_t fifth)
{
    uint16_t values[WHEEL_HISTORY_COUNT];
    uint32_t outer;
    values[0] = first;
    values[1] = second;
    values[2] = third;
    values[3] = fourth;
    values[4] = fifth;
    for (outer = 1U; outer < WHEEL_HISTORY_COUNT; ++outer)
    {
        uint32_t inner = outer;
        const uint16_t selected = values[outer];
        while ((inner > 0U) && (values[inner - 1U] > selected))
        {
            values[inner] = values[inner - 1U];
            --inner;
        }
        values[inner] = selected;
    }
    return values[2];
}

static STAR_NOINLINE uint32_t PeriodToSpeedQ8(uint32_t period, uint32_t pulses)
{
    uint32_t speed = 0U;
    if ((period != 0U) && (pulses != 0U))
    {
        speed = (pulses * 48000U) / period;
    }
    return speed << 8U;
}

static STAR_NOINLINE uint32_t EvaluateWheelSlip(
    uint32_t wheel_speed_q8, uint32_t vehicle_speed_q8)
{
    uint32_t slip = 0U;
    if (vehicle_speed_q8 > 256U)
    {
        const uint32_t difference = (wheel_speed_q8 >= vehicle_speed_q8)
            ? (wheel_speed_q8 - vehicle_speed_q8)
            : (vehicle_speed_q8 - wheel_speed_q8);
        slip = (difference * 100U) / vehicle_speed_q8;
    }
    return slip;
}

static STAR_NOINLINE uint32_t SaturatingIncrementU8(uint32_t value)
{
    return (value < 255U) ? (value + 1U) : 255U;
}

static STAR_NOINLINE uint32_t UpdateDtcStatus(
    uint32_t old_status, uint32_t active,
    uint32_t confirm_count, uint32_t heal_count)
{
    uint32_t status = old_status;
    if (active != 0U)
    {
        status |= 0x01U;
        status &= ~0x04U;
        if (confirm_count >= 3U)
        {
            status |= 0x02U;
        }
    }
    else
    {
        status &= ~0x01U;
        if (heal_count >= 5U)
        {
            status &= ~0x02U;
            status |= 0x04U;
        }
    }
    return status;
}

static STAR_NOINLINE uint32_t UpdateDtcChecksum(
    uint32_t checksum, uint32_t status, uint32_t event_index)
{
    uint32_t result = checksum + (status | (event_index << 8U));
    result ^= result >> 7U;
    return (result << 9U) | (result >> 23U);
}

void AutomotiveHoldoutV2_Initialize(void)
{
    uint32_t index;
    uint32_t history;
    for (index = 0U; index < CONTACTOR_COUNT; ++index)
    {
        s_pack_voltage[index] = (uint16_t)(3520U + (index * 13U));
        s_bus_voltage[index] = (uint16_t)(3475U + (index * 18U));
        s_coil_current[index] = (uint16_t)(150U + (index * 71U));
        s_contactor_command[index] = (uint8_t)((index != 4U) ? 1U : 0U);
        s_contactor_state[index] = (uint8_t)(index & 3U);
    }
    for (index = 0U; index < WHEEL_COUNT; ++index)
    {
        for (history = 0U; history < WHEEL_HISTORY_COUNT; ++history)
        {
            s_wheel_period[index][history] =
                (uint16_t)(1080U + (index * 37U) + (history * 11U));
        }
        s_wheel_pulse_count[index] = (uint16_t)(42U + index);
    }
    for (index = 0U; index < DTC_EVENT_COUNT; ++index)
    {
        s_dtc_active[index] = (uint8_t)(((index % 3U) == 0U) ? 1U : 0U);
        s_dtc_confirm_counter[index] = (uint8_t)(index & 3U);
        s_dtc_heal_counter[index] = (uint8_t)(index % 6U);
        s_dtc_status[index] = (uint8_t)(index & 7U);
    }
    s_holdout_sink = 0U;
}

void AutomotiveHoldoutV2_ApplyScenario(uint32_t task_id, uint32_t scenario_id)
{
    uint32_t index;
    uint32_t history;
    if ((task_id == 0U) && (scenario_id == 1U))
    {
        for (index = 0U; index < CONTACTOR_COUNT; ++index)
        {
            s_pack_voltage[index] = 3500U;
            s_bus_voltage[index] = (uint16_t)(3500U - 85U);
            s_coil_current[index] = (uint16_t)((index & 1U) != 0U ? 90U : 680U);
            s_contactor_command[index] = 1U;
            s_contactor_state[index] = (uint8_t)(index & 3U);
        }
    }
    else if ((task_id == 0U) && (scenario_id == 2U))
    {
        for (index = 0U; index < CONTACTOR_COUNT; ++index)
        {
            s_pack_voltage[index] = 3600U;
            s_bus_voltage[index] = 3300U;
            s_coil_current[index] = (uint16_t)((index & 1U) != 0U ? 70U : 720U);
            s_contactor_command[index] = (uint8_t)((index & 1U) != 0U);
            s_contactor_state[index] = (uint8_t)((index % 3U) + 1U);
        }
    }
    else if ((task_id == 1U) && (scenario_id == 1U))
    {
        for (index = 0U; index < WHEEL_COUNT; ++index)
        {
            for (history = 0U; history < WHEEL_HISTORY_COUNT; ++history)
            {
                s_wheel_period[index][history] = 1100U;
            }
            s_wheel_pulse_count[index] = (uint16_t)(40U + index);
        }
    }
    else if ((task_id == 1U) && (scenario_id == 2U))
    {
        for (index = 0U; index < WHEEL_COUNT; ++index)
        {
            for (history = 0U; history < WHEEL_HISTORY_COUNT; ++history)
            {
                s_wheel_period[index][history] = (uint16_t)(
                    1300U - (history * 47U) + (index * 9U));
            }
            s_wheel_pulse_count[index] = (uint16_t)(38U + (index * 3U));
        }
    }
    else if ((task_id == 2U) && (scenario_id == 1U))
    {
        for (index = 0U; index < DTC_EVENT_COUNT; ++index)
        {
            s_dtc_active[index] = (uint8_t)(index & 1U);
            s_dtc_confirm_counter[index] = 2U;
            s_dtc_heal_counter[index] = 4U;
            s_dtc_status[index] = 0x03U;
        }
    }
    else if ((task_id == 2U) && (scenario_id == 2U))
    {
        for (index = 0U; index < DTC_EVENT_COUNT; ++index)
        {
            s_dtc_active[index] = 0U;
            s_dtc_confirm_counter[index] = 255U;
            s_dtc_heal_counter[index] = 4U;
            s_dtc_status[index] = 0x03U;
        }
    }
    else
    {
        /* Scenario zero is the typical state installed by Initialize. */
    }
}

void BatteryContactorSupervisor_Task10ms(void)
{
    uint32_t channel;
    uint32_t state_mask = 0U;
    uint32_t fault_mask = 0U;
    uint32_t diagnostic = 0xB47C29E1UL;
    for (channel = 0U; channel < CONTACTOR_COUNT; ++channel)
    {
        const uint32_t agreement = EvaluateVoltageAgreement(
            s_pack_voltage[channel], s_bus_voltage[channel]);
        const uint32_t current_fault = EvaluateCoilCurrent(s_coil_current[channel]);
        const uint32_t next_state = NextContactorState(
            s_contactor_state[channel], s_contactor_command[channel],
            agreement, current_fault);
        s_contactor_state[channel] = (uint8_t)next_state;
        state_mask |= next_state << (channel * 3U);
        if ((current_fault != 0U) || (next_state == 3U))
        {
            fault_mask |= 1UL << channel;
        }
        diagnostic = MixContactorDiagnostic(diagnostic, next_state, channel);
    }
    s_holdout_sink = diagnostic ^ state_mask ^ (fault_mask << 24U);
}

void WheelSpeedFusion_Task5ms(void)
{
    uint32_t wheel;
    uint32_t wheel_speed[WHEEL_COUNT];
    uint32_t vehicle_speed = 0U;
    uint32_t slip_mask = 0U;
    for (wheel = 0U; wheel < WHEEL_COUNT; ++wheel)
    {
        const uint32_t period = MedianOfFiveU16(
            s_wheel_period[wheel][0], s_wheel_period[wheel][1],
            s_wheel_period[wheel][2], s_wheel_period[wheel][3],
            s_wheel_period[wheel][4]);
        wheel_speed[wheel] = PeriodToSpeedQ8(period, s_wheel_pulse_count[wheel]);
        vehicle_speed += wheel_speed[wheel];
    }
    vehicle_speed >>= 2U;
    for (wheel = 0U; wheel < WHEEL_COUNT; ++wheel)
    {
        const uint32_t slip = EvaluateWheelSlip(wheel_speed[wheel], vehicle_speed);
        if (slip > 12U)
        {
            slip_mask |= 1UL << wheel;
        }
    }
    s_holdout_sink = vehicle_speed ^ (slip_mask << 24U);
}

void DiagnosticEventAging_Task100ms(void)
{
    uint32_t event;
    uint32_t confirmed_mask = 0U;
    uint32_t checksum = 0xD7C4A915UL;
    for (event = 0U; event < DTC_EVENT_COUNT; ++event)
    {
        uint32_t confirm_count = s_dtc_confirm_counter[event];
        uint32_t heal_count = s_dtc_heal_counter[event];
        if (s_dtc_active[event] != 0U)
        {
            confirm_count = SaturatingIncrementU8(confirm_count);
            heal_count = 0U;
        }
        else
        {
            heal_count = SaturatingIncrementU8(heal_count);
            if (heal_count >= 5U)
            {
                confirm_count = 0U;
            }
        }
        s_dtc_confirm_counter[event] = (uint8_t)confirm_count;
        s_dtc_heal_counter[event] = (uint8_t)heal_count;
        s_dtc_status[event] = (uint8_t)UpdateDtcStatus(
            s_dtc_status[event], s_dtc_active[event], confirm_count, heal_count);
        if ((s_dtc_status[event] & 0x02U) != 0U)
        {
            confirmed_mask |= 1UL << event;
        }
        checksum = UpdateDtcChecksum(checksum, s_dtc_status[event], event);
    }
    s_holdout_sink = checksum ^ confirmed_mask;
}
