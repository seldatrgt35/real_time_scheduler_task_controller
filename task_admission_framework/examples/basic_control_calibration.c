#include "basic_control_calibration.h"

typedef __UINT32_TYPE__ uint32_t;
#if defined(__GNUC__) || defined(__clang__)
#define STAR_NOINLINE __attribute__((noinline))
#else
#define STAR_NOINLINE
#endif
typedef uint32_t (*StarTransform)(uint32_t);
static uint32_t s_input[128];
static volatile uint32_t s_sink;
static STAR_NOINLINE uint32_t AddThree(uint32_t value) { return value + 3U; }
static STAR_NOINLINE uint32_t XorMask(uint32_t value) { return value ^ 0x5AU; }
static const StarTransform s_transforms[2] = {AddThree, XorMask};

void StarControl_Initialize(void) {
  uint32_t index;
  for (index = 0U; index < 128U; ++index) {
    s_input[index] = index * 13U + 5U;
  }
  s_sink = 0x13579BDFU;
}

void StarControl_Branch8(void) {
  uint32_t i, v = s_sink;
  for (i = 0U; i < 8U; ++i) {
    if ((i & 1U) != 0U) {
      v += i;
    } else {
      v ^= i;
    }
  }
  s_sink = v;
}
void StarControl_Branch16(void) {
  uint32_t i, v = s_sink;
  for (i = 0U; i < 16U; ++i) {
    if ((i & 1U) != 0U) {
      v += i;
    } else {
      v ^= i;
    }
  }
  s_sink = v;
}
void StarControl_Branch64(void) {
  uint32_t i, v = s_sink;
  for (i = 0U; i < 64U; ++i) {
    if ((i & 1U) != 0U) {
      v += i;
    } else {
      v ^= i;
    }
  }
  s_sink = v;
}

void StarControl_Callback8(void) {
  uint32_t i, v = s_sink;
  for (i = 0U; i < 8U; ++i) {
    v = s_transforms[i & 1U](v);
  }
  s_sink = v;
}
void StarControl_Callback16(void) {
  uint32_t i, v = s_sink;
  for (i = 0U; i < 16U; ++i) {
    v = s_transforms[i & 1U](v);
  }
  s_sink = v;
}
void StarControl_Callback64(void) {
  uint32_t i, v = s_sink;
  for (i = 0U; i < 64U; ++i) {
    v = s_transforms[i & 1U](v);
  }
  s_sink = v;
}

void StarControl_Switch8(void) {
  uint32_t i, v = s_sink;
  for (i = 0U; i < 8U; ++i) {
    switch (i & 3U) {
    case 0U:
      v += 1U;
      break;
    case 1U:
      v ^= 2U;
      break;
    case 2U:
      v |= 4U;
      break;
    default:
      v &= 0xFFFFFFFEU;
      break;
    }
  }
  s_sink = v;
}
void StarControl_Switch16(void) {
  uint32_t i, v = s_sink;
  for (i = 0U; i < 16U; ++i) {
    switch (i & 3U) {
    case 0U:
      v += 1U;
      break;
    case 1U:
      v ^= 2U;
      break;
    case 2U:
      v |= 4U;
      break;
    default:
      v &= 0xFFFFFFFEU;
      break;
    }
  }
  s_sink = v;
}
void StarControl_Switch64(void) {
  uint32_t i, v = s_sink;
  for (i = 0U; i < 64U; ++i) {
    switch (i & 3U) {
    case 0U:
      v += 1U;
      break;
    case 1U:
      v ^= 2U;
      break;
    case 2U:
      v |= 4U;
      break;
    default:
      v &= 0xFFFFFFFEU;
      break;
    }
  }
  s_sink = v;
}

void StarControl_Checksum8(void) {
  uint32_t i, c = s_sink;
  for (i = 0U; i < 8U; ++i) {
    c ^= s_input[i] & 0xFFU;
  }
  s_sink = c;
}
void StarControl_Checksum16(void) {
  uint32_t i, c = s_sink;
  for (i = 0U; i < 16U; ++i) {
    c ^= s_input[i] & 0xFFU;
  }
  s_sink = c;
}
void StarControl_Checksum64(void) {
  uint32_t i, c = s_sink;
  for (i = 0U; i < 64U; ++i) {
    c ^= s_input[i] & 0xFFU;
  }
  s_sink = c;
}
