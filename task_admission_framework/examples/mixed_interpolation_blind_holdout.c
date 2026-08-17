/* Independent blind holdout. This source must never be used for model fitting. */
#include "mixed_interpolation_blind_holdout.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;
typedef __INT64_TYPE__ int64_t;

static int32_t g_holdout_axis[33U];
static uint32_t g_holdout_fraction[24U];
static volatile int32_t g_holdout_sink;

static int32_t BlendAxisPoint(int32_t first, int32_t second, uint32_t q9)
{
    const int64_t distance = (int64_t)(second - first) * (int64_t)q9;
    return first + (int32_t)(distance / 512L);
}

void MixedInterpolationHoldout_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < 33U; ++index)
    {
        g_holdout_axis[index] = (int32_t)(index * 213L) - 350L;
    }
    for (index = 0U; index < 24U; ++index)
    {
        g_holdout_fraction[index] = (index * 43U) & 511U;
    }
    g_holdout_sink = 0;
}

void MixedInterpolationHoldout_24(void)
{
    uint32_t index;
    int32_t accumulated = 0;
    for (index = 0U; index < 24U; ++index)
    {
        const uint32_t segment = (index * 7U) & 31U;
        int32_t output = BlendAxisPoint(
            g_holdout_axis[segment],
            g_holdout_axis[segment + 1U],
            g_holdout_fraction[index]);
        if (output > 5200L) { output = 5200L; }
        else if (output < -200L) { output = -200L; }
        else { /* Output is inside the holdout range. */ }
        accumulated += output;
    }
    g_holdout_sink = accumulated;
}
