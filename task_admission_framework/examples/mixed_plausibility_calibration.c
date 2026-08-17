/* Training-only mixed memory/branch/bitwise plausibility kernels. */
#include "mixed_plausibility_calibration.h"

typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;

static uint16_t g_plausibility_samples[32U];
static volatile uint32_t g_plausibility_sink;

void MixedPlausibilityCalibration_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < 32U; ++index)
    {
        g_plausibility_samples[index] =
            (uint16_t)(850U + (index * 29U));
    }
    g_plausibility_sink = 0U;
}

static void PlausibilityKernel(uint32_t count)
{
    uint32_t index;
    uint32_t total = 0U;
    uint32_t flags = 0U;
    for (index = 0U; index < count; ++index)
    {
        const uint32_t channel = index & 3U;
        const uint32_t sample = (uint32_t)g_plausibility_samples[index];
        total += sample;
        if (sample > (1000U + (channel * 17U)))
        {
            flags |= (1UL << channel);
        }
        else
        {
            flags &= ~(1UL << channel);
        }
    }
    g_plausibility_sink = total ^ flags;
}

void MixedPlausibilityCalibration_8(void) { PlausibilityKernel(8U); }
void MixedPlausibilityCalibration_16(void) { PlausibilityKernel(16U); }
void MixedPlausibilityCalibration_32(void) { PlausibilityKernel(32U); }
