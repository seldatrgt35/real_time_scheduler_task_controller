#include "automotive_standard_tasks.h"

#if defined(__GNUC__) || defined(__clang__)
#define STAR_NOINLINE __attribute__((noinline))
#else
#define STAR_NOINLINE
#endif

typedef uint32_t (*star_transform_t)(uint32_t);
static uint32_t g_sensor[256];
static uint32_t g_filtered[256];
static volatile uint32_t g_sink;

static STAR_NOINLINE uint32_t diagnostic_transform(uint32_t value)
{
    return value + 17U;
}

static const star_transform_t g_transforms[2] = {
    diagnostic_transform, diagnostic_transform
};

void StarAutomotive_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < 256U; ++index) {
        g_sensor[index] = index * 13U + 5U;
        g_filtered[index] = 0U;
    }
    g_sink = 0x13579bdfU;
}

void StarTask_5ms_SensorFusion(void)
{
    uint32_t index;
    uint32_t value = g_sink | 1U;
    for (index = 0U; index < 144U; ++index) {
        value += index + 3U;
        value *= ((index & 7U) + 1U);
        value ^= (index | 0x55U);
        value = (value << 1U) | (value >> 31U);
        if ((index & 1U) != 0U) { value += index; }
        else { value ^= index; }
    }
    g_sink = value;
}

void StarTask_10ms_SignalFilter(void)
{
    uint32_t index;
    uint32_t value = g_sink;
    for (index = 0U; index < 192U; ++index) { value ^= g_sensor[index]; }
    for (index = 0U; index < 192U; ++index) { value += g_sensor[(index * 17U) & 255U]; }
    for (index = 0U; index < 96U; ++index) { g_filtered[index] = g_sensor[index]; }
    for (index = 96U; index < 160U; ++index) { g_filtered[index] = 0U; }
    g_sink = value;
}

void StarTask_20ms_MotorControl(void)
{
    uint32_t index;
    int32_t q15 = (int32_t)(g_sink | 1U);
    uint32_t q31 = g_sink | 1U;
    for (index = 0U; index < 80U; ++index) { q15 = (q15 * 16384) >> 15; }
    for (index = 0U; index < 80U; ++index) { q15 += (q15 * 8192) >> 15; }
    for (index = 0U; index < 80U; ++index) { q31 *= 1024U; }
    for (index = 0U; index < 80U; ++index) { q31 += q31 * 16U; }
    g_sink = q31 ^ (uint32_t)q15;
}

void StarTask_50ms_StateEstimator(void)
{
    uint32_t index;
    float state = (float)(g_sink | 1U);
    double covariance = (double)(g_sink | 1U);
    for (index = 0U; index < 40U; ++index) { state = state + 1.25F; }
    for (index = 0U; index < 40U; ++index) { state = state * 0.875F; }
    for (index = 0U; index < 24U; ++index) { covariance = covariance / 1.0625; }
    g_sink = (uint32_t)state ^ (uint32_t)covariance;
}

void StarTask_100ms_Diagnostics(void)
{
    uint32_t index;
    uint32_t value = g_sink;
    for (index = 0U; index < 96U; ++index) { value ^= g_sensor[index] & 255U; }
    for (index = 0U; index < 48U; ++index) { value = diagnostic_transform(value); }
    for (index = 0U; index < 32U; ++index) { value = g_transforms[index & 1U](value); }
    for (index = 0U; index < 40U; ++index) {
        switch (index & 3U) {
            case 0U: value += 1U; break;
            case 1U: value ^= 2U; break;
            case 2U: value |= 4U; break;
            default: value &= 0xfffffffeU; break;
        }
    }
    g_sink = value;
}
