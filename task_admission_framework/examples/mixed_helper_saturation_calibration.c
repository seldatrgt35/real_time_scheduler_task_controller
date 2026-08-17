/*
 * Training-only kernels for the mixed execution-region model.
 * body_chassis_control_holdout.c must never be used to fit these families.
 */
#include "mixed_helper_saturation_calibration.h"

typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT16_TYPE__ int16_t;
typedef __INT32_TYPE__ int32_t;
typedef __INT64_TYPE__ int64_t;

static uint16_t g_input[32U];
static int16_t g_output[32U];
static int32_t g_map[33U];
static volatile int32_t g_sink;

static int32_t ApplyGainQ8(int32_t value, int32_t gain_q8)
{
    return (value * gain_q8) / 256L;
}

static int32_t InterpolateQ8(int32_t lower, int32_t upper, uint32_t fraction)
{
    const int64_t delta = (int64_t)(upper - lower) * (int64_t)fraction;
    return lower + (int32_t)(delta / 256L);
}

void MixedRegionCalibration_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < 32U; ++index)
    {
        g_input[index] = (uint16_t)(700U + (index * 37U));
        g_output[index] = 0;
        g_map[index] = (int32_t)(index * 180L);
    }
    g_map[32U] = 5760L;
    g_sink = 0;
}

static void ActuatorKernel(uint32_t count)
{
    uint32_t index;
    int32_t total = 0;
    for (index = 0U; index < count; ++index)
    {
        int32_t command = ApplyGainQ8(1200L - (int32_t)g_input[index], 96L);
        if (command > 100L) { command = 100L; }
        else if (command < 0L) { command = 0L; }
        else { /* Command is in range. */ }
        g_output[index] = (int16_t)command;
        total += command;
    }
    g_sink = total;
}

static void AccumulatorKernel(uint32_t count)
{
    uint32_t index;
    int32_t request = g_sink;
    for (index = 0U; index < count; ++index)
    {
        request += ApplyGainQ8((int32_t)g_input[index] - 1000L, 64L);
        if (request > 2500L) { request = 2500L; }
        else if (request < -2500L) { request = -2500L; }
        else { /* Request is in range. */ }
    }
    g_sink = request;
}

static void InterpolationKernel(uint32_t count)
{
    uint32_t index;
    int32_t total = 0;
    for (index = 0U; index < count; ++index)
    {
        const uint32_t slot = (index * 5U) & 31U;
        const uint32_t fraction = (index * 37U) & 255U;
        int32_t value = InterpolateQ8(g_map[slot], g_map[slot + 1U], fraction);
        if (value > 5000L) { value = 5000L; }
        else if (value < 0L) { value = 0L; }
        else { /* Value is in range. */ }
        total += value;
    }
    g_sink = total;
}

#define DEFINE_POINT(name, kernel, count) \
    void name(void) { kernel(count); }

DEFINE_POINT(MixedCalibration_Actuator_8, ActuatorKernel, 8U)
DEFINE_POINT(MixedCalibration_Actuator_16, ActuatorKernel, 16U)
DEFINE_POINT(MixedCalibration_Actuator_32, ActuatorKernel, 32U)
DEFINE_POINT(MixedCalibration_Accumulator_8, AccumulatorKernel, 8U)
DEFINE_POINT(MixedCalibration_Accumulator_16, AccumulatorKernel, 16U)
DEFINE_POINT(MixedCalibration_Accumulator_32, AccumulatorKernel, 32U)
DEFINE_POINT(MixedCalibration_Interpolation_8, InterpolationKernel, 8U)
DEFINE_POINT(MixedCalibration_Interpolation_16, InterpolationKernel, 16U)
DEFINE_POINT(MixedCalibration_Interpolation_32, InterpolationKernel, 32U)
