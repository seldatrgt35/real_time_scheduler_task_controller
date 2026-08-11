#include "powertrain_diagnostics_communication_tasks.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT32_TYPE__ uint32_t;

#define STAR_DIAGNOSTIC_SAMPLE_COUNT (64U)
#define STAR_CAN_PAYLOAD_LENGTH       (8U)

extern void CAN_Send(uint32_t identifier, const void *payload, uint8_t length);

static uint32_t g_star_diagnostic_samples[STAR_DIAGNOSTIC_SAMPLE_COUNT];
static uint32_t g_star_network_signals[STAR_CAN_PAYLOAD_LENGTH];
static uint8_t g_star_can_payload[STAR_CAN_PAYLOAD_LENGTH];
static volatile uint32_t g_star_diagnostic_state;
static volatile uint32_t g_star_network_state;

static uint32_t StarDiagnosticDebounce(uint32_t value)
{
    return value + 3U;
}

void StarPowertrainCommunication_Initialize(void)
{
    uint32_t index;

    for (index = 0U; index < STAR_DIAGNOSTIC_SAMPLE_COUNT; ++index)
    {
        g_star_diagnostic_samples[index] = (index * 17U) ^ 0x5AU;
    }
    for (index = 0U; index < 8U; ++index)
    {
        g_star_network_signals[index] = (index * 211U) + 19U;
        g_star_can_payload[index] = 0U;
    }
    g_star_diagnostic_state = 0U;
    g_star_network_state = 0U;
}

void PowertrainDiagnosticsTask_50ms(void)
{
    uint32_t index;
    uint32_t checksum = 0U;
    uint32_t dtc_state = 0U;

    /* Check bounded diagnostic samples for data corruption. */
    for (index = 0U; index < 48U; ++index)
    {
        checksum ^= g_star_diagnostic_samples[index] & 0xFFU;
    }

    /* Execute the bounded DTC state machine. */
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

    /* Apply a bounded debounce transform to diagnostic counters. */
    for (index = 0U; index < 16U; ++index)
    {
        dtc_state = StarDiagnosticDebounce(dtc_state);
    }
    g_star_diagnostic_state = dtc_state ^ checksum;
}

void PowertrainCommunicationCpuTask_100ms(void)
{
    uint32_t index;
    uint32_t checksum = 0U;
    uint32_t network_state = g_star_network_state;

    /* Pack bounded application signals into one eight-byte CAN payload. */
    for (index = 0U; index < 8U; ++index)
    {
        g_star_can_payload[index] = (uint8_t)(g_star_network_signals[index] & 0xFFU);
    }

    /* Calculate the application checksum; bus transmission is not included. */
    for (index = 0U; index < 8U; ++index)
    {
        checksum ^= (uint32_t)g_star_can_payload[index] & 0xFFU;
    }

    /* Update the bounded network-management state machine. */
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

void PowertrainCanTransmitTask_100ms(void)
{
    PowertrainCommunicationCpuTask_100ms();
    CAN_Send(0x510U, g_star_can_payload, (uint8_t)STAR_CAN_PAYLOAD_LENGTH);
}
