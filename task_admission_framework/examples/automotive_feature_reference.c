/*
 * Automotive scheduler-task reference for STAR structural coverage tests.
 *
 * Design constraints:
 * - no dynamic allocation, recursion, blocking or unbounded loops;
 * - fixed-width storage and explicit integer conversions;
 * - deterministic table sizes and scheduler entry points;
 * - initialization is separated from timed task execution.
 *
 * The module is MISRA-oriented example code, not a formal MISRA compliance
 * claim. A production project still requires its configured static checker,
 * deviation process, compiler qualification and integration review.
 */
#include "automotive_feature_reference.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT16_TYPE__ int16_t;
typedef __INT32_TYPE__ int32_t;
typedef __INT64_TYPE__ int64_t;

#define APP_SENSOR_COUNT       (32U)
#define APP_FILTER_COUNT       (16U)
#define APP_TORQUE_MAP_POINTS  (17U)
#define APP_CAN_PAYLOAD_SIZE   (8U)
#define APP_DTC_COUNT          (8U)
#define APP_Q15_ONE            (32768L)

typedef enum
{
    DIAG_STATE_INIT = 0,
    DIAG_STATE_MONITOR,
    DIAG_STATE_CONFIRMED,
    DIAG_STATE_RECOVERY
} DiagState;

typedef uint32_t (*SignalTransform)(uint32_t value, uint8_t sample);

static uint16_t g_adc_samples[APP_SENSOR_COUNT];
static int16_t g_filter_input[APP_FILTER_COUNT];
static int16_t g_filter_output[APP_FILTER_COUNT];
static int32_t g_torque_axis[APP_TORQUE_MAP_POINTS];
static uint8_t g_can_payload[APP_CAN_PAYLOAD_SIZE];
static uint8_t g_dtc_debounce[APP_DTC_COUNT];
static DiagState g_diag_state;
static volatile uint32_t g_control_status;
static volatile int32_t g_requested_torque;
static volatile uint32_t g_network_status;

static uint32_t TransformXor(uint32_t value, uint8_t sample)
{
    return value ^ (uint32_t)sample;
}

static uint32_t TransformRotate(uint32_t value, uint8_t sample)
{
    return (value << 1U) | (value >> 31U) | (uint32_t)sample;
}

static const SignalTransform g_signal_transforms[2U] =
{
    TransformXor,
    TransformRotate
};

static uint8_t CalculatePayloadChecksum(const uint8_t * const data,
                                        uint32_t length)
{
    uint32_t index;
    uint8_t checksum = 0U;

    for (index = 0U; index < length; ++index)
    {
        checksum = (uint8_t)(checksum ^ data[index]);
    }
    return checksum;
}

static int32_t InterpolateTorque(int32_t lower,
                                 int32_t upper,
                                 uint32_t fraction_q8)
{
    const int64_t delta = (int64_t)(upper - lower) * (int64_t)fraction_q8;
    return lower + (int32_t)(delta / 256L);
}

void AutomotiveFeatureReference_Initialize(void)
{
    uint32_t index;

    for (index = 0U; index < APP_SENSOR_COUNT; ++index)
    {
        g_adc_samples[index] = (uint16_t)((index * 73U) & 4095U);
    }
    for (index = 0U; index < APP_FILTER_COUNT; ++index)
    {
        g_filter_input[index] = (int16_t)((int32_t)(index * 31U) - 200L);
        g_filter_output[index] = 0;
    }
    for (index = 0U; index < APP_TORQUE_MAP_POINTS; ++index)
    {
        g_torque_axis[index] = (int32_t)(index * 250U);
    }
    for (index = 0U; index < APP_DTC_COUNT; ++index)
    {
        g_dtc_debounce[index] = 0U;
    }
    for (index = 0U; index < APP_CAN_PAYLOAD_SIZE; ++index)
    {
        g_can_payload[index] = 0U;
    }
    g_diag_state = DIAG_STATE_INIT;
    g_control_status = 0U;
    g_requested_torque = 0;
    g_network_status = 0U;
}

