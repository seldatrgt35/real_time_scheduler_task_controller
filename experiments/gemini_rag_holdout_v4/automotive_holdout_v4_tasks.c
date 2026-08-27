#include "automotive_holdout_v4_tasks.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;

#define PHASE_COUNT        (3U)
#define RIPPLE_SAMPLES     (8U)
#define NETWORK_SIGNALS    (16U)
#define INJECTOR_COUNT     (8U)
#define BREAKPOINT_COUNT   (8U)

static volatile uint16_t s_phase_samples[PHASE_COUNT][RIPPLE_SAMPLES];
static volatile uint16_t s_phase_ripple_limit[PHASE_COUNT];
static volatile uint16_t s_signal_age[NETWORK_SIGNALS];
static volatile uint16_t s_signal_timeout[NETWORK_SIGNALS];
static volatile uint8_t s_signal_received[NETWORK_SIGNALS];
static volatile uint8_t s_signal_state[NETWORK_SIGNALS];
static volatile uint16_t s_engine_speed;
static volatile uint16_t s_battery_mv;
static volatile int32_t s_cylinder_trim[INJECTOR_COUNT];
static volatile uint16_t s_speed_axis[BREAKPOINT_COUNT];
static volatile uint16_t s_pulse_table[BREAKPOINT_COUNT];
static volatile uint32_t s_holdout_v4_sink;

static uint16_t AbsoluteDifferenceU16(uint16_t left, uint16_t right)
{
    return (left >= right) ? (uint16_t)(left - right)
                           : (uint16_t)(right - left);
}

static uint16_t InterpolatePulseU16(uint16_t speed)
{
    uint32_t index;
    uint32_t numerator;
    uint32_t denominator;
    uint32_t result;

    if (speed <= s_speed_axis[0])
    {
        result = s_pulse_table[0];
    }
    else if (speed >= s_speed_axis[BREAKPOINT_COUNT - 1U])
    {
        result = s_pulse_table[BREAKPOINT_COUNT - 1U];
    }
    else
    {
        result = s_pulse_table[0];
        for (index = 1U; index < BREAKPOINT_COUNT; ++index)
        {
            if (speed <= s_speed_axis[index])
            {
                numerator = (uint32_t)(speed - s_speed_axis[index - 1U]) *
                            (uint32_t)(s_pulse_table[index] -
                                       s_pulse_table[index - 1U]);
                denominator = (uint32_t)(s_speed_axis[index] -
                                         s_speed_axis[index - 1U]);
                result = (uint32_t)s_pulse_table[index - 1U] +
                         (numerator / denominator);
                break;
            }
        }
    }
    return (uint16_t)result;
}

static uint16_t ApplyVoltageCorrectionU16(uint16_t pulse, uint16_t battery_mv)
{
    uint32_t corrected = pulse;
    if (battery_mv < 10500U)
    {
        corrected += 180U;
    }
    else if (battery_mv < 12000U)
    {
        corrected += 90U;
    }
    else if (battery_mv > 15000U)
    {
        corrected -= (corrected > 60U) ? 60U : corrected;
    }
    else
    {
        /* No voltage correction in the nominal range. */
    }
    return (uint16_t)corrected;
}

void AutomotiveHoldoutV4_Initialize(void)
{
    uint32_t phase;
    uint32_t sample;
    uint32_t signal;
    uint32_t injector;

    for (phase = 0U; phase < PHASE_COUNT; ++phase)
    {
        s_phase_ripple_limit[phase] = (uint16_t)(105U + (phase * 9U));
        for (sample = 0U; sample < RIPPLE_SAMPLES; ++sample)
        {
            s_phase_samples[phase][sample] =
                (uint16_t)(720U + (phase * 31U) +
                           ((sample * sample + phase * 7U) % 83U));
        }
    }
    for (signal = 0U; signal < NETWORK_SIGNALS; ++signal)
    {
        s_signal_age[signal] = (uint16_t)(signal * 7U);
        s_signal_timeout[signal] = (uint16_t)(35U + ((signal % 4U) * 20U));
        s_signal_received[signal] =
            (uint8_t)(((signal == 2U) || (signal == 11U)) ? 1U : 0U);
        s_signal_state[signal] = (uint8_t)(signal % 3U);
    }
    s_engine_speed = 2875U;
    s_battery_mv = 11200U;
    for (injector = 0U; injector < INJECTOR_COUNT; ++injector)
    {
        s_cylinder_trim[injector] = (int32_t)((injector * 13U) % 41U) - 20;
    }
    for (injector = 0U; injector < BREAKPOINT_COUNT; ++injector)
    {
        s_speed_axis[injector] = (uint16_t)(500U + (injector * 750U));
        s_pulse_table[injector] = (uint16_t)(900U + (injector * 125U));
    }
    s_holdout_v4_sink = 0U;
}

