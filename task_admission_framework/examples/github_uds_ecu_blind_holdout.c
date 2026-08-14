/**
 * @file github_uds_ecu_blind_holdout.c
 * @brief Blind UDS/OBD-II ECU scheduler holdout derived from openxc/uds-c.
 *
 * Upstream: https://github.com/openxc/uds-c
 * Pinned commit: e56aeb9c884ccbdbe73e1630942f8c0d17e27498
 * Copyright (c) 2013 Ford Motor Company. BSD-3-Clause licensed.
 *
 * The protocol decisions are adapted from the upstream diagnostic request,
 * positive/negative response and OBD-II PID decoding paths. This wrapper uses
 * fixed storage and bounded loops so each function is suitable as a periodic
 * embedded scheduler runnable. It has not been used to calibrate STAR.
 */
#include "github_uds_ecu_blind_holdout.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;

#define STAR_RX_FRAME_COUNT   (8U)
#define STAR_PAYLOAD_SIZE     (8U)
#define STAR_RESPONSE_OFFSET  (0x40U)
#define STAR_NEGATIVE_MODE    (0x7FU)

extern void CAN_Send(uint32_t identifier, const void *payload, uint8_t length);

typedef struct
{
    uint32_t identifier;
    uint8_t data[STAR_PAYLOAD_SIZE];
    uint8_t size;
} StarCanFrame;

static StarCanFrame g_rx[STAR_RX_FRAME_COUNT];
static uint8_t g_reassembly[32U];
static uint8_t g_tx[STAR_PAYLOAD_SIZE];
static uint8_t g_dtc_debounce[8U];
static volatile uint32_t g_matched_frames;
static volatile uint32_t g_pid_value;
static volatile uint32_t g_response_state;
static volatile uint32_t g_dtc_state;
static volatile uint32_t g_alive;

void StarGithubUds_Initialize(void)
{
    uint32_t frame;
    uint32_t byte;
    for (frame = 0U; frame < 8U; ++frame)
    {
        g_rx[frame].identifier = 0x7E8U + frame;
        g_rx[frame].size = STAR_PAYLOAD_SIZE;
        for (byte = 0U; byte < STAR_PAYLOAD_SIZE; ++byte)
        {
            g_rx[frame].data[byte] =
                (uint8_t)((frame * 29U) + (byte * 17U));
        }
        g_rx[frame].data[1U] = 0x41U;
        g_rx[frame].data[2U] = (uint8_t)(0x0CU + frame);
    }
    for (byte = 0U; byte < 32U; ++byte) { g_reassembly[byte] = 0U; }
    for (byte = 0U; byte < 8U; ++byte)
    {
        g_tx[byte] = 0U;
        g_dtc_debounce[byte] = 0U;
    }
    g_matched_frames = 0U;
    g_pid_value = 0U;
    g_response_state = 0U;
    g_dtc_state = 0U;
    g_alive = 0U;
}

void StarTask_UdsCanRxDispatch_5ms(void)
{
    uint32_t frame;
    uint32_t matches = 0U;
    for (frame = 0U; frame < 8U; ++frame)
    {
        if ((g_rx[frame].identifier >= 0x7E8U) &&
            (g_rx[frame].identifier <= 0x7EFU) &&
            (g_rx[frame].size > 2U))
        {
            const uint32_t destination = frame * 4U;
            g_reassembly[destination] = g_rx[frame].data[1U];
            g_reassembly[destination + 1U] = g_rx[frame].data[2U];
            g_reassembly[destination + 2U] = g_rx[frame].data[3U];
            g_reassembly[destination + 3U] = g_rx[frame].data[4U];
            ++matches;
        }
    }
    g_matched_frames = matches;
}

