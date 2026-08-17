#include "basic_gap_calibration.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;

#define STAR_DEMCR       (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL    (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT  (*(volatile uint32_t *)0xE0001004UL)
#define STAR_POINT_COUNT (9U)
#define STAR_SAMPLES     (40U)
#define STAR_WARMUPS     (8U)
#define STAR_CORE_HZ     (48000000U)

typedef void (*StarGapTask)(void);

typedef struct
{
    uint32_t family_id;
    uint32_t iterations;
    uint32_t completed_samples;
    uint32_t mean_execution_us_x1000;
    uint32_t max_execution_us_x1000;
} StarGapPoint;

typedef struct
{
    uint32_t point_count;
    uint32_t sample_count;
    uint32_t measurement_overhead_cycles;
    uint32_t error_flags;
    StarGapPoint points[STAR_POINT_COUNT];
} StarGapResults;

volatile uint32_t g_star_gap_complete;
volatile uint32_t g_star_gap_current;
volatile StarGapResults g_star_gap_results;

static const StarGapTask s_tasks[STAR_POINT_COUNT] =
{
    StarGap_Arithmetic8, StarGap_Arithmetic16, StarGap_Arithmetic64,
    StarGap_MaskedDivide8, StarGap_MaskedDivide16, StarGap_MaskedDivide64,
    StarGap_MaskedModulo8, StarGap_MaskedModulo16, StarGap_MaskedModulo64
};

static const uint32_t s_iterations[3] = {8U, 16U, 64U};

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

static void MeasurePoint(uint32_t point_id)
{
    volatile StarGapPoint * const point = &g_star_gap_results.points[point_id];
    uint64_t total = 0ULL;
    uint32_t maximum = 0U;
    uint32_t sample;
    point->family_id = point_id / 3U;
    point->iterations = s_iterations[point_id % 3U];
    g_star_gap_current = point_id;
    for (sample = 0U; sample < STAR_WARMUPS; ++sample)
    {
        StarGap_Initialize();
        s_tasks[point_id]();
    }
    for (sample = 0U; sample < STAR_SAMPLES; ++sample)
    {
        uint32_t elapsed;
        const uint32_t overhead = g_star_gap_results.measurement_overhead_cycles;
        StarGap_Initialize();
        elapsed = STAR_DWT_CYCCNT;
        s_tasks[point_id]();
        elapsed = STAR_DWT_CYCCNT - elapsed;
        if (elapsed >= overhead) { elapsed -= overhead; }
        else { g_star_gap_results.error_flags |= 2U; }
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
    uint32_t point_id;
    STAR_DEMCR |= (1UL << 24U);
    STAR_DWT_CYCCNT = 0U;
    STAR_DWT_CTRL |= 1U;
    g_star_gap_results.point_count = STAR_POINT_COUNT;
    g_star_gap_results.sample_count = STAR_SAMPLES;
    g_star_gap_results.measurement_overhead_cycles = MeasureOverhead();
    for (point_id = 0U; point_id < STAR_POINT_COUNT; ++point_id)
    {
        MeasurePoint(point_id);
    }
    g_star_gap_complete =
        (g_star_gap_results.error_flags == 0U) ? 1U : 2U;
    for (;;) { __asm__ volatile ("nop"); }
}