void AppTask_PowertrainInput_5ms(void)
{
    uint32_t index;
    uint32_t sensor_sum = 0U;
    uint32_t plausibility_flags = 0U;

    /* Bounded ADC sample processing and pedal-sensor plausibility checks. */
    for (index = 0U; index < 16U; ++index)
    {
        const uint32_t sample = (uint32_t)g_adc_samples[index];
        sensor_sum += sample;
        if (sample > 3900U)
        {
            plausibility_flags |= (1UL << (index & 7U));
        }
        else
        {
            plausibility_flags &= ~(1UL << (index & 7U));
        }
    }
    g_control_status = sensor_sum ^ plausibility_flags;
}

void AppTask_SignalConditioning_10ms(void)
{
    uint32_t index;
    const int32_t coefficient_q15 = 8192L;

    /* Copy the acquisition window and apply a bounded Q15 low-pass stage. */
    for (index = 0U; index < APP_FILTER_COUNT; ++index)
    {
        const int32_t input = (int32_t)g_filter_input[index];
        const int32_t previous = (int32_t)g_filter_output[index];
        const int32_t correction =
            (int32_t)(((int64_t)(input - previous) * coefficient_q15)
                      / APP_Q15_ONE);
        g_filter_output[index] = (int16_t)(previous + correction);
    }
}

void AppTask_TorqueCoordination_20ms(void)
{
    uint32_t index;
    int32_t torque_sum = 0;

    /* Calibration-table lookup, linear interpolation and actuator saturation. */
    for (index = 0U; index < 16U; ++index)
    {
        const uint32_t map_index = (index * 5U) & 15U;
        const uint32_t fraction_q8 = (index * 37U) & 255U;
        int32_t torque = InterpolateTorque(g_torque_axis[map_index],
                                           g_torque_axis[map_index + 1U],
                                           fraction_q8);
        if (torque > 3500L)
        {
            torque = 3500L;
        }
        else if (torque < 0L)
        {
            torque = 0L;
        }
        else
        {
            /* Torque is already inside the permitted actuator range. */
        }
        torque_sum += torque;
    }
    g_requested_torque = torque_sum;
}

void AppTask_Diagnostics_50ms(void)
{
    uint32_t index;
    uint32_t confirmed_faults = 0U;

    /* Debounce eight diagnostic monitors using a bounded state update. */
    for (index = 0U; index < APP_DTC_COUNT; ++index)
    {
        const uint32_t failed = (g_control_status >> index) & 1U;
        if (failed != 0U)
        {
            if (g_dtc_debounce[index] < 5U)
            {
                ++g_dtc_debounce[index];
            }
        }
        else if (g_dtc_debounce[index] > 0U)
        {
            --g_dtc_debounce[index];
        }
        else
        {
            /* Debounce counter remains at zero. */
        }
        if (g_dtc_debounce[index] >= 3U)
        {
            confirmed_faults |= (1UL << index);
        }
    }

    /* Explicit diagnostic state machine; every invocation executes one state. */
    switch (g_diag_state)
    {
        case DIAG_STATE_INIT:
            g_diag_state = DIAG_STATE_MONITOR;
            break;
        case DIAG_STATE_MONITOR:
            g_diag_state = (confirmed_faults != 0U)
                ? DIAG_STATE_CONFIRMED : DIAG_STATE_MONITOR;
            break;
        case DIAG_STATE_CONFIRMED:
            g_diag_state = (confirmed_faults == 0U)
                ? DIAG_STATE_RECOVERY : DIAG_STATE_CONFIRMED;
            break;
        default:
            g_diag_state = DIAG_STATE_MONITOR;
            break;
    }
    g_network_status = confirmed_faults;
}

void AppTask_NetworkManagement_100ms(void)
{
    uint32_t index;
    uint32_t transformed = (uint32_t)g_requested_torque;

    /* Pack a deterministic eight-byte powertrain status frame. */
    for (index = 0U; index < (APP_CAN_PAYLOAD_SIZE - 1U); ++index)
    {
        const uint32_t shift = (index & 3U) * 8U;
        g_can_payload[index] = (uint8_t)(transformed >> shift);
        transformed = g_signal_transforms[index & 1U](
            transformed, g_can_payload[index]);
    }
    g_can_payload[APP_CAN_PAYLOAD_SIZE - 1U] =
        CalculatePayloadChecksum(g_can_payload, APP_CAN_PAYLOAD_SIZE - 1U);
    g_network_status ^= transformed;
}
