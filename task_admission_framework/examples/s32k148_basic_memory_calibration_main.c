#include "basic_memory_calibration.h"
typedef __UINT32_TYPE__ uint32_t;
typedef __UINT64_TYPE__ uint64_t;
#define STAR_DEMCR (*(volatile uint32_t *)0xE000EDFCUL)
#define STAR_DWT_CTRL (*(volatile uint32_t *)0xE0001000UL)
#define STAR_DWT_CYCCNT (*(volatile uint32_t *)0xE0001004UL)
#define STAR_POINT_COUNT 12U
#define STAR_SAMPLES 40U
#define STAR_WARMUPS 8U
#define STAR_CORE_HZ 48000000U
typedef void (*StarMemoryTask)(void);
typedef struct {
  uint32_t family_id;
  uint32_t iterations;
  uint32_t completed_samples;
  uint32_t mean_execution_us_x1000;
  uint32_t max_execution_us_x1000;
} StarMemoryPoint;
typedef struct {
  uint32_t point_count;
  uint32_t sample_count;
  uint32_t measurement_overhead_cycles;
  uint32_t error_flags;
  StarMemoryPoint points[STAR_POINT_COUNT];
} StarMemoryResults;
volatile uint32_t g_star_memory_complete;
volatile uint32_t g_star_memory_current;
volatile StarMemoryResults g_star_memory_results;
static const StarMemoryTask s_tasks[STAR_POINT_COUNT] = {
    StarMemory_Sequential8, StarMemory_Sequential16, StarMemory_Sequential64,
    StarMemory_Random8,     StarMemory_Random16,     StarMemory_Random64,
    StarMemory_Copy8,       StarMemory_Copy16,       StarMemory_Copy64,
    StarMemory_Set8,        StarMemory_Set16,        StarMemory_Set64};
static const uint32_t s_iterations[3] = {8U, 16U, 64U};
static uint32_t ToUsX1000(uint32_t cycles) {
  return (uint32_t)(((uint64_t)cycles * 1000000000ULL) / STAR_CORE_HZ);
}
static uint32_t Overhead(void) {
  uint32_t i, min = 0xFFFFFFFFUL;
  for (i = 0U; i < 64U; ++i) {
    const uint32_t s = STAR_DWT_CYCCNT;
    const uint32_t e = STAR_DWT_CYCCNT - s;
    if (e < min) {
      min = e;
    }
  }
  return min;
}
static void Measure(uint32_t id) {
  volatile StarMemoryPoint *const p = &g_star_memory_results.points[id];
  uint64_t total = 0ULL;
  uint32_t max = 0U, s;
  p->family_id = id / 3U;
  p->iterations = s_iterations[id % 3U];
  g_star_memory_current = id;
  for (s = 0U; s < STAR_WARMUPS; ++s) {
    StarMemory_Initialize();
    s_tasks[id]();
  }
  for (s = 0U; s < STAR_SAMPLES; ++s) {
    uint32_t e;
    StarMemory_Initialize();
    e = STAR_DWT_CYCCNT;
    s_tasks[id]();
    e = STAR_DWT_CYCCNT - e;
    if (e >= g_star_memory_results.measurement_overhead_cycles) {
      e -= g_star_memory_results.measurement_overhead_cycles;
    } else {
      g_star_memory_results.error_flags |= 2U;
    }
    total += e;
    if (e > max) {
      max = e;
    }
  }
  p->completed_samples = STAR_SAMPLES;
  p->mean_execution_us_x1000 = ToUsX1000((uint32_t)(total / STAR_SAMPLES));
  p->max_execution_us_x1000 = ToUsX1000(max);
}
int main(void) {
  uint32_t id;
  STAR_DEMCR |= (1UL << 24U);
  STAR_DWT_CYCCNT = 0U;
  STAR_DWT_CTRL |= 1U;
  g_star_memory_results.point_count = STAR_POINT_COUNT;
  g_star_memory_results.sample_count = STAR_SAMPLES;
  g_star_memory_results.measurement_overhead_cycles = Overhead();
  for (id = 0U; id < STAR_POINT_COUNT; ++id) {
    Measure(id);
  }
  g_star_memory_complete = (g_star_memory_results.error_flags == 0U) ? 1U : 2U;
  for (;;) {
    __asm__ volatile("nop");
  }
}
