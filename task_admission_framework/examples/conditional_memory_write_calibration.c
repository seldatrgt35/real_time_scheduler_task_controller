/*
 * Training-only kernels for conditional memory-write interaction cost.
 * Real automotive holdouts, including github_isotp_c_blind_holdout.c, must
 * never be used to fit the resulting model.
 */
#include "conditional_memory_write_calibration.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT32_TYPE__ uint32_t;

#define STAR_CALIBRATION_MAX_ITERATIONS (32U)
#define STAR_CALIBRATION_OUTPUT_SIZE    (128U)
#define STAR_CALIBRATION_SEQUENCE_MASK  (15U)
#define STAR_CALIBRATION_FRAME_TYPE     (2U)

typedef struct
{
    uint8_t frame_type;
    uint8_t sequence_number;
    uint8_t length;
    /* Five payload bytes keep the frame stride at the holdout's 8 bytes. */
    uint8_t payload[5U];
} ConditionalMemoryFrame;

static ConditionalMemoryFrame s_frames[STAR_CALIBRATION_MAX_ITERATIONS];
static uint8_t s_output[STAR_CALIBRATION_OUTPUT_SIZE];
static volatile uint32_t s_result;

void ConditionalMemoryWriteCalibration_Initialize(void)
{
    uint32_t index;
    uint32_t byte_index;

    for (index = 0U; index < STAR_CALIBRATION_MAX_ITERATIONS; ++index)
    {
        s_frames[index].frame_type = STAR_CALIBRATION_FRAME_TYPE;
        s_frames[index].sequence_number =
            (uint8_t)((index + 1U) & STAR_CALIBRATION_SEQUENCE_MASK);
        s_frames[index].length = 4U;
        for (byte_index = 0U; byte_index < 4U; ++byte_index)
        {
            s_frames[index].payload[byte_index] =
                (uint8_t)((index * 19U) + (byte_index * 7U));
        }
    }

    for (index = 0U; index < STAR_CALIBRATION_OUTPUT_SIZE; ++index)
    {
        s_output[index] = 0U;
    }
    s_result = 0U;
}

static void ConditionalWrite1Kernel(uint32_t count)
{
    uint32_t frame_index;
    uint32_t destination = 0U;
    uint32_t expected_sequence = 1U;

    for (frame_index = 0U; frame_index < count; ++frame_index)
    {
        if ((s_frames[frame_index].frame_type == STAR_CALIBRATION_FRAME_TYPE) &&
            (s_frames[frame_index].sequence_number == expected_sequence) &&
            (s_frames[frame_index].length >= 1U))
        {
            s_output[destination] = s_frames[frame_index].payload[0U];
            destination += 1U;
            expected_sequence =
                (expected_sequence + 1U) & STAR_CALIBRATION_SEQUENCE_MASK;
        }
    }
    s_result = destination ^ expected_sequence;
}

static void ConditionalWrite2Kernel(uint32_t count)
{
    uint32_t frame_index;
    uint32_t destination = 0U;
    uint32_t expected_sequence = 1U;

    for (frame_index = 0U; frame_index < count; ++frame_index)
    {
        if ((s_frames[frame_index].frame_type == STAR_CALIBRATION_FRAME_TYPE) &&
            (s_frames[frame_index].sequence_number == expected_sequence) &&
            (s_frames[frame_index].length >= 2U))
        {
            s_output[destination] = s_frames[frame_index].payload[0U];
            s_output[destination + 1U] = s_frames[frame_index].payload[1U];
            destination += 2U;
            expected_sequence =
                (expected_sequence + 1U) & STAR_CALIBRATION_SEQUENCE_MASK;
        }
    }
    s_result = destination ^ expected_sequence;
}

static void ConditionalWrite4Kernel(uint32_t count)
{
    uint32_t frame_index;
    uint32_t destination = 0U;
    uint32_t expected_sequence = 1U;

    for (frame_index = 0U; frame_index < count; ++frame_index)
    {
        if ((s_frames[frame_index].frame_type == STAR_CALIBRATION_FRAME_TYPE) &&
            (s_frames[frame_index].sequence_number == expected_sequence) &&
            (s_frames[frame_index].length >= 4U))
        {
            s_output[destination] = s_frames[frame_index].payload[0U];
            s_output[destination + 1U] = s_frames[frame_index].payload[1U];
            s_output[destination + 2U] = s_frames[frame_index].payload[2U];
            s_output[destination + 3U] = s_frames[frame_index].payload[3U];
            destination += 4U;
            expected_sequence =
                (expected_sequence + 1U) & STAR_CALIBRATION_SEQUENCE_MASK;
        }
    }
    s_result = destination ^ expected_sequence;
}

void ConditionalMemoryWriteCalibration_Write1_8(void)
{
    ConditionalWrite1Kernel(8U);
}

void ConditionalMemoryWriteCalibration_Write1_16(void)
{
    ConditionalWrite1Kernel(16U);
}

void ConditionalMemoryWriteCalibration_Write1_32(void)
{
    ConditionalWrite1Kernel(32U);
}

void ConditionalMemoryWriteCalibration_Write2_8(void)
{
    ConditionalWrite2Kernel(8U);
}

void ConditionalMemoryWriteCalibration_Write2_16(void)
{
    ConditionalWrite2Kernel(16U);
}

void ConditionalMemoryWriteCalibration_Write2_32(void)
{
    ConditionalWrite2Kernel(32U);
}

void ConditionalMemoryWriteCalibration_Write4_8(void)
{
    ConditionalWrite4Kernel(8U);
}

void ConditionalMemoryWriteCalibration_Write4_16(void)
{
    ConditionalWrite4Kernel(16U);
}

void ConditionalMemoryWriteCalibration_Write4_32(void)
{
    ConditionalWrite4Kernel(32U);
}
