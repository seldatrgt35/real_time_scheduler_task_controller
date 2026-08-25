#include "deterministic_automotive_task.h"

#define STAR_CHANNEL_COUNT       (16U)
#define STAR_TORQUE_MIN_Q15      (-32768)
#define STAR_TORQUE_MAX_Q15      (32767)
#define STAR_SENSOR_DELTA_LIMIT  (140U)

#if defined(__GNUC__) || defined(__clang__)
#define STAR_NOINLINE __attribute__((noinline))
#else
#define STAR_NOINLINE
#endif

typedef int32_t (*StarLimitFunction)(int32_t value, int32_t lower, int32_t upper);

static StarAutomotiveInputs s_inputs;
static StarAutomotiveOutputs s_outputs;
static uint32_t s_filtered_pedal[STAR_CHANNEL_COUNT];
static uint32_t s_filtered_speed[STAR_CHANNEL_COUNT];
static uint32_t s_fault_bitmap;
static uint32_t s_accumulated_current;

static STAR_NOINLINE int32_t StarClampS32(int32_t value,
                                         int32_t lower,
                                         int32_t upper)
{
    int32_t result = value;
    if (result > upper)
    {
        result = upper;
    }
    else if (result < lower)
    {
        result = lower;
    }
    else
    {
        /* Value is already inside the calibrated range. */
    }
    return result;
}

static STAR_NOINLINE uint32_t StarRotateLeft32(uint32_t value, uint32_t shift)
{
    return (value << shift) | (value >> (32U - shift));
}

static const StarLimitFunction s_limit_function = StarClampS32;

void StarAutomotiveTask_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < STAR_CHANNEL_COUNT; ++index)
    {
        s_inputs.pedal_raw[index] = (uint16_t)(900U + (index * 9U));
        s_inputs.speed_raw[index] = (uint16_t)(1200U + (index * 7U));
        s_inputs.current_raw[index] = (uint16_t)(180U + (index * 3U));
        s_inputs.status_words[index] = 0xA5000000UL | index;
        s_filtered_pedal[index] = 0U;
        s_filtered_speed[index] = 0U;
    }
    s_fault_bitmap = 0U;
    s_accumulated_current = 0U;
    s_outputs.requested_torque_q15 = 0;
    s_outputs.diagnostic_checksum = 0U;
    s_outputs.packed_status = 0U;
    s_outputs.thermal_derate = 1.0F;
}

void StarAutomotiveTask_SensorAcquisition(void)
{
    uint32_t index;
    uint32_t pedal_sum = 0U;
    for (index = 0U; index < STAR_CHANNEL_COUNT; ++index)
    {
        pedal_sum += s_inputs.pedal_raw[index];
    }
    s_accumulated_current = pedal_sum;
}

void StarAutomotiveTask_Plausibility(void)
{
    uint32_t index;
    uint32_t faults = 0U;
    for (index = 0U; index < STAR_CHANNEL_COUNT; ++index)
    {
        const uint32_t pedal = s_filtered_pedal[index];
        const uint32_t speed = s_filtered_speed[index];
        const uint32_t delta = (speed > pedal) ? (speed - pedal) : (pedal - speed);
        if (delta > STAR_SENSOR_DELTA_LIMIT)
        {
            faults |= (1UL << index);
        }
        else
        {
            faults &= ~(1UL << index);
        }
    }
    s_fault_bitmap = faults;
}

void StarAutomotiveTask_Control(void)
{
    uint32_t index;
    int32_t torque_q15 = 0;
    float temperature_model = 25.0F;
    for (index = 0U; index < STAR_CHANNEL_COUNT; ++index)
    {
        const int32_t pedal_q15 = (int32_t)(s_filtered_pedal[index] << 5U);
        const int32_t speed_feedback_q15 = (int32_t)(s_filtered_speed[index] << 3U);
        torque_q15 += ((pedal_q15 * 3) - speed_feedback_q15) / 4;
        temperature_model = (temperature_model + (float)s_inputs.current_raw[index]) * 0.5F;
    }
    if (s_fault_bitmap != 0U)
    {
        torque_q15 /= 2;
    }
    s_outputs.requested_torque_q15 =
        s_limit_function(torque_q15, STAR_TORQUE_MIN_Q15, STAR_TORQUE_MAX_Q15);
    s_outputs.thermal_derate = temperature_model;
}

void StarAutomotiveTask_Diagnostics(void)
{
    uint32_t index;
    uint32_t checksum = 0xFFFFFFFFUL;
    for (index = 0U; index < STAR_CHANNEL_COUNT; ++index)
    {
        checksum ^= s_inputs.status_words[index];
        checksum = StarRotateLeft32(checksum, 5U);
        checksum += s_filtered_pedal[index] & 0xFFFFU;
    }
    s_outputs.diagnostic_checksum = checksum;
}

void StarAutomotiveTask_OutputPacking(void)
{
    uint32_t packed;
    switch (s_fault_bitmap & 3U)
    {
        case 0U: packed = 0x10000000UL; break;
        case 1U: packed = 0x20000000UL; break;
        case 2U: packed = 0x40000000UL; break;
        default: packed = 0x80000000UL; break;
    }
    packed |= ((uint32_t)s_outputs.requested_torque_q15) & 0x0000FFFFUL;
    packed ^= (s_accumulated_current & 0x0FFFU) << 16U;
    s_outputs.packed_status = packed;
}

void StarAutomotiveTask_10ms(void)
{
    StarAutomotiveTask_SensorAcquisition();
    StarAutomotiveTask_Plausibility();
    StarAutomotiveTask_Control();
    StarAutomotiveTask_Diagnostics();
    StarAutomotiveTask_OutputPacking();
}

const StarAutomotiveOutputs *StarAutomotiveTask_GetOutputs(void)
{
    return &s_outputs;
}
