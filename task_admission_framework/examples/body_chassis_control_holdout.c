/*
 * Independent body/chassis ECU holdout for STAR execution-time validation.
 *
 * This module models scheduler-runnable application software. Hardware access
 * is represented by previously acquired input images and an output image;
 * driver, peripheral and network transmission latency are intentionally kept
 * outside the CPU task model.
 *
 * Safety-oriented design rules:
 * - fixed-width data and explicit conversions;
 * - static allocation only;
 * - no recursion, blocking calls or data-dependent loops;
 * - bounded table access and explicit saturation;
 * - initialization is not included in timed scheduler entry points.
 *
 * This is MISRA-oriented reference code, not a formal compliance certificate.
 */
#include "body_chassis_control_holdout.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT16_TYPE__ int16_t;
typedef __INT32_TYPE__ int32_t;

#define BCC_WHEEL_COUNT       (4U)
#define BCC_SAMPLE_COUNT      (24U)
#define BCC_THERMAL_COUNT     (12U)
#define BCC_FAULT_COUNT       (8U)
#define BCC_STATUS_BYTES      (8U)
#define BCC_SIGNAL_COUNT      (24U)

typedef enum
{
    BCC_FAULT_INIT = 0,
    BCC_FAULT_MONITOR,
    BCC_FAULT_LATCHED,
    BCC_FAULT_RECOVERY
} BccFaultState;

typedef uint32_t (*BccStatusEncoder)(uint32_t state, uint8_t input);

static uint16_t g_wheel_capture[BCC_SAMPLE_COUNT];
static int16_t g_temperature_input[BCC_THERMAL_COUNT];
static int16_t g_actuator_output[BCC_THERMAL_COUNT];
static uint8_t g_fault_counter[BCC_FAULT_COUNT];
static uint8_t g_status_frame[BCC_STATUS_BYTES];
static uint8_t g_status_signal[BCC_SIGNAL_COUNT];
static BccFaultState g_fault_state;
static volatile uint32_t g_brake_request;
static volatile int32_t g_stability_request;
static volatile uint32_t g_fault_bits;
static volatile uint32_t g_transmit_request;

static uint32_t EncodeStatusXor(uint32_t state, uint8_t input)
{
    return state ^ (uint32_t)input;
}

static uint32_t EncodeStatusRotate(uint32_t state, uint8_t input)
{
    return (state << 1U) | (state >> 31U) | (uint32_t)input;
}

static const BccStatusEncoder g_status_encoders[2U] =
{
    EncodeStatusXor,
    EncodeStatusRotate
};

static int32_t ApplyActuatorGain(int32_t error, int32_t gain_q8)
{
    return (error * gain_q8) / 256L;
}

static uint8_t CalculateStatusChecksum(const uint8_t * const payload,
                                       uint32_t length)
{
    uint32_t index;
    uint8_t checksum = 0U;

    for (index = 0U; index < length; ++index)
    {
        checksum = (uint8_t)(checksum ^ payload[index]);
    }
    return checksum;
}

void BodyChassisControl_Initialize(void)
{
    uint32_t index;

    for (index = 0U; index < BCC_SAMPLE_COUNT; ++index)
    {
        g_wheel_capture[index] = (uint16_t)(900U + (index * 17U));
    }
    for (index = 0U; index < BCC_THERMAL_COUNT; ++index)
    {
        g_temperature_input[index] = (int16_t)(20 + (int32_t)index);
        g_actuator_output[index] = 0;
    }
    for (index = 0U; index < BCC_FAULT_COUNT; ++index)
    {
        g_fault_counter[index] = 0U;
    }
    for (index = 0U; index < BCC_STATUS_BYTES; ++index)
    {
        g_status_frame[index] = 0U;
    }
    for (index = 0U; index < BCC_SIGNAL_COUNT; ++index)
    {
        g_status_signal[index] = (uint8_t)((index * 13U) + 5U);
    }
    g_fault_state = BCC_FAULT_INIT;
    g_brake_request = 0U;
    g_stability_request = 0;
    g_fault_bits = 0U;
    g_transmit_request = 0U;
}

