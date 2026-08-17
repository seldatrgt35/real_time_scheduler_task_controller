/* S32K148 DWT harness for the blind DTC snapshot packing task. */
#include "automotive_dtc_snapshot_blind_holdout.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;

#define STAR_DEMCR       (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL    (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT  (*(volatile uint32_t *)0xE0001004UL)
#define STAR_SAMPLES     (40U)
#define STAR_WARMUPS     (8U)
#define STAR_CORE_HZ     (48000000U)

typedef struct
{
    uint32_t iterations;
    uint32_t completed_samples;
    uint32_t measurement_overhead_cycles;
    uint32_t error_flags;
    uint32_t mean_execution_us_x1000;
    uint32_t max_execution_us_x1000;
} StarDtcSnapshotBlindResults;

volatile uint32_t g_star_dtc_snapshot_blind_complete;
volatile StarDtcSnapshotBlindResults g_star_dtc_snapshot_blind_results;

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

int main(void)
{
    uint64_t total = 0ULL;
    uint32_t maximum = 0U;
    uint32_t sample;

    STAR_DEMCR |= (1UL << 24U);
    STAR_DWT_CYCCNT = 0U;
    STAR_DWT_CTRL |= 1U;

    g_star_dtc_snapshot_blind_results.iterations = 16U;
    g_star_dtc_snapshot_blind_results.measurement_overhead_cycles =
        MeasureOverhead();

    for (sample = 0U; sample < STAR_WARMUPS; ++sample)
    {
        StarAutomotiveDtcSnapshot_Initialize();
        StarTask_DtcSnapshotPack_20ms();
    }

    for (sample = 0U; sample < STAR_SAMPLES; ++sample)
    {
        uint32_t elapsed;
        const uint32_t overhead =
            g_star_dtc_snapshot_blind_results.measurement_overhead_cycles;

        StarAutomotiveDtcSnapshot_Initialize();
        elapsed = STAR_DWT_CYCCNT;
        StarTask_DtcSnapshotPack_20ms();
        elapsed = STAR_DWT_CYCCNT - elapsed;
        if (elapsed >= overhead)
        {
            elapsed -= overhead;
        }
        else
        {
            g_star_dtc_snapshot_blind_results.error_flags |= 2U;
        }
        total += elapsed;
        if (elapsed > maximum)
        {
            maximum = elapsed;
        }
    }

    g_star_dtc_snapshot_blind_results.completed_samples = STAR_SAMPLES;
    g_star_dtc_snapshot_blind_results.mean_execution_us_x1000 =
        ToMicrosecondsX1000((uint32_t)(total / STAR_SAMPLES));
    g_star_dtc_snapshot_blind_results.max_execution_us_x1000 =
        ToMicrosecondsX1000(maximum);
    g_star_dtc_snapshot_blind_complete =
        (g_star_dtc_snapshot_blind_results.error_flags == 0U) ? 1U : 2U;

    for (;;)
    {
        __asm__ volatile ("nop");
    }
}
