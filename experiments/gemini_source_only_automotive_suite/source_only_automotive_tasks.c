#include "source_only_automotive_tasks.h"

#define STEERING_SAMPLE_COUNT (8U)
#define BRAKE_CHANNEL_COUNT    (6U)
#define INVERTER_SENSOR_COUNT  (10U)

static uint16_t s_steering_primary[STEERING_SAMPLE_COUNT];
static uint16_t s_steering_secondary[STEERING_SAMPLE_COUNT];
static uint16_t s_brake_pressure[ BRAKE_CHANNEL_COUNT];
static uint16_t s_inverter_temperature[INVERTER_SENSOR_COUNT];
static uint16_t s_inverter_current[INVERTER_SENSOR_COUNT];
static volatile uint32_t s_output_sink;

static uint32_t RotateLeft32(uint32_t value, uint32_t shift)
{
    return (value << shift) | (value >> (32U - shift));
}

static uint32_t AbsoluteDifferenceU16(uint16_t left, uint16_t right)
{
    return (left >= right) ? ((uint32_t)left - right) : ((uint32_t)right - left);
}

void SourceOnlyAutomotive_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < STEERING_SAMPLE_COUNT; ++index)
    {
        s_steering_primary[index] = (uint16_t)(2020U + (index * 11U));
        s_steering_secondary[index] = (uint16_t)(2012U + (index * 13U));
    }
    for (index = 0U; index < BRAKE_CHANNEL_COUNT; ++index)
    {
        s_brake_pressure[index] = (uint16_t)(850U + (index * 37U));
    }
    for (index = 0U; index < INVERTER_SENSOR_COUNT; ++index)
    {
        s_inverter_temperature[index] = (uint16_t)(620U + (index * 9U));
        s_inverter_current[index] = (uint16_t)(140U + (index * 17U));
    }
    s_output_sink = 0U;
}

void SteeringPlausibility_Task5ms(void)
{
    uint32_t index;
    uint32_t primary_sum = 0U;
    uint32_t secondary_sum = 0U;
    uint32_t fault_mask = 0U;
    uint32_t checksum = 0x13579BDFUL;

    for (index = 0U; index < STEERING_SAMPLE_COUNT; ++index)
    {
        const uint16_t primary = s_steering_primary[index];
        const uint16_t secondary = s_steering_secondary[index];
        const uint32_t delta = AbsoluteDifferenceU16(primary, secondary);
        primary_sum += primary;
        secondary_sum += secondary;
        if (delta > 45U)
        {
            fault_mask |= 1UL << index;
        }
        else if ((primary < 200U) || (primary > 3900U))
        {
            fault_mask |= 1UL << (index + 16U);
        }
        else
        {
            checksum ^= ((uint32_t)primary << 16U) | secondary;
        }
        checksum = RotateLeft32(checksum, 3U) + delta;
    }
    s_output_sink = checksum ^ fault_mask ^ primary_sum ^ secondary_sum;
}

void BrakePressureVoting_Task10ms(void)
{
    uint32_t outer;
    uint32_t inner;
    uint32_t accepted_sum = 0U;
    uint32_t accepted_count = 0U;
    uint32_t disagreement_mask = 0U;

    for (outer = 0U; outer < BRAKE_CHANNEL_COUNT; ++outer)
    {
        uint32_t neighbours = 0U;
        for (inner = 0U; inner < BRAKE_CHANNEL_COUNT; ++inner)
        {
            if (AbsoluteDifferenceU16(
                    s_brake_pressure[outer], s_brake_pressure[inner]) <= 120U)
            {
                ++neighbours;
            }
        }
        if (neighbours >= 4U)
        {
            accepted_sum += s_brake_pressure[outer];
            ++accepted_count;
        }
        else
        {
            disagreement_mask |= 1UL << outer;
        }
    }
    if (accepted_count != 0U)
    {
        accepted_sum /= accepted_count;
    }
    s_output_sink = accepted_sum ^ disagreement_mask ^ accepted_count;
}

void InverterThermalDerating_Task20ms(void)
{
    uint32_t index;
    uint32_t thermal_score = 0U;
    uint32_t derating_q10 = 1024U;
    uint32_t diagnostic = 0xA5A5A5A5UL;

    for (index = 0U; index < INVERTER_SENSOR_COUNT; ++index)
    {
        const uint32_t temperature = s_inverter_temperature[index];
        const uint32_t current = s_inverter_current[index];
        thermal_score += (temperature * current) >> 5U;
        if (temperature > 900U)
        {
            derating_q10 -= 64U;
        }
        else if (temperature > 760U)
        {
            derating_q10 -= 24U;
        }
        else
        {
            derating_q10 -= 4U;
        }
        diagnostic ^= (temperature << 16U) | current;
        diagnostic = RotateLeft32(diagnostic, 7U);
    }
    if (thermal_score > 180000U)
    {
        derating_q10 >>= 1U;
    }
    s_output_sink = diagnostic ^ thermal_score ^ derating_q10;
}
