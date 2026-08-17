/* S32K148 DWT comparison of sparse and dense paths through one DTC task. */
#include "automotive_dtc_snapshot_blind_holdout.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;

#define STAR_DEMCR         (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL      (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT    (*(volatile uint32_t *)0xE0001004UL)
#define STAR_SCENARIO_COUNT (2U)
#define STAR_SAMPLES        (40U)
#define STAR_WARMUPS        (8U)
#define STAR_CORE_HZ        (48000000U)

typedef void (*ScenarioInitializeFunction)(void);

typedef struct
{
    uint32_t scenario_id;
    uint32_t accepted_records;
    uint32_t completed_samples;
    uint32_t mean_execution_us_x1000;
    uint32_t max_execution_us_x1000;
} StarDtcPathPoint;

typedef struct
{
    uint32_t point_count;
    uint32_t sample_count;
    uint32_t measurement_overhead_cycles;
    uint32_t error_flags;
    StarDtcPathPoint points[STAR_SCENARIO_COUNT];
} StarDtcPathResults;

typedef struct
{
    ScenarioInitializeFunction initialize;
    uint32_t accepted_records;
} StarDtcPathDescriptor;

volatile uint32_t g_star_dtc_path_complete;
volatile uint32_t g_star_dtc_path_current;
volatile StarDtcPathResults g_star_dtc_path_results;

static const StarDtcPathDescriptor s_scenarios[STAR_SCENARIO_COUNT] =
{
    {StarAutomotiveDtcSnapshot_Initialize, 3U},
    {StarAutomotiveDtcSnapshot_InitializeDense, 16U}
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

static void MeasureScenario(uint32_t scenario_id)
{
    const StarDtcPathDescriptor * const descriptor = &s_scenarios[scenario_id];
    volatile StarDtcPathPoint * const point =
        &g_star_dtc_path_results.points[scenario_id];
    uint64_t total = 0ULL;
    uint32_t maximum = 0U;
    uint32_t sample;

    point->scenario_id = scenario_id;
    point->accepted_records = descriptor->accepted_records;
    g_star_dtc_path_current = scenario_id;

    for (sample = 0U; sample < STAR_WARMUPS; ++sample)
    {
        descriptor->initialize();
        StarTask_DtcSnapshotPack_20ms();
    }

    for (sample = 0U; sample < STAR_SAMPLES; ++sample)
    {
        uint32_t elapsed;
        const uint32_t overhead =
            g_star_dtc_path_results.measurement_overhead_cycles;

        descriptor->initialize();
        elapsed = STAR_DWT_CYCCNT;
        StarTask_DtcSnapshotPack_20ms();
        elapsed = STAR_DWT_CYCCNT - elapsed;
        if (elapsed >= overhead)
        {
            elapsed -= overhead;
        }
        else
        {
            g_star_dtc_path_results.error_flags |= 2U;
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
    uint32_t scenario_id;

    STAR_DEMCR |= (1UL << 24U);
    STAR_DWT_CYCCNT = 0U;
    STAR_DWT_CTRL |= 1U;

    g_star_dtc_path_results.point_count = STAR_SCENARIO_COUNT;
    g_star_dtc_path_results.sample_count = STAR_SAMPLES;
    g_star_dtc_path_results.measurement_overhead_cycles = MeasureOverhead();

    for (scenario_id = 0U; scenario_id < STAR_SCENARIO_COUNT; ++scenario_id)
    {
        MeasureScenario(scenario_id);
    }

    g_star_dtc_path_complete =
        (g_star_dtc_path_results.error_flags == 0U) ? 1U : 2U;
    for (;;)
    {
        __asm__ volatile ("nop");
    }
}
