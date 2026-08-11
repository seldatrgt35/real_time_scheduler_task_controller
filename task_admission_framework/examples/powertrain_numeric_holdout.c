#include "powertrain_numeric_holdout.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;
typedef __INT64_TYPE__ int64_t;

#define STAR_HOLDOUT_INPUT_SIZE (96U)
#define STAR_HOLDOUT_TABLE_SIZE (16U)

static int32_t g_star_holdout_input[STAR_HOLDOUT_INPUT_SIZE];
static int32_t g_star_holdout_table[STAR_HOLDOUT_TABLE_SIZE + 1U];
static volatile int32_t g_star_holdout_sink;

void StarPowertrainNumericHoldout_Initialize(void)
{
    uint32_t index;

    for (index = 0U; index < STAR_HOLDOUT_INPUT_SIZE; ++index)
    {
        g_star_holdout_input[index] = (int32_t)((index * 53U) & 2047U) - 1024;
    }
    for (index = 0U; index <= STAR_HOLDOUT_TABLE_SIZE; ++index)
    {
        g_star_holdout_table[index] = (int32_t)(index * 310U) - 1400;
    }
    g_star_holdout_sink = 23;
}

static void StarHoldout_SignedArithmetic(void)
{
    uint32_t index;
    int32_t accumulator = g_star_holdout_sink;

    for (index = 0U; index < 80U; ++index)
    {
        const int32_t sample = g_star_holdout_input[index];
        accumulator += sample;
        accumulator -= (sample / 4);
        accumulator += (sample * 3);
    }
    g_star_holdout_sink = accumulator;
}

static void StarHoldout_SaturationClamp(void)
{
    uint32_t index;
    int32_t accumulator = 0;

    for (index = 0U; index < 72U; ++index)
    {
        int32_t value = g_star_holdout_input[index] * 3;

        if (value > 1200)
        {
            value = 1200;
        }
        else if (value < -1200)
        {
            value = -1200;
        }
        else
        {
            /* The value remains inside the holdout torque range. */
        }
        accumulator += value;
    }
    g_star_holdout_sink = accumulator;
}

static void StarHoldout_Lookup1d(void)
{
    uint32_t index;
    int32_t accumulator = 0;

    for (index = 0U; index < 64U; ++index)
    {
        const uint32_t table_index = (index * 7U) & (STAR_HOLDOUT_TABLE_SIZE - 1U);
        accumulator += g_star_holdout_table[table_index];
    }
    g_star_holdout_sink = accumulator;
}

static void StarHoldout_LinearInterpolation(void)
{
    uint32_t index;
    int32_t accumulator = 0;

    for (index = 0U; index < 56U; ++index)
    {
        const uint32_t table_index = (index * 7U) & (STAR_HOLDOUT_TABLE_SIZE - 1U);
        const int32_t lower = g_star_holdout_table[table_index];
        const int32_t upper = g_star_holdout_table[table_index + 1U];
        const int32_t fraction_q8 = (int32_t)((index * 31U) & 255U);
        const int64_t weighted_delta = (int64_t)(upper - lower) * (int64_t)fraction_q8;
        const int32_t interpolated = lower + (int32_t)(weighted_delta / 256);

        accumulator += interpolated;
    }
    g_star_holdout_sink = accumulator;
}

void StarTask_5ms_PowertrainNumericHoldout(void)
{
    StarHoldout_SignedArithmetic();
    StarHoldout_SaturationClamp();
    StarHoldout_Lookup1d();
    StarHoldout_LinearInterpolation();
}
