/**
 * @file powertrain_reference_application.c
 * @brief Deterministic Powertrain CPU workload for STAR admission analysis.
 *
 * The module is MISRA-C-oriented demonstration code. It uses fixed-width
 * types, bounded loops, explicit conversions, deterministic state and no
 * dynamic allocation. Formal MISRA compliance still requires an approved
 * static-analysis tool and a project-specific deviation record.
 *
 * ADC acquisition and CAN transmission are integration boundaries and are
 * deliberately excluded from the verified CPU timing model.
 */
#include "powertrain_reference_application.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;
typedef __INT64_TYPE__ int64_t;

#define STAR_SENSOR_COUNT       (64U)
#define STAR_MAP_SIZE           (16U)
#define STAR_CAN_PAYLOAD_LENGTH (8U)

static int32_t g_star_sensor_samples[STAR_SENSOR_COUNT];
static int32_t g_star_pedal_map[STAR_MAP_SIZE + 1U];
static int32_t g_star_torque_map[STAR_MAP_SIZE + 1U];
static uint32_t g_star_diagnostic_samples[STAR_SENSOR_COUNT];
static uint32_t g_star_network_signals[STAR_CAN_PAYLOAD_LENGTH];
static uint8_t g_star_can_payload[STAR_CAN_PAYLOAD_LENGTH];

static volatile int32_t g_star_requested_torque;
static volatile int32_t g_star_filtered_speed;
static volatile int32_t g_star_safe_torque;
static volatile uint32_t g_star_diagnostic_state;
static volatile uint32_t g_star_network_state;

static uint32_t StarDiagnosticDebounce(uint32_t value)
{
    return value + 3U;
}

void StarPowertrainReference_Initialize(void)
{
    uint32_t index;

    for (index = 0U; index < STAR_SENSOR_COUNT; ++index)
    {
        g_star_sensor_samples[index] =
            (int32_t)((index * 47U) & 1023U) - 256;
        g_star_diagnostic_samples[index] = (index * 17U) ^ 0x5AU;
    }
    for (index = 0U; index <= STAR_MAP_SIZE; ++index)
    {
        g_star_pedal_map[index] = (int32_t)(index * 180U);
        g_star_torque_map[index] = (int32_t)(index * 220U) - 400;
    }
    for (index = 0U; index < STAR_CAN_PAYLOAD_LENGTH; ++index)
    {
        g_star_network_signals[index] = (index * 211U) + 19U;
        g_star_can_payload[index] = 0U;
    }
    g_star_requested_torque = 0;
    g_star_filtered_speed = 0;
    g_star_safe_torque = 0;
    g_star_diagnostic_state = 0U;
    g_star_network_state = 0U;
}

void StarTask_PowertrainFastControl_5ms(void)
{
    uint32_t index;
    int32_t sensor_sum = 0;
    int32_t requested_torque = 0;

    /* Combine bounded pedal and engine-speed samples. */
    for (index = 0U; index < 32U; ++index)
    {
        const int32_t sample = g_star_sensor_samples[index];
        sensor_sum += sample;
        sensor_sum -= sample / 4;
        sensor_sum += sample * 3;
    }
    /* Interpolate the driver torque request from a calibration map. */
    for (index = 0U; index < 24U; ++index)
    {
        const uint32_t map_index = (index * 5U) & 15U;
        const int32_t lower = g_star_pedal_map[map_index];
        const int32_t upper = g_star_pedal_map[map_index + 1U];
        const int32_t fraction_q8 = (int32_t)((index * 37U) & 255U);
        const int64_t delta =
            (int64_t)(upper - lower) * (int64_t)fraction_q8;
        requested_torque += lower + (int32_t)(delta / 256);
    }
    /* Apply the actuator torque envelope. */
    for (index = 0U; index < 32U; ++index)
    {
        int32_t value = (sensor_sum / 64) + (requested_torque / 128);
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
            /* The request is already inside the permitted range. */
        }
        requested_torque += value;
    }
    g_star_requested_torque = requested_torque;
}

