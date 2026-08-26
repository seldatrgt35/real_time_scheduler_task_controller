/* Blind source-only WCET experiment. Initialization is outside timed scope. */
typedef unsigned int uint32_t;

#define SENSOR_COUNT  (8U)
#define SAMPLE_COUNT  (4U)

static uint32_t sensor_samples[SENSOR_COUNT][SAMPLE_COUNT];
static uint32_t filtered_sensor[SENSOR_COUNT];
static volatile uint32_t task_sink;

void AutomotiveSensorMatrix_Initialize(void)
{
    uint32_t sensor;
    uint32_t sample;
    for (sensor = 0U; sensor < SENSOR_COUNT; ++sensor)
    {
        for (sample = 0U; sample < SAMPLE_COUNT; ++sample)
        {
            sensor_samples[sensor][sample] =
                (sensor * 17U) + (sample * 5U) + 11U;
        }
        filtered_sensor[sensor] = 0U;
    }
    task_sink = 0U;
}

void AutomotiveSensorMatrix_Task10ms(void)
{
    uint32_t sensor;
    uint32_t sample;
    uint32_t checksum = 0U;

    for (sensor = 0U; sensor < SENSOR_COUNT; ++sensor)
    {
        uint32_t sum = 0U;
        for (sample = 0U; sample < SAMPLE_COUNT; ++sample)
        {
            sum += sensor_samples[sensor][sample];
        }
        filtered_sensor[sensor] = sum >> 2U;
        checksum ^= filtered_sensor[sensor];
    }
    task_sink = checksum;
}
