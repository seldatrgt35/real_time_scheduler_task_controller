#include "multi_call_automotive_tasks.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;

#define STAR_NOINLINE __attribute__((noinline))
#define COOLING_SAMPLE_COUNT (12U)
#define OCCUPANT_ZONE_COUNT   (8U)
#define CAN_SIGNAL_COUNT      (16U)

static uint16_t s_coolant_temperature[COOLING_SAMPLE_COUNT];
static uint16_t s_pump_current[COOLING_SAMPLE_COUNT];
static uint16_t s_pump_speed[COOLING_SAMPLE_COUNT];
static uint16_t s_seat_pressure[OCCUPANT_ZONE_COUNT];
static uint8_t s_door_state[OCCUPANT_ZONE_COUNT];
static uint8_t s_belt_state[OCCUPANT_ZONE_COUNT];
static uint16_t s_can_raw[CAN_SIGNAL_COUNT];
static uint16_t s_can_minimum[CAN_SIGNAL_COUNT];
static uint16_t s_can_maximum[CAN_SIGNAL_COUNT];
static volatile uint32_t s_multi_call_sink;

static STAR_NOINLINE uint32_t AbsoluteDifferenceU32(uint32_t left, uint32_t right)
{
    return (left >= right) ? (left - right) : (right - left);
}

static STAR_NOINLINE uint32_t ClampU32(uint32_t value, uint32_t lower, uint32_t upper)
{
    uint32_t result = value;
    if (result < lower)
    {
        result = lower;
    }
    else if (result > upper)
    {
        result = upper;
    }
    else
    {
        /* Value is already in range. */
    }
    return result;
}

static STAR_NOINLINE uint32_t CoolingDemandQ8(uint32_t temperature)
{
    uint32_t demand;
    if (temperature > 940U)
    {
        demand = 256U;
    }
    else if (temperature > 820U)
    {
        demand = 128U + ((temperature - 820U) * 128U) / 120U;
    }
    else
    {
        demand = 64U;
    }
    return demand;
}

static STAR_NOINLINE uint32_t ExpectedPumpSpeed(uint32_t demand_q8)
{
    return 500U + ((demand_q8 * 3500U) >> 8U);
}

static STAR_NOINLINE uint32_t UpdateDiagnosticWord(
    uint32_t diagnostic, uint32_t error, uint32_t index)
{
    uint32_t result = diagnostic ^ (error + (index * 0x45D9F3BU));
    result = (result << 5U) | (result >> 27U);
    return result;
}

static STAR_NOINLINE uint32_t DecodeOccupancy(uint16_t pressure)
{
    uint32_t state;
    if (pressure > 1450U)
    {
        state = 2U;
    }
    else if (pressure > 280U)
    {
        state = 1U;
    }
    else
    {
        state = 0U;
    }
    return state;
}

static STAR_NOINLINE uint32_t EvaluateRestraintFault(
    uint32_t occupancy, uint32_t door_open, uint32_t belt_latched)
{
    uint32_t fault = 0U;
    if ((occupancy != 0U) && (belt_latched == 0U))
    {
        fault |= 1U;
    }
    if ((occupancy == 2U) && (door_open != 0U))
    {
        fault |= 2U;
    }
    return fault;
}

static STAR_NOINLINE uint32_t MixSafetySignature(
    uint32_t signature, uint32_t value, uint32_t zone)
{
    uint32_t result = signature + (value ^ (zone * 0x9E37U));
    result ^= result >> 11U;
    result *= 33U;
    return result;
}

static STAR_NOINLINE int32_t ScaleCanSignal(uint16_t raw, uint32_t signal_index)
{
    const int32_t gain = (int32_t)(signal_index + 3U);
    const int32_t offset = (int32_t)((signal_index & 3U) * 25U);
    return ((int32_t)raw * gain) - offset;
}

static STAR_NOINLINE uint32_t IsSignalInRange(
    int32_t value, uint16_t minimum, uint16_t maximum)
{
    const int32_t signed_minimum = (int32_t)minimum;
    const int32_t signed_maximum = (int32_t)maximum * 20;
    return ((value >= signed_minimum) && (value <= signed_maximum)) ? 1U : 0U;
}

