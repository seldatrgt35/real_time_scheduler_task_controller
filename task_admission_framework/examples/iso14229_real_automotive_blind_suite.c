/*
 * Blind WCET suite derived from driftregion/iso14229 UDS server/client flows.
 * Upstream commit: b0e92b14fcc384d42bfd01ecd7f745addb6bf761
 * License: MIT, Copyright (c) Nick James Kirkby & Co-Operators.
 * This validation-only source must never train execution coefficients.
 */
#include "iso14229_real_automotive_blind_suite.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;

#define STAR_DID_COUNT            (8U)
#define STAR_TRANSFER_SIZE        (32U)
#define STAR_SECURITY_KEY_SIZE    (16U)

static uint16_t s_dids[STAR_DID_COUNT];
static uint16_t s_did_values[STAR_DID_COUNT];
static uint8_t s_response[64U];
static uint8_t s_address_request[7U];
static uint8_t s_transfer_data[STAR_TRANSFER_SIZE];
static uint8_t s_transfer_target[STAR_TRANSFER_SIZE];
static uint8_t s_received_key[STAR_SECURITY_KEY_SIZE];
static uint8_t s_expected_key[STAR_SECURITY_KEY_SIZE];
static volatile uint32_t s_result;

void StarIso14229RealSuite_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < STAR_DID_COUNT; ++index)
    {
        s_dids[index] = (uint16_t)(0xF180U + index);
        s_did_values[index] = (uint16_t)(0x1200U + (index * 17U));
    }
    for (index = 0U; index < 64U; ++index)
    {
        s_response[index] = 0U;
    }
    s_address_request[0] = 0x24U;
    s_address_request[1] = 0x20U;
    s_address_request[2] = 0x00U;
    s_address_request[3] = 0x10U;
    s_address_request[4] = 0x00U;
    s_address_request[5] = 0x01U;
    s_address_request[6] = 0x00U;
    for (index = 0U; index < STAR_TRANSFER_SIZE; ++index)
    {
        s_transfer_data[index] = (uint8_t)((index * 13U) + 7U);
        s_transfer_target[index] = 0U;
    }
    for (index = 0U; index < STAR_SECURITY_KEY_SIZE; ++index)
    {
        s_expected_key[index] = (uint8_t)((index * 29U) ^ 0xA5U);
        s_received_key[index] = s_expected_key[index];
    }
    s_result = 0U;
}

void StarTask_UdsReadDidPack_10ms(void)
{
    uint32_t did_index;
    uint32_t destination = 1U;
    s_response[0] = 0x62U;
    for (did_index = 0U; did_index < STAR_DID_COUNT; ++did_index)
    {
        const uint16_t did = s_dids[did_index];
        const uint16_t value = s_did_values[did_index];
        s_response[destination] = (uint8_t)(did >> 8U);
        s_response[destination + 1U] = (uint8_t)did;
        s_response[destination + 2U] = (uint8_t)(value >> 8U);
        s_response[destination + 3U] = (uint8_t)value;
        destination += 4U;
    }
    s_result = destination ^ s_response[1U];
}

void StarTask_UdsAddressLengthDecode_20ms(void)
{
    uint32_t byte_index;
    uint32_t address = 0U;
    uint32_t size = 0U;
    for (byte_index = 0U; byte_index < 4U; ++byte_index)
    {
        address |= (uint32_t)s_address_request[1U + byte_index]
                   << (8U * (3U - byte_index));
    }
    for (byte_index = 0U; byte_index < 2U; ++byte_index)
    {
        size |= (uint32_t)s_address_request[5U + byte_index]
                << (8U * (1U - byte_index));
    }
    s_result = address ^ size;
}

void StarTask_UdsTransferDataBlock_5ms(void)
{
    uint32_t byte_index;
    uint32_t checksum = 0U;
    uint32_t block_sequence_counter = 0x21U;
    for (byte_index = 0U; byte_index < STAR_TRANSFER_SIZE; ++byte_index)
    {
        const uint8_t value = s_transfer_data[byte_index];
        s_transfer_target[byte_index] = value;
        checksum += value;
    }
    block_sequence_counter += 1U;
    s_result = checksum ^ block_sequence_counter;
}

void StarTask_UdsSecurityKeyValidate_20ms(void)
{
    uint32_t byte_index;
    uint32_t mismatch = 0U;
    for (byte_index = 0U; byte_index < STAR_SECURITY_KEY_SIZE; ++byte_index)
    {
        mismatch |= (uint32_t)(s_received_key[byte_index]
                               ^ s_expected_key[byte_index]);
    }
    s_result = mismatch;
}
