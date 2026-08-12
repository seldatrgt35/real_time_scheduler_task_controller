/**
 * @file powertrain_full_stack_demo.c
 * @brief Bounded automotive Powertrain task set for the STAR demonstration.
 *
 * The code models common ECU runnables without dynamic allocation or
 * recursion. All loops have compile-time bounds and state is represented by
 * fixed-width objects. The integration APIs represent real ADC, GPIO and CAN
 * drivers; their peripheral latency is reported separately from task CPU time.
 * Formal MISRA C compliance requires project-specific tool qualification and
 * an approved deviation record.
 */
#include "powertrain_full_stack_demo.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;
typedef __INT64_TYPE__ int64_t;

#define STAR_SENSOR_COUNT       (16U)
#define STAR_MAP_SEGMENTS       (16U)
#define STAR_CAN_PAYLOAD_SIZE   (8U)
#define STAR_TORQUE_MAX_NM_Q8   (896000)

extern uint16_t ADC_Read(uint8_t channel);
extern void CAN_Send(uint32_t identifier, const void *payload, uint8_t length);

static uint16_t g_star_adc[STAR_SENSOR_COUNT];
static int32_t g_star_filter_state[STAR_SENSOR_COUNT];
static int32_t g_star_pedal_map[STAR_MAP_SEGMENTS + 1U];
static int32_t g_star_torque_map[STAR_MAP_SEGMENTS + 1U];
static uint8_t g_star_can_payload[STAR_CAN_PAYLOAD_SIZE];
static uint8_t g_star_dtc_debounce[8U];

static volatile int32_t g_star_requested_torque_q8;
static volatile int32_t g_star_engine_speed_rpm;
static volatile int32_t g_star_limited_torque_q8;
static volatile uint32_t g_star_dtc_mask;
static volatile uint32_t g_star_alive_counter;
static volatile uint32_t g_star_actuator_enable;

static int32_t StarInterpolateQ8(const int32_t *table,
                                uint32_t segment,
                                uint32_t fraction_q8)
{
    const int32_t lower = table[segment];
    const int32_t upper = table[segment + 1U];
    const int64_t delta =
        (int64_t)(upper - lower) * (int64_t)fraction_q8;
    return lower + (int32_t)(delta / 256);
}

static uint8_t StarCrc8(const uint8_t *data, uint32_t length)
{
    uint32_t byte_index;
    uint8_t crc = 0xFFU;

    for (byte_index = 0U; byte_index < length; ++byte_index)
    {
        uint32_t bit_index;
        crc ^= data[byte_index];
        for (bit_index = 0U; bit_index < 8U; ++bit_index)
        {
            if ((crc & 0x80U) != 0U)
            {
                crc = (uint8_t)((crc << 1U) ^ 0x1DU);
            }
            else
            {
                crc = (uint8_t)(crc << 1U);
            }
        }
    }
    return crc;
}

void StarPowertrainDemo_Initialize(void)
{
    uint32_t index;

    for (index = 0U; index < STAR_SENSOR_COUNT; ++index)
    {
        g_star_adc[index] = (uint16_t)(512U + (index * 173U));
        g_star_filter_state[index] = (int32_t)g_star_adc[index] << 8U;
    }
    for (index = 0U; index <= STAR_MAP_SEGMENTS; ++index)
    {
        g_star_pedal_map[index] = (int32_t)(index * 12800U);
        g_star_torque_map[index] = (int32_t)(index * 19200U);
    }
    for (index = 0U; index < STAR_CAN_PAYLOAD_SIZE; ++index)
    {
        g_star_can_payload[index] = 0U;
        g_star_dtc_debounce[index] = 0U;
    }
    g_star_requested_torque_q8 = 0;
    g_star_engine_speed_rpm = 0;
    g_star_limited_torque_q8 = 0;
    g_star_dtc_mask = 0U;
    g_star_alive_counter = 0U;
    g_star_actuator_enable = 0U;
}

void StarIsr_AdcComplete(void)
{
    uint32_t channel;

    /* ADC acquisition is intentionally outside periodic task CPU timing. */
    for (channel = 0U; channel < STAR_SENSOR_COUNT; ++channel)
    {
        g_star_adc[channel] = ADC_Read((uint8_t)channel);
    }
}

