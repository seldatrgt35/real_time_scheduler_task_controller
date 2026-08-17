/**
 * Blind scheduler holdout derived from lishen2/isotp-c receive processing.
 *
 * Upstream: https://github.com/lishen2/isotp-c
 * Pinned commit: 5593428d95af10dde1e565cebcda16089fc74857
 * License: MIT, Copyright (c) 2019 Shen Li & Co-Operators.
 *
 * The bounded scheduler wrappers below preserve consecutive-frame sequence
 * validation, payload reassembly and protocol-error aging behavior. This
 * source has never been used to fit STAR execution coefficients.
 */
#include "github_isotp_c_blind_holdout.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT32_TYPE__ uint32_t;

#define STAR_ISOTP_FRAME_COUNT       (12U)
#define STAR_ISOTP_ERROR_COUNT       (16U)
#define STAR_ISOTP_REASSEMBLY_SIZE   (64U)
#define STAR_ISOTP_FRAME_TYPE_CF     (2U)
#define STAR_ISOTP_SEQUENCE_MASK     (15U)

typedef struct
{
    uint8_t frame_type;
    uint8_t sequence_number;
    uint8_t length;
    uint8_t payload[5U];
} StarIsotpFrame;

static StarIsotpFrame s_frames[STAR_ISOTP_FRAME_COUNT];
static uint8_t s_reassembly[STAR_ISOTP_REASSEMBLY_SIZE];
static uint8_t s_error_status[STAR_ISOTP_ERROR_COUNT];
static uint8_t s_error_age[STAR_ISOTP_ERROR_COUNT];
static volatile uint32_t s_reassembly_result;
static volatile uint32_t s_error_result;

void StarGithubIsotp_Initialize(void)
{
    uint32_t index;
    uint32_t byte_index;

    for (index = 0U; index < STAR_ISOTP_FRAME_COUNT; ++index)
    {
        s_frames[index].frame_type = STAR_ISOTP_FRAME_TYPE_CF;
        s_frames[index].sequence_number =
            (uint8_t)((index + 1U) & STAR_ISOTP_SEQUENCE_MASK);
        s_frames[index].length = 5U;
        for (byte_index = 0U; byte_index < 5U; ++byte_index)
        {
            s_frames[index].payload[byte_index] =
                (uint8_t)((index * 19U) + (byte_index * 7U));
        }
    }

    for (index = 0U; index < STAR_ISOTP_REASSEMBLY_SIZE; ++index)
    {
        s_reassembly[index] = 0U;
    }

    for (index = 0U; index < STAR_ISOTP_ERROR_COUNT; ++index)
    {
        s_error_status[index] = (uint8_t)((index * 3U) & 7U);
        s_error_age[index] = (uint8_t)(index & 1U);
    }

    s_reassembly_result = 0U;
    s_error_result = 0U;
}

void StarTask_IsotpConsecutiveFrameReassembly_10ms(void)
{
    uint32_t frame_index;
    uint32_t destination = 0U;
    uint32_t expected_sequence = 1U;

    for (frame_index = 0U;
         frame_index < STAR_ISOTP_FRAME_COUNT;
         ++frame_index)
    {
        if ((s_frames[frame_index].frame_type == STAR_ISOTP_FRAME_TYPE_CF) &&
            (s_frames[frame_index].sequence_number == expected_sequence) &&
            (s_frames[frame_index].length >= 4U))
        {
            s_reassembly[destination] = s_frames[frame_index].payload[0U];
            s_reassembly[destination + 1U] =
                s_frames[frame_index].payload[1U];
            s_reassembly[destination + 2U] =
                s_frames[frame_index].payload[2U];
            s_reassembly[destination + 3U] =
                s_frames[frame_index].payload[3U];
            destination += 4U;
            expected_sequence =
                (expected_sequence + 1U) & STAR_ISOTP_SEQUENCE_MASK;
        }
    }

    s_reassembly_result = destination ^ expected_sequence;
}

void StarTask_IsotpErrorAging_20ms(void)
{
    uint32_t index;
    uint32_t active_errors = 0U;

    for (index = 0U; index < STAR_ISOTP_ERROR_COUNT; ++index)
    {
        const uint8_t status = s_error_status[index];

        if ((status & 3U) != 0U)
        {
            if (s_error_age[index] < 7U)
            {
                ++s_error_age[index];
            }
        }
        else if (s_error_age[index] > 0U)
        {
            --s_error_age[index];
        }
        else
        {
            /* Error age remains clear. */
        }

        if (s_error_age[index] >= 3U)
        {
            active_errors |= 1UL << (index & STAR_ISOTP_SEQUENCE_MASK);
        }
    }

    s_error_result = active_errors;
}
