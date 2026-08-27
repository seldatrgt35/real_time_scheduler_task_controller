#include "automotive_holdout_v4_tasks.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;

#define STAR_DEMCR       (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL    (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT  (*(volatile uint32_t *)0xE0001004UL)
#define STAR_POINT_COUNT (3U)
#define STAR_SAMPLES     (40U)
#define STAR_WARMUPS     (8U)
#define STAR_CORE_HZ     (48000000U)

typedef struct
{
    uint32_t task_id;
    uint32_t completed_samples;
    uint32_t mean_execution_us_x1000;
    uint32_t max_execution_us_x1000;
} StarHoldoutV4Point;

typedef struct
{
    uint32_t point_count;
    uint32_t sample_count;
    uint32_t measurement_overhead_cycles;
    uint32_t error_flags;
    StarHoldoutV4Point points[STAR_POINT_COUNT];
} StarHoldoutV4Results;

volatile uint32_t g_star_holdout_v4_complete;
volatile uint32_t g_star_holdout_v4_current;
volatile StarHoldoutV4Results g_star_holdout_v4_results;

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
        if (elapsed < minimum)
        {
            minimum = elapsed;
        }
    }
    return minimum;
}

#define STAR_MEASURE_TASK(task_index, task_call)                              \
    do                                                                        \
    {                                                                         \
        uint32_t sample;                                                      \
        uint64_t total = 0ULL;                                                \
        uint32_t maximum = 0U;                                                \
        g_star_holdout_v4_current = (task_index) + 1U;                        \
        for (sample = 0U; sample < STAR_WARMUPS; ++sample)                    \
        {                                                                     \
            AutomotiveHoldoutV4_Initialize();                                \
            task_call();                                                      \
        }                                                                     \
        for (sample = 0U; sample < STAR_SAMPLES; ++sample)                    \
        {                                                                     \
            uint32_t elapsed;                                                 \
            const uint32_t overhead =                                         \
                g_star_holdout_v4_results.measurement_overhead_cycles;        \
            AutomotiveHoldoutV4_Initialize();                                \
            elapsed = STAR_DWT_CYCCNT;                                        \
            task_call();                                                      \
            elapsed = STAR_DWT_CYCCNT - elapsed;                              \
            if (elapsed >= overhead)                                          \
            {                                                                 \
                elapsed -= overhead;                                          \
            }                                                                 \
            else                                                              \
            {                                                                 \
                g_star_holdout_v4_results.error_flags |= 2U;                  \
            }                                                                 \
            total += elapsed;                                                 \
            if (elapsed > maximum)                                            \
            {                                                                 \
                maximum = elapsed;                                            \
            }                                                                 \
        }                                                                     \
        g_star_holdout_v4_results.points[(task_index)].task_id = (task_index);\
        g_star_holdout_v4_results.points[(task_index)].completed_samples =    \
            STAR_SAMPLES;                                                     \
        g_star_holdout_v4_results.points[(task_index)].                       \
            mean_execution_us_x1000 =                                         \
                ToMicrosecondsX1000((uint32_t)(total / STAR_SAMPLES));        \
        g_star_holdout_v4_results.points[(task_index)].                       \
            max_execution_us_x1000 = ToMicrosecondsX1000(maximum);            \
    } while (0)

int main(void)
{
    STAR_DEMCR |= 1UL << 24U;
    STAR_DWT_CYCCNT = 0U;
    STAR_DWT_CTRL |= 1U;
    g_star_holdout_v4_results.point_count = STAR_POINT_COUNT;
    g_star_holdout_v4_results.sample_count = STAR_SAMPLES;
    g_star_holdout_v4_results.error_flags = 0U;
    g_star_holdout_v4_complete = 0U;
    g_star_holdout_v4_current = 0U;
    g_star_holdout_v4_results.measurement_overhead_cycles = MeasureOverhead();

    STAR_MEASURE_TASK(0U, DcLinkRippleMonitor_Task1ms);
    STAR_MEASURE_TASK(1U, NetworkSignalSupervision_Task10ms);
    STAR_MEASURE_TASK(2U, InjectorPulseCompensation_Task5ms);
    g_star_holdout_v4_complete =
        (g_star_holdout_v4_results.error_flags == 0U) ? 1U : 2U;
    g_star_holdout_v4_current = 3U;
    for (;;)
    {
        __asm__ volatile ("nop");
    }
}
