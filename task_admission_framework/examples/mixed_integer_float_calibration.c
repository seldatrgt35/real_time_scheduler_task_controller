#include "mixed_integer_float_calibration.h"

static uint32_t s_input[32];
static volatile uint32_t s_integer_sink;
static volatile float s_float_sink;

void StarMixedIntegerFloat_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < 32U; ++index)
    {
        s_input[index] = (index * 11U) + 3U;
    }
    s_integer_sink = 7U;
    s_float_sink = 1.25F;
}

void StarMixedIntegerFloat_Add8(void)
{
    uint32_t index;
    uint32_t integer_value = s_integer_sink;
    float float_value = s_float_sink;
    for (index = 0U; index < 8U; ++index)
    {
        integer_value += index;
        float_value += (float)integer_value;
    }
    s_integer_sink = integer_value;
    s_float_sink = float_value;
}

void StarMixedIntegerFloat_Add16(void)
{
    uint32_t index;
    uint32_t integer_value = s_integer_sink;
    float float_value = s_float_sink;
    for (index = 0U; index < 16U; ++index)
    {
        integer_value += index;
        float_value += (float)integer_value;
    }
    s_integer_sink = integer_value;
    s_float_sink = float_value;
}

void StarMixedIntegerFloat_Add32(void)
{
    uint32_t index;
    uint32_t integer_value = s_integer_sink;
    float float_value = s_float_sink;
    for (index = 0U; index < 32U; ++index)
    {
        integer_value += index;
        float_value += (float)integer_value;
    }
    s_integer_sink = integer_value;
    s_float_sink = float_value;
}

void StarMixedIntegerFloat_Multiply8(void)
{
    uint32_t index;
    uint32_t integer_value = s_integer_sink;
    float float_value = s_float_sink;
    for (index = 0U; index < 8U; ++index)
    {
        integer_value = (integer_value * 3U) + index;
        float_value = (float_value * 0.75F) + (float)integer_value;
    }
    s_integer_sink = integer_value;
    s_float_sink = float_value;
}

void StarMixedIntegerFloat_Multiply16(void)
{
    uint32_t index;
    uint32_t integer_value = s_integer_sink;
    float float_value = s_float_sink;
    for (index = 0U; index < 16U; ++index)
    {
        integer_value = (integer_value * 3U) + index;
        float_value = (float_value * 0.75F) + (float)integer_value;
    }
    s_integer_sink = integer_value;
    s_float_sink = float_value;
}

void StarMixedIntegerFloat_Multiply32(void)
{
    uint32_t index;
    uint32_t integer_value = s_integer_sink;
    float float_value = s_float_sink;
    for (index = 0U; index < 32U; ++index)
    {
        integer_value = (integer_value * 3U) + index;
        float_value = (float_value * 0.75F) + (float)integer_value;
    }
    s_integer_sink = integer_value;
    s_float_sink = float_value;
}

void StarMixedIntegerFloat_Memory8(void)
{
    uint32_t index;
    uint32_t integer_value = s_integer_sink;
    float float_value = s_float_sink;
    for (index = 0U; index < 8U; ++index)
    {
        integer_value += s_input[index];
        float_value = (float_value + (float)s_input[index]) * 0.5F;
    }
    s_integer_sink = integer_value;
    s_float_sink = float_value;
}

void StarMixedIntegerFloat_Memory16(void)
{
    uint32_t index;
    uint32_t integer_value = s_integer_sink;
    float float_value = s_float_sink;
    for (index = 0U; index < 16U; ++index)
    {
        integer_value += s_input[index];
        float_value = (float_value + (float)s_input[index]) * 0.5F;
    }
    s_integer_sink = integer_value;
    s_float_sink = float_value;
}

void StarMixedIntegerFloat_Memory32(void)
{
    uint32_t index;
    uint32_t integer_value = s_integer_sink;
    float float_value = s_float_sink;
    for (index = 0U; index < 32U; ++index)
    {
        integer_value += s_input[index];
        float_value = (float_value + (float)s_input[index]) * 0.5F;
    }
    s_integer_sink = integer_value;
    s_float_sink = float_value;
}
