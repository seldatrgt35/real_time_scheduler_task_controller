#include "mixed_plausibility_calibration.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;

#define STAR_DEMCR       (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL    (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT  (*(volatile uint32_t *)0xE0001004UL)
#define STAR_POINT_COUNT (3U)
#define STAR_SAMPLES     (40U)
#define STAR_WARMUPS     (8U)
#define STAR_CORE_HZ     (48000000U)

typedef void (*PlausibilityFunction)(void);
typedef struct { uint32_t iterations; uint32_t completed_samples; uint32_t mean_execution_us_x1000; uint32_t max_execution_us_x1000; } PlausibilityPoint;
typedef struct { uint32_t point_count; uint32_t sample_count; uint32_t measurement_overhead_cycles; uint32_t error_flags; PlausibilityPoint points[STAR_POINT_COUNT]; } PlausibilityResults;
typedef struct { PlausibilityFunction function; uint32_t iterations; } PlausibilityDescriptor;

volatile uint32_t g_star_mixed_plausibility_complete;
volatile uint32_t g_star_mixed_plausibility_current;
volatile PlausibilityResults g_star_mixed_plausibility_results;

static const PlausibilityDescriptor g_points[STAR_POINT_COUNT] = {
    {MixedPlausibilityCalibration_8, 8U},
    {MixedPlausibilityCalibration_16, 16U},
    {MixedPlausibilityCalibration_32, 32U}
};

static uint32_t ToUsX1000(uint32_t cycles) { return (uint32_t)(((uint64_t)cycles * 1000000000ULL) / STAR_CORE_HZ); }
static uint32_t Overhead(void) { uint32_t i, minimum = 0xFFFFFFFFUL; for (i = 0U; i < 64U; ++i) { const uint32_t start = STAR_DWT_CYCCNT; const uint32_t elapsed = STAR_DWT_CYCCNT - start; if (elapsed < minimum) { minimum = elapsed; } } return minimum; }
static void Measure(uint32_t id) { volatile PlausibilityPoint * const point = &g_star_mixed_plausibility_results.points[id]; uint64_t total = 0ULL; uint32_t maximum = 0U, sample; point->iterations = g_points[id].iterations; g_star_mixed_plausibility_current = id; for (sample = 0U; sample < STAR_WARMUPS; ++sample) { MixedPlausibilityCalibration_Initialize(); g_points[id].function(); } for (sample = 0U; sample < STAR_SAMPLES; ++sample) { uint32_t elapsed, overhead = g_star_mixed_plausibility_results.measurement_overhead_cycles; MixedPlausibilityCalibration_Initialize(); elapsed = STAR_DWT_CYCCNT; g_points[id].function(); elapsed = STAR_DWT_CYCCNT - elapsed; if (elapsed >= overhead) { elapsed -= overhead; } else { g_star_mixed_plausibility_results.error_flags |= 2U; } total += elapsed; if (elapsed > maximum) { maximum = elapsed; } } point->completed_samples = STAR_SAMPLES; point->mean_execution_us_x1000 = ToUsX1000((uint32_t)(total / STAR_SAMPLES)); point->max_execution_us_x1000 = ToUsX1000(maximum); }

int main(void) { uint32_t index; STAR_DEMCR |= (1UL << 24U); STAR_DWT_CYCCNT = 0U; STAR_DWT_CTRL |= 1U; g_star_mixed_plausibility_results.point_count = STAR_POINT_COUNT; g_star_mixed_plausibility_results.sample_count = STAR_SAMPLES; g_star_mixed_plausibility_results.measurement_overhead_cycles = Overhead(); for (index = 0U; index < STAR_POINT_COUNT; ++index) { Measure(index); } g_star_mixed_plausibility_complete = (g_star_mixed_plausibility_results.error_flags == 0U) ? 1U : 2U; for (;;) { __asm__ volatile ("nop"); } }
