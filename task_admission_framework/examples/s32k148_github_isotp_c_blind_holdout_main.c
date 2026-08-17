#include "github_isotp_c_blind_holdout.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;

#define STAR_DEMCR       (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL    (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT  (*(volatile uint32_t *)0xE0001004UL)
#define STAR_POINT_COUNT (2U)
#define STAR_SAMPLE_COUNT (40U)
#define STAR_WARMUP_COUNT (8U)
#define STAR_CORE_HZ      (48000000U)

typedef enum
{
    STAR_ISOTP_TASK_REASSEMBLY = 0,
    STAR_ISOTP_TASK_ERROR_AGING = 1
} StarIsotpTaskId;

typedef void (*StarTaskFunction)(void);

typedef struct
{
    StarTaskFunction function;
    StarIsotpTaskId task_id;
} StarTaskDescriptor;

typedef struct
{
    uint32_t task_id;
    uint32_t completed_samples;
    uint32_t mean_execution_us_x1000;
    uint32_t max_execution_us_x1000;
} StarIsotpPoint;

typedef struct
{
    uint32_t point_count;
    uint32_t sample_count;
    uint32_t measurement_overhead_cycles;
    uint32_t error_flags;
    StarIsotpPoint points[STAR_POINT_COUNT];
} StarIsotpResults;

volatile uint32_t g_star_github_isotp_complete;
volatile uint32_t g_star_github_isotp_current;
volatile StarIsotpResults g_star_github_isotp_results;

static const StarTaskDescriptor s_tasks[STAR_POINT_COUNT] =
{
    {
        StarTask_IsotpConsecutiveFrameReassembly_10ms,
        STAR_ISOTP_TASK_REASSEMBLY
    },
    {
        StarTask_IsotpErrorAging_20ms,
        STAR_ISOTP_TASK_ERROR_AGING
    }
};

static uint32_t StarCyclesToUsX1000(uint32_t cycles)
{
    const uint64_t scaled_cycles = (uint64_t)cycles * 1000000000ULL;
    return (uint32_t)(scaled_cycles / STAR_CORE_HZ);
}

static uint32_t StarMeasureOverhead(void)
{
    uint32_t index;
    uint32_t minimum_cycles = 0xFFFFFFFFUL;

    for (index = 0U; index < 64U; ++index)
    {
        const uint32_t start_cycles = STAR_DWT_CYCCNT;
        const uint32_t elapsed_cycles = STAR_DWT_CYCCNT - start_cycles;

        if (elapsed_cycles < minimum_cycles)
        {
            minimum_cycles = elapsed_cycles;
        }
    }

    return minimum_cycles;
}

static void StarMeasureTask(uint32_t point_index)
{
    volatile StarIsotpPoint * const point =
        &g_star_github_isotp_results.points[point_index];
    uint64_t total_cycles = 0ULL;
    uint32_t maximum_cycles = 0U;
    uint32_t sample_index;

    point->task_id = (uint32_t)s_tasks[point_index].task_id;
    g_star_github_isotp_current = point_index;

    for (sample_index = 0U;
         sample_index < STAR_WARMUP_COUNT;
         ++sample_index)
    {
        StarGithubIsotp_Initialize();
        s_tasks[point_index].function();
    }

    for (sample_index = 0U;
         sample_index < STAR_SAMPLE_COUNT;
         ++sample_index)
    {
        uint32_t elapsed_cycles;
        const uint32_t overhead_cycles =
            g_star_github_isotp_results.measurement_overhead_cycles;

        StarGithubIsotp_Initialize();
        elapsed_cycles = STAR_DWT_CYCCNT;
        s_tasks[point_index].function();
        elapsed_cycles = STAR_DWT_CYCCNT - elapsed_cycles;

        if (elapsed_cycles >= overhead_cycles)
        {
            elapsed_cycles -= overhead_cycles;
        }
        else
        {
            g_star_github_isotp_results.error_flags |= 2U;
        }

        total_cycles += elapsed_cycles;
        if (elapsed_cycles > maximum_cycles)
        {
            maximum_cycles = elapsed_cycles;
        }
    }

    point->completed_samples = STAR_SAMPLE_COUNT;
    point->mean_execution_us_x1000 = StarCyclesToUsX1000(
        (uint32_t)(total_cycles / STAR_SAMPLE_COUNT)
    );
    point->max_execution_us_x1000 =
        StarCyclesToUsX1000(maximum_cycles);
}

int main(void)
{
    uint32_t point_index;

    STAR_DEMCR |= (1UL << 24U);
    STAR_DWT_CYCCNT = 0U;
    STAR_DWT_CTRL |= 1U;

    g_star_github_isotp_results.point_count = STAR_POINT_COUNT;
    g_star_github_isotp_results.sample_count = STAR_SAMPLE_COUNT;
    g_star_github_isotp_results.measurement_overhead_cycles =
        StarMeasureOverhead();

    for (point_index = 0U;
         point_index < STAR_POINT_COUNT;
         ++point_index)
    {
        StarMeasureTask(point_index);
    }

    g_star_github_isotp_complete =
        (g_star_github_isotp_results.error_flags == 0U) ? 1U : 2U;

    for (;;)
    {
        __asm__ volatile ("nop");
    }
}
