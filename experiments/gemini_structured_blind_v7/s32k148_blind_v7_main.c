#include "automotive_blind_v7_tasks.h"

typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;

#define STAR_DEMCR      (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL   (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT (*(volatile uint32_t *)0xE0001004UL)
#define STAR_LMEM_PCCCR (*(volatile uint32_t *)0xE0082000UL)
#define STAR_LMEM_ENCACHE (0x00000001UL)
#define STAR_LMEM_INVW0   (0x01000000UL)
#define STAR_LMEM_INVW1   (0x04000000UL)
#define STAR_LMEM_GO      (0x80000000UL)
#define STAR_SAMPLES (40U)
#define STAR_WARMUPS (8U)
#define STAR_TASK_COUNT (3U)

typedef void (*StarTaskFunction)(void);

typedef struct
{
    uint32_t task_id;
    uint32_t completed_samples;
    uint32_t mean_execution_cycles;
    uint32_t max_execution_cycles;
} StarBlindV7Point;

typedef struct
{
    uint32_t point_count;
    uint32_t sample_count;
    uint32_t measurement_overhead_cycles;
    uint32_t error_flags;
    uint32_t lmem_pcccr_initial;
    uint32_t lmem_pcccr_active;
    StarBlindV7Point points[STAR_TASK_COUNT];
} StarBlindV7Results;

volatile uint32_t g_star_blind_v7_complete;
volatile uint32_t g_star_blind_v7_current;
volatile StarBlindV7Results g_star_blind_v7_results;

static const StarTaskFunction s_tasks[STAR_TASK_COUNT] = {
    SensorVoting_Task10ms,
    NetworkDebounce_Task5ms,
    MotorThermalProtection_Task20ms
};

static void EnableCodeCache(void)
{
    STAR_LMEM_PCCCR = STAR_LMEM_INVW0 | STAR_LMEM_INVW1 |
        STAR_LMEM_GO | STAR_LMEM_ENCACHE;
    while ((STAR_LMEM_PCCCR & STAR_LMEM_GO) != 0U) { }
    STAR_LMEM_PCCCR &= ~(STAR_LMEM_INVW0 | STAR_LMEM_INVW1);
    __asm__ volatile ("dsb\n\tisb" ::: "memory");
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

int main(void)
{
    uint32_t task_id;
    STAR_DEMCR |= 1UL << 24U;
    STAR_DWT_CYCCNT = 0U;
    STAR_DWT_CTRL |= 1U;
    g_star_blind_v7_complete = 0U;
    g_star_blind_v7_results.point_count = STAR_TASK_COUNT;
    g_star_blind_v7_results.sample_count = STAR_SAMPLES;
    g_star_blind_v7_results.error_flags = 0U;
    g_star_blind_v7_results.lmem_pcccr_initial = STAR_LMEM_PCCCR;
    EnableCodeCache();
    g_star_blind_v7_results.lmem_pcccr_active = STAR_LMEM_PCCCR;
    g_star_blind_v7_results.measurement_overhead_cycles = MeasureOverhead();
    for (task_id = 0U; task_id < STAR_TASK_COUNT; ++task_id)
    {
        uint32_t sample;
        uint64_t total = 0ULL;
        uint32_t maximum = 0U;
        g_star_blind_v7_current = task_id;
        for (sample = 0U; sample < STAR_WARMUPS; ++sample)
        {
            BlindV7_Initialize(task_id);
            s_tasks[task_id]();
        }
        for (sample = 0U; sample < STAR_SAMPLES; ++sample)
        {
            uint32_t elapsed;
            BlindV7_Initialize(task_id);
            elapsed = STAR_DWT_CYCCNT;
            s_tasks[task_id]();
            elapsed = STAR_DWT_CYCCNT - elapsed;
            if (elapsed >= g_star_blind_v7_results.measurement_overhead_cycles)
            {
                elapsed -= g_star_blind_v7_results.measurement_overhead_cycles;
            }
            else
            {
                g_star_blind_v7_results.error_flags |= 1U;
            }
            total += elapsed;
            if (elapsed > maximum) { maximum = elapsed; }
        }
        g_star_blind_v7_results.points[task_id].task_id = task_id;
        g_star_blind_v7_results.points[task_id].completed_samples = STAR_SAMPLES;
        g_star_blind_v7_results.points[task_id].mean_execution_cycles =
            (uint32_t)(total / STAR_SAMPLES);
        g_star_blind_v7_results.points[task_id].max_execution_cycles = maximum;
    }
    g_star_blind_v7_current = STAR_TASK_COUNT;
    g_star_blind_v7_complete =
        (g_star_blind_v7_results.error_flags == 0U) ? 1U : 2U;
    for (;;) { __asm__ volatile ("nop"); }
}
