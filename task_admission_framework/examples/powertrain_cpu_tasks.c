#include "powertrain_cpu_tasks.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;
typedef __INT64_TYPE__ int64_t;

#define STAR_SENSOR_COUNT (64U)
#define STAR_MAP_SIZE     (16U)

static int32_t g_star_sensor_samples[STAR_SENSOR_COUNT];
static int32_t g_star_pedal_map[STAR_MAP_SIZE + 1U];
static int32_t g_star_torque_map[STAR_MAP_SIZE + 1U];
static volatile int32_t g_star_requested_torque;
static volatile int32_t g_star_filtered_speed;
static volatile int32_t g_star_safe_torque;

void StarPowertrainCpu_Initialize(void)
{
    uint32_t index;

    for (index = 0U; index < STAR_SENSOR_COUNT; ++index)
    {
        g_star_sensor_samples[index] = (int32_t)((index * 47U) & 1023U) - 256;
    }
    for (index = 0U; index <= STAR_MAP_SIZE; ++index)
    {
        g_star_pedal_map[index] = (int32_t)(index * 180U);
        g_star_torque_map[index] = (int32_t)(index * 220U) - 400;
    }
    g_star_requested_torque = 0;
    g_star_filtered_speed = 0;
    g_star_safe_torque = 0;
}

void PowertrainFastControlTask_5ms(void)
{
    uint32_t index;
    int32_t sensor_sum = 0;
    int32_t mapped_torque = 0;

    /* Combine bounded pedal and speed samples using signed arithmetic. */
    for (index = 0U; index < 32U; ++index)
    {
        const int32_t sample = g_star_sensor_samples[index];
        sensor_sum += sample;
        sensor_sum -= (sample / 4);
        sensor_sum += (sample * 3);
    }

    /* Interpolate the pedal request from a deterministic calibration map. */
    for (index = 0U; index < 24U; ++index)
    {
        const uint32_t map_index = (index * 5U) & (STAR_MAP_SIZE - 1U);
        const int32_t lower = g_star_pedal_map[map_index];
        const int32_t upper = g_star_pedal_map[map_index + 1U];
        const int32_t fraction_q8 = (int32_t)((index * 37U) & 255U);
        const int64_t delta = (int64_t)(upper - lower) * (int64_t)fraction_q8;
        mapped_torque += lower + (int32_t)(delta / 256);
    }

    /* Apply the actuator torque range after the request calculation. */
    for (index = 0U; index < 32U; ++index)
    {
        int32_t value = (sensor_sum / 64) + (mapped_torque / 128);

        if (value > 3000)
        {
            value = 3000;
        }
        else if (value < 0)
        {
            value = 0;
        }
        else
        {
            /* The requested torque is already inside the actuator range. */
        }
        mapped_torque += value;
    }
    g_star_requested_torque = mapped_torque;
}

void PowertrainSensorTask_10ms(void)
{
    uint32_t index;
    int32_t filtered_speed = 0;
    int32_t converted_speed = 0;

    /* Filter bounded RPM and vehicle-speed samples. */
    for (index = 0U; index < 24U; ++index)
    {
        const int32_t sample = g_star_sensor_samples[index + 16U];
        filtered_speed += sample;
        filtered_speed -= (sample / 4);
        filtered_speed += (sample * 3);
    }

    /* Convert sensor values using interpolation between calibration points. */
    for (index = 0U; index < 32U; ++index)
    {
        const uint32_t map_index = (index * 7U) & (STAR_MAP_SIZE - 1U);
        const int32_t lower = g_star_torque_map[map_index];
        const int32_t upper = g_star_torque_map[map_index + 1U];
        const int32_t fraction_q8 = (int32_t)((index * 29U) & 255U);
        const int64_t delta = (int64_t)(upper - lower) * (int64_t)fraction_q8;
        converted_speed += lower + (int32_t)(delta / 256);
    }

    for (index = 0U; index < 24U; ++index)
    {
        int32_t value = (filtered_speed / 32) + (converted_speed / 128);

        if (value > 8000)
        {
            value = 8000;
        }
        else if (value < 0)
        {
            value = 0;
        }
        else
        {
            /* The filtered speed is plausible. */
        }
        converted_speed += value;
    }
    g_star_filtered_speed = converted_speed;
}

void PowertrainTorqueSafetyTask_20ms(void)
{
    uint32_t index;
    int32_t torque_limit = 0;
    int32_t traction_limit = 0;

    /* Read bounded torque limits from a calibration table. */
    for (index = 0U; index < 32U; ++index)
    {
        const uint32_t map_index = (index * 3U) & (STAR_MAP_SIZE - 1U);
        torque_limit += g_star_torque_map[map_index];
    }

    /* Interpolate the traction-control reduction request. */
    for (index = 0U; index < 24U; ++index)
    {
        const uint32_t map_index = (index * 11U) & (STAR_MAP_SIZE - 1U);
        const int32_t lower = g_star_torque_map[map_index];
        const int32_t upper = g_star_torque_map[map_index + 1U];
        const int32_t fraction_q8 = (int32_t)((index * 41U) & 255U);
        const int64_t delta = (int64_t)(upper - lower) * (int64_t)fraction_q8;
        traction_limit += lower + (int32_t)(delta / 256);
    }

    /* Enforce the final safety envelope before actuator output. */
    for (index = 0U; index < 48U; ++index)
    {
        int32_t value = (g_star_requested_torque / 64) - (traction_limit / 128);

        if (value > torque_limit)
        {
            value = torque_limit;
        }
        else if (value < 0)
        {
            value = 0;
        }
        else
        {
            /* No additional torque reduction is required. */
        }
        torque_limit += value;
    }
    g_star_safe_torque = torque_limit;
}
