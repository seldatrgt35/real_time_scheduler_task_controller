/* S32K148 DWT harness for mixed_helper_saturation_calibration.c. */
#include "mixed_helper_saturation_calibration.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;

#define STAR_DEMCR       (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL    (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT  (*(volatile uint32_t *)0xE0001004UL)
#define STAR_POINT_COUNT (9U)
#define STAR_SAMPLES     (40U)
#define STAR_WARMUPS     (8U)
#define STAR_CORE_HZ     (48000000U)

typedef void (*MixedCalibrationFunction)(void);

typedef struct
{
    uint32_t family_id;
    uint32_t iterations;
    uint32_t completed_samples;
    uint32_t mean_execution_us_x1000;
    uint32_t max_execution_us_x1000;
} MixedCalibrationPoint;

typedef struct
{
    uint32_t point_count;
    uint32_t sample_count;
    uint32_t measurement_overhead_cycles;
    uint32_t error_flags;
    MixedCalibrationPoint points[STAR_POINT_COUNT];
} MixedCalibrationResults;

typedef struct
{
    MixedCalibrationFunction function;
    uint32_t family_id;
    uint32_t iterations;
} MixedCalibrationDescriptor;

volatile uint32_t g_star_mixed_region_complete;
volatile uint32_t g_star_mixed_region_current;
volatile MixedCalibrationResults g_star_mixed_region_results;

static const MixedCalibrationDescriptor g_points[STAR_POINT_COUNT] =
{
    {MixedCalibration_Actuator_8, 0U, 8U},
    {MixedCalibration_Actuator_16, 0U, 16U},
    {MixedCalibration_Actuator_32, 0U, 32U},
    {MixedCalibration_Accumulator_8, 1U, 8U},
    {MixedCalibration_Accumulator_16, 1U, 16U},
    {MixedCalibration_Accumulator_32, 1U, 32U},
    {MixedCalibration_Interpolation_8, 2U, 8U},
    {MixedCalibration_Interpolation_16, 2U, 16U},
    {MixedCalibration_Interpolation_32, 2U, 32U}
};

static uint32_t ToMicrosecondsX1000(uint32_t cycles)
{
    return (uint32_t)(((uint64_t)cycles * 1000000000ULL) / STAR_CORE_HZ);
}

static uint32_t MeasureOverhead(void)
{
    uint32_t index;
    uint32_t minimum = 0xFFFFFFFFUL;
    for (index = 0U; index < 64U; ++index)
    {
        const uint32_t start = STAR_DWT_CYCCNT;
        const uint32_t elapsed = STAR_DWT_CYCCNT - start;
        if (elapsed < minimum) { minimum = elapsed; }
    }
    return minimum;
}

static void MeasurePoint(uint32_t point_index)
{
    const MixedCalibrationDescriptor * const descriptor = &g_points[point_index];
    volatile MixedCalibrationPoint * const point =
        &g_star_mixed_region_results.points[point_index];
    uint64_t total = 0ULL;
    uint32_t maximum = 0U;
    uint32_t sample;

    point->family_id = descriptor->family_id;
    point->iterations = descriptor->iterations;
    g_star_mixed_region_current = point_index;
    for (sample = 0U; sample < STAR_WARMUPS; ++sample)
    {
        MixedRegionCalibration_Initialize();
        descriptor->function();
    }
    for (sample = 0U; sample < STAR_SAMPLES; ++sample)
    {
        uint32_t elapsed;
        const uint32_t overhead =
            g_star_mixed_region_results.measurement_overhead_cycles;
        MixedRegionCalibration_Initialize();
        elapsed = STAR_DWT_CYCCNT;
        descriptor->function();
        elapsed = STAR_DWT_CYCCNT - elapsed;
        if (elapsed >= overhead) { elapsed -= overhead; }
        else { g_star_mixed_region_results.error_flags |= 2U; }
        total += elapsed;
        if (elapsed > maximum) { maximum = elapsed; }
    }
    point->completed_samples = STAR_SAMPLES;
    point->mean_execution_us_x1000 =
        ToMicrosecondsX1000((uint32_t)(total / STAR_SAMPLES));
    point->max_execution_us_x1000 = ToMicrosecondsX1000(maximum);
}

int main(void)
{
    uint32_t index;
    STAR_DEMCR |= (1UL << 24U);
    STAR_DWT_CYCCNT = 0U;
    STAR_DWT_CTRL |= 1U;
    g_star_mixed_region_results.point_count = STAR_POINT_COUNT;
    g_star_mixed_region_results.sample_count = STAR_SAMPLES;
    g_star_mixed_region_results.measurement_overhead_cycles = MeasureOverhead();
    for (index = 0U; index < STAR_POINT_COUNT; ++index)
    {
        MeasurePoint(index);
    }
    g_star_mixed_region_complete =
        (g_star_mixed_region_results.error_flags == 0U) ? 1U : 2U;
    for (;;) { __asm__ volatile ("nop"); }
}