void StarTask_PowertrainSensorProcessing_10ms(void)
{
    uint32_t index;
    int32_t filtered_speed = 0;
    int32_t converted_speed = 0;

    for (index = 0U; index < 24U; ++index)
    {
        const int32_t sample = g_star_sensor_samples[index + 16U];
        filtered_speed += sample;
        filtered_speed -= sample / 4;
        filtered_speed += sample * 3;
    }
    for (index = 0U; index < 32U; ++index)
    {
        const uint32_t map_index = (index * 7U) & 15U;
        const int32_t lower = g_star_torque_map[map_index];
        const int32_t upper = g_star_torque_map[map_index + 1U];
        const int32_t fraction_q8 = (int32_t)((index * 29U) & 255U);
        const int64_t delta =
            (int64_t)(upper - lower) * (int64_t)fraction_q8;
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
            /* The converted speed is plausible. */
        }
        converted_speed += value;
    }
    g_star_filtered_speed = converted_speed;
}

void StarTask_PowertrainTorqueSafety_20ms(void)
{
    uint32_t index;
    int32_t torque_limit = 0;
    int32_t traction_limit = 0;

    for (index = 0U; index < 32U; ++index)
    {
        const uint32_t map_index = (index * 3U) & 15U;
        torque_limit += g_star_torque_map[map_index];
    }
    for (index = 0U; index < 24U; ++index)
    {
        const uint32_t map_index = (index * 11U) & 15U;
        const int32_t lower = g_star_torque_map[map_index];
        const int32_t upper = g_star_torque_map[map_index + 1U];
        const int32_t fraction_q8 = (int32_t)((index * 41U) & 255U);
        const int64_t delta =
            (int64_t)(upper - lower) * (int64_t)fraction_q8;
        traction_limit += lower + (int32_t)(delta / 256);
    }
    for (index = 0U; index < 48U; ++index)
    {
        int32_t value =
            (g_star_requested_torque / 64) - (traction_limit / 128);
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
            /* No additional traction reduction is required. */
        }
        torque_limit += value;
    }
    g_star_safe_torque = torque_limit;
}

void StarTask_PowertrainDiagnostics_50ms(void)
{
    uint32_t index;
    uint32_t checksum = 0U;
    uint32_t dtc_state = 0U;

    for (index = 0U; index < 48U; ++index)
    {
        checksum ^= g_star_diagnostic_samples[index] & 0xFFU;
    }
    for (index = 0U; index < 24U; ++index)
    {
        switch (index & 3U)
        {
            case 0U: dtc_state += 1U; break;
            case 1U: dtc_state ^= 2U; break;
            case 2U: dtc_state |= 4U; break;
            default: dtc_state &= 0xFFFFFFFEU; break;
        }
    }
    for (index = 0U; index < 16U; ++index)
    {
        dtc_state = StarDiagnosticDebounce(dtc_state);
    }
    g_star_diagnostic_state = dtc_state ^ checksum;
}

void StarTask_PowertrainCommunication_100ms(void)
{
    uint32_t index;
    uint32_t checksum = 0U;
    uint32_t network_state = g_star_network_state;

    for (index = 0U; index < 8U; ++index)
    {
        g_star_can_payload[index] =
            (uint8_t)(g_star_network_signals[index] & 0xFFU);
    }
    for (index = 0U; index < 8U; ++index)
    {
        checksum ^= (uint32_t)g_star_can_payload[index] & 0xFFU;
    }
    for (index = 0U; index < 16U; ++index)
    {
        switch (index & 3U)
        {
            case 0U: network_state += 1U; break;
            case 1U: network_state ^= 2U; break;
            case 2U: network_state |= 4U; break;
            default: network_state &= 0xFFFFFFFEU; break;
        }
    }
    g_star_can_payload[7U] ^= (uint8_t)checksum;
    g_star_network_state = network_state;
}
