/* S32K148 DWT harness for the blind iso14229-derived automotive suite. */
#include "iso14229_real_automotive_blind_suite.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;

#define STAR_DEMCR       (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL    (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT  (*(volatile uint32_t *)0xE0001004UL)
#define STAR_POINT_COUNT (4U)
#define STAR_SAMPLES     (40U)
#define STAR_WARMUPS     (8U)
#define STAR_CORE_HZ     (48000000U)

typedef void (*AutomotiveTaskFunction)(void);

typedef struct
{
    uint32_t task_id;
    uint32_t completed_samples;
    uint32_t mean_execution_us_x1000;
    uint32_t max_execution_us_x1000;
} Iso14229RealTaskPoint;

typedef struct
{
    uint32_t point_count;
    uint32_t sample_count;
    uint32_t measurement_overhead_cycles;
    uint32_t error_flags;
    Iso14229RealTaskPoint points[STAR_POINT_COUNT];
} Iso14229RealTaskResults;

volatile uint32_t g_star_iso14229_real_complete;
volatile uint32_t g_star_iso14229_real_current;
volatile Iso14229RealTaskResults g_star_iso14229_real_results;

static const AutomotiveTaskFunction s_tasks[STAR_POINT_COUNT] =
{
    StarTask_UdsReadDidPack_10ms,
    StarTask_UdsAddressLengthDecode_20ms,
    StarTask_UdsTransferDataBlock_5ms,
    StarTask_UdsSecurityKeyValidate_20ms
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
        if (elapsed < minimum)
        {
            minimum = elapsed;
        }
    }
    return minimum;
}

static void MeasurePoint(uint32_t task_id)
{
    volatile Iso14229RealTaskPoint * const point =
        &g_star_iso14229_real_results.points[task_id];
    uint64_t total = 0ULL;
    uint32_t maximum = 0U;
    uint32_t sample;

    point->task_id = task_id;
    g_star_iso14229_real_current = task_id;
    for (sample = 0U; sample < STAR_WARMUPS; ++sample)
    {
        StarIso14229RealSuite_Initialize();
        s_tasks[task_id]();
    }
    for (sample = 0U; sample < STAR_SAMPLES; ++sample)
    {
        uint32_t elapsed;
        const uint32_t overhead =
            g_star_iso14229_real_results.measurement_overhead_cycles;
        StarIso14229RealSuite_Initialize();
        elapsed = STAR_DWT_CYCCNT;
        s_tasks[task_id]();
        elapsed = STAR_DWT_CYCCNT - elapsed;
        if (elapsed >= overhead)
        {
            elapsed -= overhead;
        }
        else
        {
            g_star_iso14229_real_results.error_flags |= 2U;
        }
        total += elapsed;
        if (elapsed > maximum)
        {
            maximum = elapsed;
        }
    }
    point->completed_samples = STAR_SAMPLES;
    point->mean_execution_us_x1000 =
        ToMicrosecondsX1000((uint32_t)(total / STAR_SAMPLES));
    point->max_execution_us_x1000 = ToMicrosecondsX1000(maximum);
}

int main(void)
{
    uint32_t task_id;
    STAR_DEMCR |= (1UL << 24U);
    STAR_DWT_CYCCNT = 0U;
    STAR_DWT_CTRL |= 1U;
    g_star_iso14229_real_results.point_count = STAR_POINT_COUNT;
    g_star_iso14229_real_results.sample_count = STAR_SAMPLES;
    g_star_iso14229_real_results.measurement_overhead_cycles = MeasureOverhead();
    for (task_id = 0U; task_id < STAR_POINT_COUNT; ++task_id)
    {
        MeasurePoint(task_id);
    }
    g_star_iso14229_real_complete =
        (g_star_iso14229_real_results.error_flags == 0U) ? 1U : 2U;
    for (;;)
    {
        __asm__ volatile ("nop");
    }
}
