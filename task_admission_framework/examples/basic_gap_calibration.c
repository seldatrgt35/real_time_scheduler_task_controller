#include "basic_gap_calibration.h"

typedef __UINT32_TYPE__ uint32_t;

#define STAR_GAP_MASK (63U)

static volatile uint32_t s_gap_sink;

void StarGap_Initialize(void)
{
    s_gap_sink = 0x13579BDFU;
}

void StarGap_Arithmetic8(void)
{
    uint32_t index; uint32_t value = s_gap_sink; const uint32_t local = 7U;
    for (index = 0U; index < 8U; ++index)
    { value += 3U; value += local; value += index; value *= local; value -= local; }
    s_gap_sink = value;
}

void StarGap_Arithmetic16(void)
{
    uint32_t index; uint32_t value = s_gap_sink; const uint32_t local = 7U;
    for (index = 0U; index < 16U; ++index)
    { value += 3U; value += local; value += index; value *= local; value -= local; }
    s_gap_sink = value;
}

void StarGap_Arithmetic64(void)
{
    uint32_t index; uint32_t value = s_gap_sink; const uint32_t local = 7U;
    for (index = 0U; index < 64U; ++index)
    { value += 3U; value += local; value += index; value *= local; value -= local; }
    s_gap_sink = value;
}

void StarGap_MaskedDivide8(void)
{
    uint32_t index; uint32_t value = s_gap_sink;
    for (index = 1U; index <= 8U; ++index)
    { value += (0x3FFFU / index) & STAR_GAP_MASK; }
    s_gap_sink = value;
}

void StarGap_MaskedDivide16(void)
{
    uint32_t index; uint32_t value = s_gap_sink;
    for (index = 1U; index <= 16U; ++index)
    { value += (0x3FFFU / index) & STAR_GAP_MASK; }
    s_gap_sink = value;
}

void StarGap_MaskedDivide64(void)
{
    uint32_t index; uint32_t value = s_gap_sink;
    for (index = 1U; index <= 64U; ++index)
    { value += (0x3FFFU / index) & STAR_GAP_MASK; }
    s_gap_sink = value;
}

void StarGap_MaskedModulo8(void)
{
    uint32_t index; uint32_t value = s_gap_sink;
    for (index = 1U; index <= 8U; ++index)
    { value += (0xF3579BDFU % index) & STAR_GAP_MASK; }
    s_gap_sink = value;
}

void StarGap_MaskedModulo16(void)
{
    uint32_t index; uint32_t value = s_gap_sink;
    for (index = 1U; index <= 16U; ++index)
    { value += (0xF3579BDFU % index) & STAR_GAP_MASK; }
    s_gap_sink = value;
}

void StarGap_MaskedModulo64(void)
{
    uint32_t index; uint32_t value = s_gap_sink;
    for (index = 1U; index <= 64U; ++index)
    { value += (0xF3579BDFU % index) & STAR_GAP_MASK; }
    s_gap_sink = value;
}
