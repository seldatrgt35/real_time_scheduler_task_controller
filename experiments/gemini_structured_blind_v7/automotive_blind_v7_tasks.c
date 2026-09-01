#include "automotive_blind_v7_tasks.h"

#define SENSOR_COUNT (3U)
#define SAMPLE_COUNT (4U)
#define NETWORK_SIGNAL_COUNT (8U)
#define MOTOR_PHASE_COUNT (3U)

static volatile int16_t s_sensor_samples[SENSOR_COUNT][SAMPLE_COUNT];
static volatile int16_t s_sensor_filtered[SENSOR_COUNT];
static volatile uint8_t s_network_alive[NETWORK_SIGNAL_COUNT];
static volatile uint8_t s_network_previous[NETWORK_SIGNAL_COUNT];
static volatile uint8_t s_network_debounce[NETWORK_SIGNAL_COUNT];
static volatile uint16_t s_phase_current[MOTOR_PHASE_COUNT];
static volatile uint16_t s_phase_temperature[MOTOR_PHASE_COUNT];
static volatile uint16_t s_phase_limit[MOTOR_PHASE_COUNT];
static volatile uint32_t s_blind_v7_sink;

__attribute__((noinline))
static uint16_t AbsDiffS16(int16_t first, int16_t second)
{
    int32_t difference = (int32_t)first - (int32_t)second;
    if (difference < 0)
    {
        difference = -difference;
    }
    return (uint16_t)difference;
}

__attribute__((noinline))
static int16_t ClampS16(int32_t value, int16_t lower, int16_t upper)
{
    int32_t result = value;
    if (result < (int32_t)lower)
    {
        result = lower;
    }
    if (result > (int32_t)upper)
    {
        result = upper;
    }
    return (int16_t)result;
}

__attribute__((noinline))
static uint8_t UpdateAliveDebounce(uint8_t counter, uint8_t changed)
{
    uint8_t result = counter;
    if (changed != 0U)
    {
        result = 0U;
    }
    else if (result < 7U)
    {
        ++result;
    }
    else
    {
        result = 7U;
    }
    return result;
}

__attribute__((noinline))
static uint16_t ThermalLimitU16(uint16_t temperature)
{
    uint16_t limit;
    if (temperature >= 120U)
    {
        limit = 400U;
    }
    else if (temperature > 80U)
    {
        limit = (uint16_t)(2000U - ((temperature - 80U) * 40U));
    }
    else
    {
        limit = 2000U;
    }
    return limit;
}

__attribute__((noinline))
static uint16_t SlewLimitU16(uint16_t previous, uint16_t requested)
{
    uint16_t result = requested;
    if (requested > (uint16_t)(previous + 96U))
    {
        result = (uint16_t)(previous + 96U);
    }
    else if ((uint16_t)(requested + 96U) < previous)
    {
        result = (uint16_t)(previous - 96U);
    }
    else
    {
        /* Requested value is already inside the slew window. */
    }
    return result;
}

void BlindV7_Initialize(uint32_t task_id)
{
    uint32_t index;
    static const int16_t sensor_seed[SENSOR_COUNT][SAMPLE_COUNT] = {
        {101, 108, 96, 104}, {520, 475, 505, 490}, {-40, -25, -55, -30}
    };
    static const uint8_t alive_seed[NETWORK_SIGNAL_COUNT] = {
        4U, 8U, 12U, 16U, 20U, 24U, 28U, 32U
    };
    static const uint8_t previous_seed[NETWORK_SIGNAL_COUNT] = {
        4U, 7U, 12U, 15U, 20U, 23U, 27U, 32U
    };
    static const uint16_t current_seed[MOTOR_PHASE_COUNT] = {1850U, 920U, 2400U};
    static const uint16_t temperature_seed[MOTOR_PHASE_COUNT] = {72U, 96U, 126U};
    (void)task_id;
    for (index = 0U; index < SENSOR_COUNT; ++index)
    {
        uint32_t sample;
        for (sample = 0U; sample < SAMPLE_COUNT; ++sample)
        {
            s_sensor_samples[index][sample] = sensor_seed[index][sample];
        }
        s_sensor_filtered[index] = 0;
    }
    for (index = 0U; index < NETWORK_SIGNAL_COUNT; ++index)
    {
        s_network_alive[index] = alive_seed[index];
        s_network_previous[index] = previous_seed[index];
        s_network_debounce[index] = (uint8_t)(index & 3U);
    }
    for (index = 0U; index < MOTOR_PHASE_COUNT; ++index)
    {
        s_phase_current[index] = current_seed[index];
        s_phase_temperature[index] = temperature_seed[index];
        s_phase_limit[index] = (uint16_t)(1000U + (index * 200U));
    }
    s_blind_v7_sink = 0U;
}

void SensorVoting_Task10ms(void)
{
    uint32_t sensor;
    uint32_t checksum = 0U;
    for (sensor = 0U; sensor < SENSOR_COUNT; ++sensor)
    {
        uint32_t sample;
        int32_t sum = 0;
        uint16_t spread = 0U;
        for (sample = 0U; sample < SAMPLE_COUNT; ++sample)
        {
            const int16_t value = s_sensor_samples[sensor][sample];
            sum += value;
            if (sample > 0U)
            {
                spread += AbsDiffS16(value, s_sensor_samples[sensor][sample - 1U]);
            }
        }
        s_sensor_filtered[sensor] = ClampS16(sum >> 2, -1000, 1000);
        checksum += ((uint32_t)(uint16_t)s_sensor_filtered[sensor] << 1U) ^ spread;
    }
    s_blind_v7_sink = checksum;
}

void NetworkDebounce_Task5ms(void)
{
    uint32_t signal;
    uint32_t status = 0U;
    for (signal = 0U; signal < NETWORK_SIGNAL_COUNT; ++signal)
    {
        const uint8_t current = s_network_alive[signal];
        const uint8_t changed = (current != s_network_previous[signal]) ? 1U : 0U;
        const uint8_t counter = UpdateAliveDebounce(
            s_network_debounce[signal], changed);
        s_network_debounce[signal] = counter;
        s_network_previous[signal] = current;
        if (counter >= 5U)
        {
            status |= 1UL << signal;
        }
        else
        {
            status ^= ((uint32_t)current << (signal & 7U));
        }
    }
    s_blind_v7_sink = status;
}

void MotorThermalProtection_Task20ms(void)
{
    uint32_t phase;
    uint32_t checksum = 0U;
    for (phase = 0U; phase < MOTOR_PHASE_COUNT; ++phase)
    {
        const uint16_t thermal_limit = ThermalLimitU16(s_phase_temperature[phase]);
        uint16_t requested = s_phase_current[phase];
        if (requested > thermal_limit)
        {
            requested = thermal_limit;
        }
        s_phase_limit[phase] = SlewLimitU16(s_phase_limit[phase], requested);
        checksum += ((uint32_t)s_phase_limit[phase] * (phase + 3U)) >> 1U;
    }
    s_blind_v7_sink = checksum;
}
