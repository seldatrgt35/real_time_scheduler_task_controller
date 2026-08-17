#include "basic_memory_calibration.h"

typedef __UINT32_TYPE__ uint32_t;
static uint32_t s_input[128];
static uint32_t s_output[128];
static volatile uint32_t s_sink;

void StarMemory_Initialize(void) {
  uint32_t index;
  for (index = 0U; index < 128U; ++index) {
    s_input[index] = index * 13U + 5U;
    s_output[index] = 0U;
  }
  s_sink = 0x13579BDFU;
}

void StarMemory_Sequential8(void) {
  uint32_t i;
  uint32_t v = s_sink;
  for (i = 0U; i < 8U; ++i) {
    v += s_input[i];
  }
  s_sink = v;
}
void StarMemory_Sequential16(void) {
  uint32_t i;
  uint32_t v = s_sink;
  for (i = 0U; i < 16U; ++i) {
    v += s_input[i];
  }
  s_sink = v;
}
void StarMemory_Sequential64(void) {
  uint32_t i;
  uint32_t v = s_sink;
  for (i = 0U; i < 64U; ++i) {
    v += s_input[i];
  }
  s_sink = v;
}

void StarMemory_Random8(void) {
  uint32_t i;
  uint32_t v = s_sink;
  for (i = 0U; i < 8U; ++i) {
    v += s_input[(i * 17U) & 127U];
  }
  s_sink = v;
}
void StarMemory_Random16(void) {
  uint32_t i;
  uint32_t v = s_sink;
  for (i = 0U; i < 16U; ++i) {
    v += s_input[(i * 17U) & 127U];
  }
  s_sink = v;
}
void StarMemory_Random64(void) {
  uint32_t i;
  uint32_t v = s_sink;
  for (i = 0U; i < 64U; ++i) {
    v += s_input[(i * 17U) & 127U];
  }
  s_sink = v;
}

void StarMemory_Copy8(void) {
  uint32_t i;
  for (i = 0U; i < 8U; ++i) {
    s_output[i] = s_input[i];
  }
  s_sink = s_output[7U];
}
void StarMemory_Copy16(void) {
  uint32_t i;
  for (i = 0U; i < 16U; ++i) {
    s_output[i] = s_input[i];
  }
  s_sink = s_output[15U];
}
void StarMemory_Copy64(void) {
  uint32_t i;
  for (i = 0U; i < 64U; ++i) {
    s_output[i] = s_input[i];
  }
  s_sink = s_output[63U];
}

void StarMemory_Set8(void) {
  uint32_t i;
  for (i = 0U; i < 8U; ++i) {
    s_output[i] = 0xA5A5A5A5U;
  }
  s_sink = s_output[7U];
}
void StarMemory_Set16(void) {
  uint32_t i;
  for (i = 0U; i < 16U; ++i) {
    s_output[i] = 0xA5A5A5A5U;
  }
  s_sink = s_output[15U];
}
void StarMemory_Set64(void) {
  uint32_t i;
  for (i = 0U; i < 64U; ++i) {
    s_output[i] = 0xA5A5A5A5U;
  }
  s_sink = s_output[63U];
}
