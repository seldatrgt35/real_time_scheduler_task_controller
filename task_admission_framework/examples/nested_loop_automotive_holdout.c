#include "nested_loop_automotive_holdout.h"

typedef __UINT32_TYPE__ uint32_t;

#define STAR_SENSOR_COUNT  (8U)
#define STAR_SAMPLE_COUNT  (4U)

static uint32_t s_sensor_samples[STAR_SENSOR_COUNT][STAR_SAMPLE_COUNT];
static uint32_t s_filtered_sensor[STAR_SENSOR_COUNT];
static volatile uint32_t s_nested_loop_sink;

void NestedLoopAutomotive_Initialize(void)
{
    uint32_t sensor;
    uint32_t sample;
    for (sensor = 0U; sensor < STAR_SENSOR_COUNT; ++sensor)
    {
        for (sample = 0U; sample < STAR_SAMPLE_COUNT; ++sample)
        {
            s_sensor_samples[sensor][sample] =
                (sensor * 17U) + (sample * 5U) + 11U;
        }
        s_filtered_sensor[sensor] = 0U;
    }
    s_nested_loop_sink = 0U;
}

void NestedLoopAutomotive_SensorMatrixTask_10ms(void)
{
    uint32_t sensor;
    uint32_t sample;
    uint32_t checksum = 0U;
    for (sensor = 0U; sensor < STAR_SENSOR_COUNT; ++sensor)
    {
        uint32_t sum = 0U;
        for (sample = 0U; sample < STAR_SAMPLE_COUNT; ++sample)
        {
            sum += s_sensor_samples[sensor][sample];
        }
        s_filtered_sensor[sensor] = sum >> 2U;
        checksum ^= s_filtered_sensor[sensor];
    }
    s_nested_loop_sink = checksum;
}