void StarTask_PedalAndTorqueControl_5ms(void)
{
    uint32_t index;
    int32_t torque_sum = 0;

    /* Pedal, throttle and crank-related ADC samples. */
    for (index = 0U; index < 4U; ++index)
    {
        const uint16_t sample = g_star_adc[index];
        const uint32_t segment = ((uint32_t)sample >> 8U) & 15U;
        const uint32_t fraction = (uint32_t)sample & 255U;
        g_star_adc[index] = sample;
        torque_sum += StarInterpolateQ8(g_star_pedal_map,
                                        segment, fraction);
    }
    torque_sum /= 4;
    if (torque_sum > STAR_TORQUE_MAX_NM_Q8)
    {
        torque_sum = STAR_TORQUE_MAX_NM_Q8;
    }
    else if (torque_sum < 0)
    {
        torque_sum = 0;
    }
    else
    {
        /* Torque request is inside the calibrated envelope. */
    }
    g_star_requested_torque_q8 = torque_sum;
    g_star_actuator_enable = (uint32_t)(torque_sum != 0);
}

void StarTask_SensorFusionAndSpeed_10ms(void)
{
    uint32_t index;
    int32_t speed_sum = 0;

    /* Bounded first-order filters for wheel and engine-speed channels. */
    for (index = 4U; index < 12U; ++index)
    {
        const int32_t input_q8 = (int32_t)g_star_adc[index] << 8U;
        const int32_t error_q8 = input_q8 - g_star_filter_state[index];
        g_star_filter_state[index] += error_q8 / 8;
        speed_sum += g_star_filter_state[index] >> 8U;
    }
    g_star_engine_speed_rpm = speed_sum / 8;
}

void StarTask_TorqueLimiterAndTraction_20ms(void)
{
    uint32_t index;
    int32_t traction_limit = STAR_TORQUE_MAX_NM_Q8;

    for (index = 0U; index < 8U; ++index)
    {
        const uint32_t segment = ((uint32_t)g_star_adc[index] >> 8U) & 15U;
        const int32_t mapped = StarInterpolateQ8(
            g_star_torque_map, segment,
            (uint32_t)g_star_adc[index] & 255U);
        if (mapped < traction_limit)
        {
            traction_limit = mapped;
        }
    }
    if (g_star_requested_torque_q8 < traction_limit)
    {
        traction_limit = g_star_requested_torque_q8;
    }
    if (g_star_engine_speed_rpm > 6500)
    {
        traction_limit -= traction_limit / 8;
    }
    g_star_limited_torque_q8 = traction_limit;
}

void StarTask_DiagnosticsAndPlausibility_50ms(void)
{
    uint32_t index;
    uint32_t dtc_mask = g_star_dtc_mask;

    for (index = 0U; index < 8U; ++index)
    {
        const uint16_t primary = g_star_adc[index];
        const uint16_t redundant = g_star_adc[index + 8U];
        const uint16_t difference = (primary > redundant)
            ? (uint16_t)(primary - redundant)
            : (uint16_t)(redundant - primary);
        if ((primary < 80U) || (primary > 4015U) || (difference > 900U))
        {
            if (g_star_dtc_debounce[index] < 5U)
            {
                ++g_star_dtc_debounce[index];
            }
        }
        else if (g_star_dtc_debounce[index] > 0U)
        {
            --g_star_dtc_debounce[index];
        }
        else
        {
            /* No debounce state change is required. */
        }
        if (g_star_dtc_debounce[index] >= 3U)
        {
            dtc_mask |= (1UL << index);
        }
    }
    g_star_dtc_mask = dtc_mask;
}

void StarTask_CanObdAndNetworkManagement_100ms(void)
{
    const uint32_t torque = (uint32_t)g_star_limited_torque_q8;
    const uint32_t speed = (uint32_t)g_star_engine_speed_rpm;

    g_star_can_payload[0] = (uint8_t)(torque >> 8U);
    g_star_can_payload[1] = (uint8_t)(torque >> 16U);
    g_star_can_payload[2] = (uint8_t)speed;
    g_star_can_payload[3] = (uint8_t)(speed >> 8U);
    g_star_can_payload[4] = (uint8_t)g_star_dtc_mask;
    g_star_can_payload[5] = (uint8_t)(g_star_dtc_mask >> 8U);
    g_star_can_payload[6] = (uint8_t)g_star_alive_counter;
    g_star_can_payload[7] = StarCrc8(g_star_can_payload, 7U);
    ++g_star_alive_counter;

    /* CPU driver cost is budgeted; bus and ISR latency stay separate. */
    CAN_Send(0x510U, g_star_can_payload,
             (uint8_t)STAR_CAN_PAYLOAD_SIZE);
}
