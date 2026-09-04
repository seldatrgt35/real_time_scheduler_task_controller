#include "automotive_branch_v10_task.h"
typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;
#define DEMCR (*(volatile uint32_t *)0xE000EDFCUL)
#define DWT_CTRL (*(volatile uint32_t *)0xE0001000UL)
#define DWT_CYCCNT (*(volatile uint32_t *)0xE0001004UL)
#define LMEM_PCCCR (*(volatile uint32_t *)0xE0082000UL)
#define LMEM_ENCACHE (0x00000001UL)
#define LMEM_INVW0 (0x01000000UL)
#define LMEM_INVW1 (0x04000000UL)
#define LMEM_GO (0x80000000UL)
#define SAMPLES (40U)
#define WARMUPS (8U)
typedef struct { uint32_t completed_samples; uint32_t measurement_overhead_cycles; uint32_t error_flags; uint32_t mean_execution_cycles; uint32_t max_execution_cycles; uint32_t lmem_pcccr_initial; uint32_t lmem_pcccr_active; } StarBranchV10Results;
volatile uint32_t g_star_branch_v10_complete;
volatile StarBranchV10Results g_star_branch_v10_results;
static void EnableCodeCache(void) { LMEM_PCCCR = LMEM_INVW0 | LMEM_INVW1 | LMEM_GO | LMEM_ENCACHE; while ((LMEM_PCCCR & LMEM_GO) != 0U) { } LMEM_PCCCR &= ~(LMEM_INVW0 | LMEM_INVW1); __asm__ volatile ("dsb\n\tisb" ::: "memory"); }
static uint32_t MeasureOverhead(void) { uint32_t i; uint32_t minimum = 0xFFFFFFFFUL; for (i = 0U; i < 64U; ++i) { const uint32_t start = DWT_CYCCNT; const uint32_t elapsed = DWT_CYCCNT - start; if (elapsed < minimum) { minimum = elapsed; } } return minimum; }
int main(void) { uint32_t sample; uint64_t total = 0ULL; uint32_t maximum = 0U; DEMCR |= 1UL << 24U; DWT_CYCCNT = 0U; DWT_CTRL |= 1U; g_star_branch_v10_complete = 0U; g_star_branch_v10_results.error_flags = 0U; g_star_branch_v10_results.lmem_pcccr_initial = LMEM_PCCCR; EnableCodeCache(); g_star_branch_v10_results.lmem_pcccr_active = LMEM_PCCCR; g_star_branch_v10_results.measurement_overhead_cycles = MeasureOverhead(); for (sample = 0U; sample < WARMUPS; ++sample) { BranchV10_Initialize(); RedundantPedalFaultArbitration_Task5ms(); } for (sample = 0U; sample < SAMPLES; ++sample) { uint32_t elapsed; BranchV10_Initialize(); elapsed = DWT_CYCCNT; RedundantPedalFaultArbitration_Task5ms(); elapsed = DWT_CYCCNT - elapsed; if (elapsed >= g_star_branch_v10_results.measurement_overhead_cycles) { elapsed -= g_star_branch_v10_results.measurement_overhead_cycles; } else { g_star_branch_v10_results.error_flags |= 1U; } total += elapsed; if (elapsed > maximum) { maximum = elapsed; } } g_star_branch_v10_results.completed_samples = SAMPLES; g_star_branch_v10_results.mean_execution_cycles = (uint32_t)(total / SAMPLES); g_star_branch_v10_results.max_execution_cycles = maximum; g_star_branch_v10_complete = (g_star_branch_v10_results.error_flags == 0U) ? 1U : 2U; for (;;) { __asm__ volatile ("nop"); } }