void DcLinkRippleMonitor_Task1ms(void)
{
    uint32_t phase;
    uint32_t sample;
    uint32_t fault_mask = 0U;
    uint32_t signature = 0U;

    for (phase = 0U; phase < PHASE_COUNT; ++phase)
    {
        uint16_t minimum = 0xFFFFU;
        uint16_t maximum = 0U;
        uint32_t deviation_sum = 0U;
        for (sample = 0U; sample < RIPPLE_SAMPLES; ++sample)
        {
            const uint16_t value = s_phase_samples[phase][sample];
            if (value < minimum)
            {
                minimum = value;
            }
            if (value > maximum)
            {
                maximum = value;
            }
            deviation_sum += AbsoluteDifferenceU16(value, 760U);
            signature = (signature << 3U) ^ value ^ (signature >> 2U);
        }
        if (((uint16_t)(maximum - minimum) > s_phase_ripple_limit[phase]) ||
            (deviation_sum > 620U))
        {
            fault_mask |= 1UL << phase;
        }
    }
    s_holdout_v4_sink = signature ^ fault_mask;
}

void NetworkSignalSupervision_Task10ms(void)
{
    uint32_t signal;
    uint32_t timeout_mask = 0U;
    uint32_t recovered_mask = 0U;
    uint32_t state_checksum = 0U;

    for (signal = 0U; signal < NETWORK_SIGNALS; ++signal)
    {
        uint16_t age = s_signal_age[signal];
        uint8_t state = s_signal_state[signal];
        if (s_signal_received[signal] != 0U)
        {
            age = 0U;
            s_signal_received[signal] = 0U;
            if (state == 2U)
            {
                state = 1U;
                recovered_mask |= 1UL << signal;
            }
        }
        else
        {
            age = (age <= 0xFFF5U) ? (uint16_t)(age + 10U) : 0xFFFFU;
            if (age >= s_signal_timeout[signal])
            {
                state = 2U;
                timeout_mask |= 1UL << signal;
            }
            else if (state == 0U)
            {
                state = 1U;
            }
            else
            {
                /* State remains valid until the timeout threshold. */
            }
        }
        s_signal_age[signal] = age;
        s_signal_state[signal] = state;
        state_checksum += ((uint32_t)state + 1U) * (signal + 3U);
    }
    s_holdout_v4_sink = timeout_mask ^ recovered_mask ^ state_checksum;
}

void InjectorPulseCompensation_Task5ms(void)
{
    uint32_t injector;
    uint32_t checksum = 0U;
    uint32_t saturation_mask = 0U;
    const uint16_t base_pulse = InterpolatePulseU16(s_engine_speed);
    const uint16_t voltage_pulse =
        ApplyVoltageCorrectionU16(base_pulse, s_battery_mv);

    for (injector = 0U; injector < INJECTOR_COUNT; ++injector)
    {
        int32_t command = (int32_t)voltage_pulse + s_cylinder_trim[injector];
        if (command < 600)
        {
            command = 600;
            saturation_mask |= 1UL << injector;
        }
        else if (command > 2400)
        {
            command = 2400;
            saturation_mask |= 1UL << injector;
        }
        else
        {
            /* Command is already in the calibrated actuator range. */
        }
        checksum = (checksum * 33U) ^ (uint32_t)command ^ injector;
    }
    s_holdout_v4_sink = checksum ^ saturation_mask;
}
