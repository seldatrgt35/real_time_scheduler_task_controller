#include "basic_feature_wcet_suite.h"

#define STAR_BASIC_ITERATIONS (32U)
#define STAR_BASIC_MASK       (63U)

#if defined(__GNUC__) || defined(__clang__)
#define STAR_NOINLINE __attribute__((noinline))
#else
#define STAR_NOINLINE
#endif

typedef uint32_t (*StarBasicTransform)(uint32_t);

static uint32_t s_input[64];
static uint32_t s_output[64];
static volatile uint32_t s_sink;

static STAR_NOINLINE uint32_t AddThree(uint32_t value)
{
    return value + 3U;
}

static STAR_NOINLINE uint32_t XorMask(uint32_t value)
{
    return value ^ 0x5AU;
}

static const StarBasicTransform s_transforms[2] = {AddThree, XorMask};

void StarBasicSuite_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < 64U; ++index)
    {
        s_input[index] = (index * 13U) + 5U;
        s_output[index] = 0U;
    }
    s_sink = 0x13579BDFU;
}

void StarBasic_Arithmetic(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    const uint32_t local = 7U;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value += 3U;
        value += local;
        value += index;
        value *= local;
        value -= local;
    }
    s_sink = value;
}

void StarBasic_DivideModulo(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 1U; index <= STAR_BASIC_ITERATIONS; ++index)
    {
        value += 31U / index;
        value += 0xF3579BDFU % index;
    }
    s_sink = value;
}

void StarBasic_BitwiseShift(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value &= 0xFFFFFFFEU;
        value |= index;
        value ^= 0x5AU;
        value = (value << 1U) | (value >> 31U);
    }
    s_sink = value;
}

void StarBasic_Branch(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        if ((index & 1U) != 0U)
        {
            value += index;
        }
        else
        {
            value ^= index;
        }
    }
    s_sink = value;
}

void StarBasic_SequentialMemory(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value += s_input[index];
    }
    s_sink = value;
}

void StarBasic_RandomMemory(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value += s_input[(index * 17U) & STAR_BASIC_MASK];
    }
    s_sink = value;
}

void StarBasic_MemoryCopy(void)
{
    uint32_t index;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        s_output[index] = s_input[index];
    }
    s_sink = s_output[STAR_BASIC_ITERATIONS - 1U];
}

void StarBasic_MemorySet(void)
{
    uint32_t index;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        s_output[index] = 0xA5A5A5A5U;
    }
    s_sink = s_output[STAR_BASIC_ITERATIONS - 1U];
}

void StarBasic_FixedPoint(void)
{
    uint32_t index;
    uint32_t value = s_sink | 1U;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value += (value * 8192U) >> 15U;
    }
    s_sink = value;
}

void StarBasic_FloatingPoint(void)
{
    uint32_t index;
    float value = (float)(s_sink | 1U);
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value = (value + 1.25F) * 0.875F;
    }
    s_sink = (uint32_t)value;
}

void StarBasic_DirectCall(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value = AddThree(value);
    }
    s_sink = value;
}

void StarBasic_IndirectCall(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value = s_transforms[index & 1U](value);
    }
    s_sink = value;
}

void StarBasic_Switch(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        switch (index & 3U)
        {
            case 0U: value += 1U; break;
            case 1U: value ^= 2U; break;
            case 2U: value |= 4U; break;
            default: value &= 0xFFFFFFFEU; break;
        }
    }
    s_sink = value;
}

void StarBasic_MaskedMultiply(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value += (index * 17U) & STAR_BASIC_MASK;
    }
    s_sink = value;
}

void StarBasic_MaskedDivide(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 1U; index <= STAR_BASIC_ITERATIONS; ++index)
    {
        value += (0x3FFFU / index) & STAR_BASIC_MASK;
    }
    s_sink = value;
}

void StarBasic_MaskedModulo(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 1U; index <= STAR_BASIC_ITERATIONS; ++index)
    {
        value += (0xF3579BDFU % index) & STAR_BASIC_MASK;
    }
    s_sink = value;
}

void StarBasic_BitwiseNested(void)
{
    uint32_t index;
    uint32_t value = s_sink;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value = (value ^ index) | 0x55U;
    }
    s_sink = value;
}

void StarBasic_Checksum(void)
{
    uint32_t index;
    uint32_t checksum = s_sink;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        checksum ^= s_input[index] & 0xFFU;
    }
    s_sink = checksum;
}

void StarBasic_Q15Multiply(void)
{
    uint32_t index;
    uint32_t value = s_sink | 1U;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value = (value * 16384U) >> 15U;
    }
    s_sink = value;
}

void StarBasic_Q31Multiply(void)
{
    uint32_t index;
    uint32_t value = s_sink | 1U;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value *= 1024U;
    }
    s_sink = value;
}

void StarBasic_Q31Mac(void)
{
    uint32_t index;
    uint32_t value = s_sink | 1U;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value += value * 16U;
    }
    s_sink = value;
}

void StarBasic_Float32Add(void)
{
    uint32_t index;
    float value = (float)(s_sink | 1U);
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value = value + 1.25F;
    }
    s_sink = (uint32_t)value;
}

void StarBasic_Float32Divide(void)
{
    uint32_t index;
    float value = (float)(s_sink | 1U);
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value = value / 1.0625F;
    }
    s_sink = (uint32_t)value;
}

void StarBasic_Float64Add(void)
{
    uint32_t index;
    double value = (double)(s_sink | 1U);
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value = value + 1.25;
    }
    s_sink = (uint32_t)value;
}

void StarBasic_Float64Multiply(void)
{
    uint32_t index;
    double value = (double)(s_sink | 1U);
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value = value * 0.875;
    }
    s_sink = (uint32_t)value;
}

void StarBasic_Float64Divide(void)
{
    uint32_t index;
    double value = (double)(s_sink | 1U);
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        value = value / 1.0625;
    }
    s_sink = (uint32_t)value;
}

void StarBasic_IntToFloat(void)
{
    uint32_t index;
    float total = 0.0F;
    for (index = 0U; index < STAR_BASIC_ITERATIONS; ++index)
    {
        total += (float)s_input[index];
    }
    s_sink = (uint32_t)total;
}
