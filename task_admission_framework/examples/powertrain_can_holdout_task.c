/**
 * @file powertrain_can_holdout_task.c
 * @brief Independent bounded Powertrain communication and CAN holdout task.
 */
#include "powertrain_can_holdout_task.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT32_TYPE__ uint32_t;

#define STAR_HOLDOUT_SIGNAL_COUNT (12U)
#define STAR_HOLDOUT_PAYLOAD_SIZE (8U)

extern void CAN_Send(uint32_t identifier, const void *payload, uint8_t length);

static uint32_t g_star_holdout_signals[STAR_HOLDOUT_SIGNAL_COUNT];
static uint8_t g_star_holdout_payload[STAR_HOLDOUT_PAYLOAD_SIZE];
static volatile uint32_t g_star_holdout_network_state;

void StarPowertrainCanHoldout_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < 12U; ++index)
    {
        g_star_holdout_signals[index] = (index * 173U) ^ 0x35U;
    }
    for (index = 0U; index < 8U; ++index)
    {
        g_star_holdout_payload[index] = 0U;
    }
    g_star_holdout_network_state = 0U;
}

void StarTask_PowertrainCanHoldout_100ms(void)
{
    uint32_t index;
    uint32_t checksum = 0xA5U;
    uint32_t network_state = g_star_holdout_network_state;

    for (index = 0U; index < 8U; ++index)
    {
        const uint32_t signal = g_star_holdout_signals[index + 2U];
        g_star_holdout_payload[index] =
            (uint8_t)((signal ^ (signal >> 8U)) & 0xFFU);
    }
    for (index = 0U; index < 16U; ++index)
    {
        checksum ^= (uint32_t)g_star_holdout_payload[index & 7U];
        checksum = (checksum << 1U) | (checksum >> 31U);
    }
    for (index = 0U; index < 12U; ++index)
    {
        switch (index & 3U)
        {
            case 0U: network_state += checksum & 3U; break;
            case 1U: network_state ^= checksum; break;
            case 2U: network_state |= 0x10U; break;
            default: network_state &= 0xFFFFFFEFU; break;
        }
    }
    g_star_holdout_payload[7U] ^= (uint8_t)checksum;
    g_star_holdout_network_state = network_state;
    CAN_Send(0x521U, g_star_holdout_payload, (uint8_t)STAR_HOLDOUT_PAYLOAD_SIZE);
}