void StarTask_ObdPidDecode_10ms(void)
{
    uint32_t frame;
    uint32_t decoded = 0U;
    for (frame = 0U; frame < 8U; ++frame)
    {
        const uint8_t pid = g_rx[frame].data[2U];
        const uint32_t a = g_rx[frame].data[3U];
        const uint32_t b = g_rx[frame].data[4U];
        switch (pid)
        {
            case 0x0CU: decoded += ((a * 256U) + b) / 4U; break;
            case 0x0DU: decoded += a; break;
            case 0x10U: decoded += ((a * 256U) + b) / 100U; break;
            case 0x11U: decoded += (a * 100U) / 255U; break;
            case 0x05U: decoded += a - 40U; break;
            default: decoded += (a << 8U) | b; break;
        }
    }
    g_pid_value = decoded;
}

void StarTask_UdsResponseValidation_20ms(void)
{
    uint32_t frame;
    uint32_t state = 0U;
    for (frame = 0U; frame < 8U; ++frame)
    {
        const uint8_t mode = g_rx[frame].data[1U];
        const uint8_t pid = g_rx[frame].data[2U];
        if (mode == STAR_NEGATIVE_MODE)
        {
            state ^= (uint32_t)g_rx[frame].data[3U] << (frame & 7U);
        }
        else if ((mode == (0x01U + STAR_RESPONSE_OFFSET)) &&
                 (pid >= 0x0CU) && (pid <= 0x13U))
        {
            state |= 1UL << frame;
        }
        else
        {
            state += 3U;
        }
    }
    g_response_state = state;
}

void StarTask_DtcAndSessionMaintenance_50ms(void)
{
    uint32_t index;
    uint32_t state = g_dtc_state;
    for (index = 0U; index < 8U; ++index)
    {
        const uint8_t status = g_rx[index].data[3U];
        if ((status & 0x0FU) != 0U)
        {
            if (g_dtc_debounce[index] < 5U) { ++g_dtc_debounce[index]; }
        }
        else if (g_dtc_debounce[index] > 0U)
        {
            --g_dtc_debounce[index];
        }
        else
        {
            /* No diagnostic state transition. */
        }
        if (g_dtc_debounce[index] >= 3U) { state |= 1UL << index; }
    }
    g_dtc_state = state;
}

void StarTask_ObdRequestAndCanTx_100ms(void)
{
    uint32_t index;
    uint8_t checksum = 0U;
    g_tx[0U] = 2U;
    g_tx[1U] = 0x01U;
    g_tx[2U] = (uint8_t)(0x0CU + (g_alive & 3U));
    for (index = 3U; index < 7U; ++index)
    {
        g_tx[index] = (uint8_t)(g_pid_value >> ((index - 3U) * 4U));
    }
    for (index = 0U; index < 7U; ++index)
    {
        checksum ^= g_tx[index];
        checksum = (uint8_t)((checksum << 1U) | (checksum >> 7U));
    }
    g_tx[7U] = checksum;
    ++g_alive;
    CAN_Send(0x7DFU, g_tx, (uint8_t)STAR_PAYLOAD_SIZE);
}

void StarTask_UdsRequestMatchSupported_5ms(void)
{
    uint32_t index;
    uint32_t matches = 0U;
    for (index = 0U; index < 8U; ++index)
    {
        const uint32_t expected_id = 0x7E8U + index;
        if ((g_rx[index].identifier == expected_id) &&
            (g_rx[index].data[1U] == 0x41U))
        {
            ++matches;
        }
    }
    g_matched_frames = matches;
}

void StarTask_UdsPayloadPackSupported_10ms(void)
{
    uint32_t index;
    for (index = 0U; index < 16U; ++index)
    {
        g_reassembly[index] =
            g_rx[index & 7U].data[(index >> 1U) & 7U];
    }
    g_response_state = g_reassembly[15U];
}

void StarTask_UdsChecksumSupported_20ms(void)
{
    uint32_t index;
    uint32_t checksum = 0U;
    for (index = 0U; index < 16U; ++index)
    {
        checksum ^= (uint32_t)g_reassembly[index] & 0xFFU;
    }
    g_pid_value = checksum;
}