static STAR_NOINLINE uint32_t UpdateGatewayCrc(
    uint32_t crc, uint32_t value, uint32_t signal_index)
{
    uint32_t result = crc ^ value ^ (signal_index << 16U);
    uint32_t bit;
    for (bit = 0U; bit < 4U; ++bit)
    {
        const uint32_t feedback = result & 1U;
        result >>= 1U;
        if (feedback != 0U)
        {
            result ^= 0xEDB88320UL;
        }
    }
    return result;
}

void MultiCallAutomotive_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < COOLING_SAMPLE_COUNT; ++index)
    {
        s_coolant_temperature[index] = (uint16_t)(760U + (index * 19U));
        s_pump_current[index] = (uint16_t)(210U + (index * 7U));
        s_pump_speed[index] = (uint16_t)(1550U + (index * 83U));
    }
    for (index = 0U; index < OCCUPANT_ZONE_COUNT; ++index)
    {
        s_seat_pressure[index] = (uint16_t)(180U + (index * 245U));
        s_door_state[index] = (uint8_t)((index == 3U) ? 1U : 0U);
        s_belt_state[index] = (uint8_t)((index & 1U) != 0U);
    }
    for (index = 0U; index < CAN_SIGNAL_COUNT; ++index)
    {
        s_can_raw[index] = (uint16_t)(95U + (index * 41U));
        s_can_minimum[index] = (uint16_t)(20U + index);
        s_can_maximum[index] = (uint16_t)(240U + (index * 14U));
    }
    s_multi_call_sink = 0U;
}

void CoolingPumpDiagnostic_Task10ms(void)
{
    uint32_t index;
    uint32_t accumulated_error = 0U;
    uint32_t overcurrent_count = 0U;
    uint32_t diagnostic = 0xC001C0DEUL;

    for (index = 0U; index < COOLING_SAMPLE_COUNT; ++index)
    {
        const uint32_t demand = CoolingDemandQ8(s_coolant_temperature[index]);
        const uint32_t expected_speed = ExpectedPumpSpeed(demand);
        const uint32_t speed_error = AbsoluteDifferenceU32(
            expected_speed, s_pump_speed[index]);
        const uint32_t bounded_error = ClampU32(speed_error, 0U, 4095U);
        accumulated_error += bounded_error;
        if (s_pump_current[index] > (260U + (demand >> 2U)))
        {
            ++overcurrent_count;
        }
        diagnostic = UpdateDiagnosticWord(diagnostic, bounded_error, index);
    }
    s_multi_call_sink = diagnostic ^ accumulated_error ^ overcurrent_count;
}

void OccupantDoorSafety_Task20ms(void)
{
    uint32_t zone;
    uint32_t occupied_mask = 0U;
    uint32_t fault_mask = 0U;
    uint32_t signature = 0x714A92D3UL;

    for (zone = 0U; zone < OCCUPANT_ZONE_COUNT; ++zone)
    {
        const uint32_t occupancy = DecodeOccupancy(s_seat_pressure[zone]);
        const uint32_t fault = EvaluateRestraintFault(
            occupancy, s_door_state[zone], s_belt_state[zone]);
        const uint32_t packed = occupancy | (fault << 4U);
        if (occupancy != 0U)
        {
            occupied_mask |= 1UL << zone;
        }
        if (fault != 0U)
        {
            fault_mask |= 1UL << zone;
        }
        signature = MixSafetySignature(signature, packed, zone);
    }
    s_multi_call_sink = signature ^ occupied_mask ^ (fault_mask << 16U);
}

void CanSignalGateway_Task5ms(void)
{
    uint32_t signal;
    uint32_t valid_count = 0U;
    uint32_t invalid_mask = 0U;
    uint32_t accumulated = 0U;
    uint32_t crc = 0xFFFFFFFFUL;

    for (signal = 0U; signal < CAN_SIGNAL_COUNT; ++signal)
    {
        const int32_t scaled = ScaleCanSignal(s_can_raw[signal], signal);
        const uint32_t valid = IsSignalInRange(
            scaled, s_can_minimum[signal], s_can_maximum[signal]);
        const uint32_t bounded = ClampU32((uint32_t)scaled, 0U, 65535U);
        if (valid != 0U)
        {
            accumulated += bounded;
            ++valid_count;
        }
        else
        {
            invalid_mask |= 1UL << signal;
        }
        crc = UpdateGatewayCrc(crc, bounded, signal);
    }
    s_multi_call_sink = crc ^ accumulated ^ invalid_mask ^ valid_count;
}