void BccTask_WheelSpeedAndBrake_5ms(void)
{
    uint32_t index;
    uint32_t accumulated_speed = 0U;
    uint32_t slip_flags = 0U;

    for (index = 0U; index < BCC_SAMPLE_COUNT; ++index)
    {
        const uint32_t wheel = index & (BCC_WHEEL_COUNT - 1U);
        const uint32_t speed = (uint32_t)g_wheel_capture[index];
        accumulated_speed += speed;
        if (speed > (1100U + (wheel * 20U)))
        {
            slip_flags |= (1UL << wheel);
        }
        else
        {
            slip_flags &= ~(1UL << wheel);
        }
    }
    g_brake_request = accumulated_speed ^ slip_flags;
}

void BccTask_ThermalActuator_10ms(void)
{
    uint32_t index;
    int32_t total_output = 0;

    for (index = 0U; index < BCC_THERMAL_COUNT; ++index)
    {
        const int32_t measured = (int32_t)g_temperature_input[index];
        const int32_t error = 85L - measured;
        int32_t command = ApplyActuatorGain(error, 96L);

        if (command > 100L)
        {
            command = 100L;
        }
        else if (command < 0L)
        {
            command = 0L;
        }
        else
        {
            /* Command is inside the valid actuator range. */
        }
        g_actuator_output[index] = (int16_t)command;
        total_output += command;
    }
    g_stability_request = total_output;
}

void BccTask_StabilityRequest_20ms(void)
{
    uint32_t index;
    int32_t request = g_stability_request;

    for (index = 0U; index < 20U; ++index)
    {
        const int32_t correction =
            ApplyActuatorGain((int32_t)g_wheel_capture[index] - 1000L, 64L);
        request += correction;
        if (request > 2500L)
        {
            request = 2500L;
        }
        else if (request < -2500L)
        {
            request = -2500L;
        }
        else
        {
            /* Stability correction remains within the permitted envelope. */
        }
    }
    g_stability_request = request;
}

void BccTask_FaultManager_50ms(void)
{
    uint32_t index;
    uint32_t active_faults = 0U;

    for (index = 0U; index < BCC_FAULT_COUNT; ++index)
    {
        const uint32_t failed = (g_brake_request >> index) & 1U;
        if (failed != 0U)
        {
            if (g_fault_counter[index] < 6U)
            {
                ++g_fault_counter[index];
            }
        }
        else if (g_fault_counter[index] > 0U)
        {
            --g_fault_counter[index];
        }
        else
        {
            /* Counter remains at its lower bound. */
        }
        if (g_fault_counter[index] >= 4U)
        {
            active_faults |= (1UL << index);
        }
    }

    switch (g_fault_state)
    {
        case BCC_FAULT_INIT:
            g_fault_state = BCC_FAULT_MONITOR;
            break;
        case BCC_FAULT_MONITOR:
            g_fault_state = (active_faults != 0U)
                ? BCC_FAULT_LATCHED : BCC_FAULT_MONITOR;
            break;
        case BCC_FAULT_LATCHED:
            g_fault_state = (active_faults == 0U)
                ? BCC_FAULT_RECOVERY : BCC_FAULT_LATCHED;
            break;
        default:
            g_fault_state = BCC_FAULT_MONITOR;
            break;
    }
    g_fault_bits = active_faults;
}

void BccTask_StatusCommunication_100ms(void)
{
    uint32_t index;
    uint32_t encoded = g_brake_request ^ (uint32_t)g_stability_request;

    /* Encode the bounded application-signal image before frame packing. */
    for (index = 0U; index < BCC_SIGNAL_COUNT; ++index)
    {
        encoded = g_status_encoders[index & 1U](encoded,
                                                 g_status_signal[index]);
    }

    /* Classical CAN frame layout is intentionally explicit and reviewable. */
    g_status_frame[0U] = (uint8_t)encoded;
    g_status_frame[1U] = (uint8_t)(encoded >> 8U);
    g_status_frame[2U] = (uint8_t)(encoded >> 16U);
    g_status_frame[3U] = (uint8_t)(encoded >> 24U);
    g_status_frame[4U] = (uint8_t)g_fault_bits;
    g_status_frame[5U] = (uint8_t)(g_fault_bits >> 8U);
    g_status_frame[6U] = (uint8_t)g_fault_state;
    g_status_frame[BCC_STATUS_BYTES - 1U] =
        CalculateStatusChecksum(g_status_frame, BCC_STATUS_BYTES - 1U);
    g_transmit_request = encoded ^ g_fault_bits;
}
