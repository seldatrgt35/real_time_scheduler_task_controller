#include "automotive_holdout_v5_tasks.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT16_TYPE__ int16_t;
typedef __INT32_TYPE__ int32_t;

#define WHEEL_COUNT          (4U)
#define PULSE_WINDOW         (6U)
#define PRESSURE_SAMPLES     (8U)
#define CURRENT_SAMPLES      (12U)
#define DERATE_ZONES         (6U)

static volatile uint16_t s_wheel_period[WHEEL_COUNT][PULSE_WINDOW];
static volatile uint16_t s_wheel_spread_limit[WHEEL_COUNT];
static volatile uint16_t s_tank_pressure[PRESSURE_SAMPLES];
static volatile uint16_t s_reference_pressure[PRESSURE_SAMPLES];
static volatile uint8_t s_evap_state;
static volatile uint8_t s_purge_command;
static volatile int16_t s_phase_current[CURRENT_SAMPLES];
static volatile uint16_t s_motor_temperature;
static volatile uint16_t s_temperature_axis[DERATE_ZONES];
static volatile uint16_t s_derate_permille[DERATE_ZONES];
static volatile uint32_t s_holdout_v5_sink;

static uint16_t AbsDiffU16(uint16_t left, uint16_t right)
{
    return (left >= right) ? (uint16_t)(left - right)
                           : (uint16_t)(right - left);
}

static uint16_t MeanU16(const volatile uint16_t *values, uint32_t count)
{
    uint32_t index;
    uint32_t sum = 0U;
    for (index = 0U; index < count; ++index)
    {
        sum += values[index];
    }
    return (uint16_t)(sum / count);
}

static uint16_t CurrentMagnitudeU16(int16_t current)
{
    int32_t widened = current;
    if (widened < 0)
    {
        widened = -widened;
    }
    return (uint16_t)widened;
}

static uint16_t LookupDerateU16(uint16_t temperature)
{
    uint32_t zone;
    uint16_t result = s_derate_permille[DERATE_ZONES - 1U];
    for (zone = 0U; zone < DERATE_ZONES; ++zone)
    {
        if (temperature <= s_temperature_axis[zone])
        {
            result = s_derate_permille[zone];
            break;
        }
    }
    return result;
}

void AutomotiveHoldoutV5_Initialize(void)
{
    uint32_t wheel;
    uint32_t sample;

    for (wheel = 0U; wheel < WHEEL_COUNT; ++wheel)
    {
        s_wheel_spread_limit[wheel] = (uint16_t)(28U + wheel * 3U);
        for (sample = 0U; sample < PULSE_WINDOW; ++sample)
        {
            s_wheel_period[wheel][sample] =
                (uint16_t)(920U + wheel * 17U + ((sample * 11U) % 37U));
        }
    }
    for (sample = 0U; sample < PRESSURE_SAMPLES; ++sample)
    {
        s_tank_pressure[sample] = (uint16_t)(510U + sample * 9U);
        s_reference_pressure[sample] = (uint16_t)(548U - sample * 3U);
    }
    s_evap_state = 2U;
    s_purge_command = 64U;
    for (sample = 0U; sample < CURRENT_SAMPLES; ++sample)
    {
        s_phase_current[sample] =
            (int16_t)((int32_t)((sample * 47U) % 281U) - 140);
    }
    s_motor_temperature = 104U;
    for (sample = 0U; sample < DERATE_ZONES; ++sample)
    {
        s_temperature_axis[sample] = (uint16_t)(65U + sample * 12U);
        s_derate_permille[sample] = (uint16_t)(1000U - sample * 135U);
    }
    s_holdout_v5_sink = 0U;
}

void WheelPulseCoherence_Task2ms(void)
{
    uint32_t wheel;
    uint32_t sample;
    uint32_t invalid_mask = 0U;
    uint32_t signature = 0U;

    for (wheel = 0U; wheel < WHEEL_COUNT; ++wheel)
    {
        uint16_t minimum = 0xFFFFU;
        uint16_t maximum = 0U;
        uint32_t adjacent_delta = 0U;
        uint16_t previous = s_wheel_period[wheel][0];
        for (sample = 0U; sample < PULSE_WINDOW; ++sample)
        {
            const uint16_t current = s_wheel_period[wheel][sample];
            if (current < minimum)
            {
                minimum = current;
            }
            if (current > maximum)
            {
                maximum = current;
            }
            adjacent_delta += AbsDiffU16(current, previous);
            previous = current;
            signature = (signature * 17U) ^ current ^ (wheel << sample);
        }
        if (((uint16_t)(maximum - minimum) > s_wheel_spread_limit[wheel]) ||
            (adjacent_delta > 125U))
        {
            invalid_mask |= 1UL << wheel;
        }
    }
    s_holdout_v5_sink = signature ^ invalid_mask;
}

void EvapPurgeDiagnostic_Task100ms(void)
{
    uint32_t diagnostic_flags = 0U;
    uint32_t score = 0U;
    const uint16_t tank_mean = MeanU16(s_tank_pressure, PRESSURE_SAMPLES);
    const uint16_t reference_mean =
        MeanU16(s_reference_pressure, PRESSURE_SAMPLES);
    const uint16_t pressure_delta = AbsDiffU16(tank_mean, reference_mean);

    switch (s_evap_state)
    {
        case 0U:
            score = pressure_delta;
            if (pressure_delta < 12U)
            {
                s_evap_state = 1U;
            }
            break;
        case 1U:
            score = pressure_delta * (uint32_t)(s_purge_command + 1U);
            if (pressure_delta > 42U)
            {
                diagnostic_flags |= 1U;
                s_evap_state = 3U;
            }
            else
            {
                s_evap_state = 2U;
            }
            break;
        case 2U:
            score = (uint32_t)(tank_mean + reference_mean) * pressure_delta;
            if ((pressure_delta > 30U) && (s_purge_command > 48U))
            {
                diagnostic_flags |= 2U;
            }
            s_evap_state = 3U;
            break;
        default:
            score = pressure_delta ^ 0x5A5AU;
            diagnostic_flags |= 4U;
            break;
    }
    s_holdout_v5_sink = score ^ diagnostic_flags ^ s_evap_state;
}

void MotorCurrentDerating_Task5ms(void)
{
    uint32_t sample;
    uint32_t magnitude_sum = 0U;
    uint32_t peak = 0U;
    uint32_t overload_count = 0U;
    uint32_t checksum = 0U;
    const uint16_t derate = LookupDerateU16(s_motor_temperature);

    for (sample = 0U; sample < CURRENT_SAMPLES; ++sample)
    {
        const uint16_t magnitude = CurrentMagnitudeU16(s_phase_current[sample]);
        magnitude_sum += magnitude;
        if (magnitude > peak)
        {
            peak = magnitude;
        }
        if (magnitude > 96U)
        {
            ++overload_count;
        }
        checksum = (checksum << 5U) ^ (checksum >> 3U) ^ magnitude;
    }
    magnitude_sum = (magnitude_sum * derate) / 1000U;
    if ((peak > 132U) || (overload_count >= 4U))
    {
        magnitude_sum = (magnitude_sum * 3U) / 4U;
    }
    s_holdout_v5_sink = magnitude_sum ^ peak ^ overload_count ^ checksum;
}
