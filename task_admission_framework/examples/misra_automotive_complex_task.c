#include "misra_automotive_complex_task.h"

#if defined(__GNUC__) || defined(__clang__)
#define STAR_NOINLINE __attribute__((noinline))
#else
#define STAR_NOINLINE
#endif

typedef uint32_t (*StarTransformFunction)(uint32_t value);

static uint32_t g_star_input[256U];
static uint32_t g_star_output[256U];
static volatile uint32_t g_star_result;

static STAR_NOINLINE uint32_t StarTransform_AddOffset(uint32_t value)
{
    return value + 23U;
}

static const StarTransformFunction g_star_transforms[2] =
{
    StarTransform_AddOffset,
    StarTransform_AddOffset
};

void StarMisraAutomotive_Initialize(void)
{
    uint32_t index;

    /* Initialize all 256 input and output samples outside the timed task. */
    for (index = 0U; index < 256U; ++index)
    {
        g_star_input[index] = (index * 9U) + 7U;
        g_star_output[index] = 0U;
    }

    g_star_result = 0x3579BDF1U;
}

void StarTask_5ms_MisraControl(void)
{
    uint32_t index;
    uint32_t value = g_star_result | 1U;

    for (index = 0U; index < 80U; ++index)
    {
        /* The bounded loop represents sensor normalization and state mixing. */
        value += index + 5U;
        value *= ((index & 7U) + 1U);
        value ^= (index | 0x45U);
        value = (value << 1U) | (value >> 31U);

        if ((index & 1U) != 0U)
        {
            value += index;
        }
        else
        {
            value ^= index;
        }
    }

    g_star_result = value;
}

void StarTask_10ms_MisraMemory(void)
{
    uint32_t index;
    uint32_t value = g_star_result;

    /* Process 112 sequential samples from the current acquisition window. */
    for (index = 0U; index < 112U; ++index)
    {
        value ^= g_star_input[index];
    }

    /* Process 72 deterministically indexed samples. */
    for (index = 0U; index < 72U; ++index)
    {
        value += g_star_input[(index * 17U) & 255U];
    }

    /* Copy the first 40 samples into the output buffer. */
    for (index = 0U; index < 40U; ++index)
    {
        g_star_output[index] = g_star_input[index];
    }

    /* Clear output samples 40 through 63. */
    for (index = 40U; index < 64U; ++index)
    {
        g_star_output[index] = 0U;
    }

    g_star_result = value;
}

void StarTask_20ms_MisraFixedPoint(void)
{
    uint32_t index;
    uint32_t q31_value = g_star_result | 1U;

    for (index = 0U; index < 48U; ++index)
    {
        q31_value += q31_value * 16U;
    }

    g_star_result = q31_value;
}

void StarTask_50ms_MisraFloatingPoint(void)
{
    uint32_t index;
    float filtered_value = (float)(g_star_result | 1U);

    for (index = 0U; index < 20U; ++index)
    {
        filtered_value = filtered_value * 0.875F;
    }

    g_star_result = (uint32_t)filtered_value;
}

void StarTask_100ms_MisraDiagnostics(void)
{
    uint32_t index;
    uint32_t value = g_star_result;

    for (index = 0U; index < 56U; ++index)
    {
        value ^= g_star_input[index] & 255U;
    }

    for (index = 0U; index < 20U; ++index)
    {
        value = g_star_transforms[index & 1U](value);
    }

    for (index = 0U; index < 24U; ++index)
    {
        switch (index & 3U)
        {
            case 0U:
                value += 1U;
                break;
            case 1U:
                value ^= 2U;
                break;
            case 2U:
                value |= 4U;
                break;
            default:
                value &= 0xFFFFFFFEU;
                break;
        }
    }

    g_star_result = value;
}

void StarTask_20ms_MisraAutomotiveComplex(void)
{
    StarTask_5ms_MisraControl();
    StarTask_10ms_MisraMemory();
    StarTask_20ms_MisraFixedPoint();
    StarTask_50ms_MisraFloatingPoint();
    StarTask_100ms_MisraDiagnostics();
}
