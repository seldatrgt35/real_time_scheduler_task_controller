#include "manual_automotive_task.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;

#define ACTUATOR_COUNT (4U)

static volatile uint16_t s_requested_command[ACTUATOR_COUNT];
static volatile uint16_t s_previous_command[ACTUATOR_COUNT];
static volatile uint16_t s_feedback_value[ACTUATOR_COUNT];
static volatile uint8_t s_fault_counter[ACTUATOR_COUNT];
static volatile uint16_t s_output_command[ACTUATOR_COUNT];
static volatile uint32_t s_manual_sink;

__attribute__((noinline))
static uint16_t ClampCommandU16(uint16_t value,
                               uint16_t lower_limit,
                               uint16_t upper_limit)
{
    uint16_t result = value;
    if (result < lower_limit)
    {
        result = lower_limit;
    }
    if (result > upper_limit)
    {
        result = upper_limit;
    }
    return result;
}

__attribute__((noinline))
static uint16_t RateLimitU16(uint16_t previous,
                            uint16_t requested,
                            uint16_t maximum_step)
{
    uint16_t result;
    if (requested > previous)
    {
        const uint16_t difference = (uint16_t)(requested - previous);
        result = (difference > maximum_step)
            ? (uint16_t)(previous + maximum_step)
            : requested;
    }
    else
    {
        const uint16_t difference = (uint16_t)(previous - requested);
        result = (difference > maximum_step)
            ? (uint16_t)(previous - maximum_step)
            : requested;
    }
    return result;
}

__attribute__((noinline))
static uint8_t UpdateDebounceU8(uint8_t counter, uint8_t active)
{
    uint8_t result = counter;
    if (active != 0U)
    {
        if (result < 5U)
        {
            ++result;
        }
    }
    else if (result > 0U)
    {
        --result;
    }
    else
    {
        /* The counter remains at zero. */
    }
    return result;
}

void ManualAutomotive_Initialize(void)
{
    s_requested_command[0] = 900U;
    s_requested_command[1] = 1800U;
    s_requested_command[2] = 2600U;
    s_requested_command[3] = 4200U;
    s_previous_command[0] = 850U;
    s_previous_command[1] = 1700U;
    s_previous_command[2] = 2500U;
    s_previous_command[3] = 3400U;
    s_feedback_value[0] = 10U;
    s_feedback_value[1] = 25U;
    s_feedback_value[2] = 70U;
    s_feedback_value[3] = 80U;
    s_fault_counter[0] = 0U;
    s_fault_counter[1] = 1U;
    s_fault_counter[2] = 3U;
    s_fault_counter[3] = 4U;
    s_output_command[0] = 0U;
    s_output_command[1] = 0U;
    s_output_command[2] = 0U;
    s_output_command[3] = 0U;
    s_manual_sink = 0U;
}

void ThrottleActuatorMonitor_Task5ms(void)
{
    uint32_t channel;
    uint32_t checksum = 0U;
    for (channel = 0U; channel < ACTUATOR_COUNT; ++channel)
    {
        const uint16_t clamped = ClampCommandU16(
            s_requested_command[channel], 500U, 3500U);
        const uint16_t limited = RateLimitU16(
            s_previous_command[channel], clamped, 120U);
        const uint8_t fault_active =
            (s_feedback_value[channel] > 60U) ? 1U : 0U;
        const uint8_t counter = UpdateDebounceU8(
            s_fault_counter[channel], fault_active);
        s_fault_counter[channel] = counter;
        s_output_command[channel] = limited;
        checksum += ((uint32_t)limited << 1U) ^ (uint32_t)counter;
    }
    s_manual_sink = checksum;
}
