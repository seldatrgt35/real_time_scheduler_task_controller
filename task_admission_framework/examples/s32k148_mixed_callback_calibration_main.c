#include "mixed_callback_calibration.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;

#define STAR_DEMCR       (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL    (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT  (*(volatile uint32_t *)0xE0001004UL)
#define STAR_POINT_COUNT (6U)
#define STAR_SAMPLES     (40U)
#define STAR_WARMUPS     (8U)
#define STAR_CORE_HZ     (48000000U)

typedef void (*CallbackFunction)(void);
typedef struct { uint32_t family_id; uint32_t iterations; uint32_t completed_samples; uint32_t mean_execution_us_x1000; uint32_t max_execution_us_x1000; } CallbackPoint;
typedef struct { uint32_t point_count; uint32_t sample_count; uint32_t measurement_overhead_cycles; uint32_t error_flags; CallbackPoint points[STAR_POINT_COUNT]; } CallbackResults;
typedef struct { CallbackFunction function; uint32_t family_id; uint32_t iterations; } CallbackDescriptor;

volatile uint32_t g_star_mixed_callback_complete;
volatile uint32_t g_star_mixed_callback_current;
volatile CallbackResults g_star_mixed_callback_results;

static const CallbackDescriptor g_points[STAR_POINT_COUNT] = {
    {MixedCallback_8, 0U, 8U}, {MixedCallback_16, 0U, 16U},
    {MixedCallback_32, 0U, 32U}, {MixedCallbackPack_8, 1U, 8U},
    {MixedCallbackPack_16, 1U, 16U}, {MixedCallbackPack_32, 1U, 32U}
};

static uint32_t ToUsX1000(uint32_t cycles) { return (uint32_t)(((uint64_t)cycles * 1000000000ULL) / STAR_CORE_HZ); }
static uint32_t Overhead(void) { uint32_t i, minimum = 0xFFFFFFFFUL; for (i = 0U; i < 64U; ++i) { const uint32_t start = STAR_DWT_CYCCNT; const uint32_t elapsed = STAR_DWT_CYCCNT - start; if (elapsed < minimum) { minimum = elapsed; } } return minimum; }
static void Measure(uint32_t id) { volatile CallbackPoint * const point = &g_star_mixed_callback_results.points[id]; uint64_t total = 0ULL; uint32_t maximum = 0U, sample; point->family_id = g_points[id].family_id; point->iterations = g_points[id].iterations; g_star_mixed_callback_current = id; for (sample = 0U; sample < STAR_WARMUPS; ++sample) { MixedCallbackCalibration_Initialize(); g_points[id].function(); } for (sample = 0U; sample < STAR_SAMPLES; ++sample) { uint32_t elapsed, overhead = g_star_mixed_callback_results.measurement_overhead_cycles; MixedCallbackCalibration_Initialize(); elapsed = STAR_DWT_CYCCNT; g_points[id].function(); elapsed = STAR_DWT_CYCCNT - elapsed; if (elapsed >= overhead) { elapsed -= overhead; } else { g_star_mixed_callback_results.error_flags |= 2U; } total += elapsed; if (elapsed > maximum) { maximum = elapsed; } } point->completed_samples = STAR_SAMPLES; point->mean_execution_us_x1000 = ToUsX1000((uint32_t)(total / STAR_SAMPLES)); point->max_execution_us_x1000 = ToUsX1000(maximum); }

int main(void) { uint32_t index; STAR_DEMCR |= (1UL << 24U); STAR_DWT_CYCCNT = 0U; STAR_DWT_CTRL |= 1U; g_star_mixed_callback_results.point_count = STAR_POINT_COUNT; g_star_mixed_callback_results.sample_count = STAR_SAMPLES; g_star_mixed_callback_results.measurement_overhead_cycles = Overhead(); for (index = 0U; index < STAR_POINT_COUNT; ++index) { Measure(index); } g_star_mixed_callback_complete = (g_star_mixed_callback_results.error_flags == 0U) ? 1U : 2U; for (;;) { __asm__ volatile ("nop"); } }
