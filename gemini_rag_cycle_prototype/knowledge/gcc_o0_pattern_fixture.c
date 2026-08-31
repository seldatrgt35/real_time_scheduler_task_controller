typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;

static volatile uint32_t s_pattern_sink;

__attribute__((noinline, used))
int32_t PatternLeafIncrement(int32_t input)
{
    int32_t result = input;
    result += 1;
    return result;
}

__attribute__((noinline, used))
int32_t PatternSingleArgumentCall(int32_t input)
{
    int32_t result = PatternLeafIncrement(input);
    return result;
}

__attribute__((noinline, used))
uint32_t PatternThreeArgumentHelper(uint32_t first,
                                    uint32_t second,
                                    uint32_t third)
{
    return (first + second) ^ third;
}

__attribute__((noinline, used))
uint32_t PatternThreeArgumentCall(uint32_t first,
                                  uint32_t second,
                                  uint32_t third)
{
    uint32_t result = PatternThreeArgumentHelper(first, second, third);
    return result;
}

__attribute__((noinline, used))
uint32_t PatternBoundedLoop(const volatile uint16_t *values)
{
    uint32_t index;
    uint32_t sum = 0U;
    for (index = 0U; index < 8U; ++index)
    {
        sum += values[index];
    }
    return sum;
}

__attribute__((noinline, used))
uint32_t PatternConditionalBranch(uint32_t value, uint32_t limit)
{
    uint32_t result;
    if (value > limit)
    {
        result = value - limit;
    }
    else
    {
        result = limit - value;
    }
    return result;
}

__attribute__((noinline, used))
void PatternVolatileReadWrite(volatile uint32_t *values, uint32_t index)
{
    const uint32_t value = values[index];
    values[index] = value ^ 0x55AA55AAUL;
    s_pattern_sink = values[index];
}

__attribute__((noinline, used))
int32_t PatternNestedHelperCall(int32_t input)
{
    int32_t result = PatternSingleArgumentCall(input);
    return result;
}
