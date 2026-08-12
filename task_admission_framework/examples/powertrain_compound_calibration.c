/** Independent bounded calibration kernels for S32K148 ARM GCC O0. */
#include "powertrain_compound_calibration.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;
typedef __INT64_TYPE__ int64_t;

static uint16_t g_input[32U];
static int32_t g_map[17U];
static uint8_t g_debounce[16U];
static uint8_t g_payload[16U];
static volatile int32_t g_numeric_sink;
static volatile uint32_t g_state_sink;

void StarCompoundCalibration_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < 32U; ++index)
    {
        g_input[index] = (uint16_t)(211U + (index * 97U));
    }
    for (index = 0U; index < 17U; ++index)
    {
        g_map[index] = (int32_t)(index * 17700U) - 1300;
    }
    for (index = 0U; index < 16U; ++index)
    {
        g_debounce[index] = (uint8_t)(index & 3U);
        g_payload[index] = (uint8_t)(index * 19U);
    }
}

static void StarTorqueMapKernel(uint32_t count)
{
    uint32_t index;
    int32_t result = 900000;
    for (index = 0U; index < count; ++index)
    {
        const uint32_t segment = ((uint32_t)g_input[index] >> 8U) & 15U;
        const uint32_t fraction = (uint32_t)g_input[index] & 255U;
        const int32_t lower = g_map[segment];
        const int32_t upper = g_map[segment + 1U];
        const int64_t delta = (int64_t)(upper - lower) * (int64_t)fraction;
        const int32_t mapped = lower + (int32_t)(delta / 256);
        if (mapped < result) { result = mapped; }
        if (result < 0) { result = 0; }
    }
    g_numeric_sink = result;
}

static void StarDiagnosticsKernel(uint32_t count)
{
    uint32_t index;
    uint32_t faults = 0U;
    for (index = 0U; index < count; ++index)
    {
        const uint16_t first = g_input[index];
        const uint16_t second = g_input[index + 16U];
        const uint16_t difference = (first > second)
            ? (uint16_t)(first - second) : (uint16_t)(second - first);
        if ((first < 100U) || (first > 3900U) || (difference > 700U))
        {
            if (g_debounce[index] < 7U) { ++g_debounce[index]; }
        }
        else if (g_debounce[index] > 0U) { --g_debounce[index]; }
        else { /* State remains clear. */ }
        if (g_debounce[index] >= 3U) { faults |= 1UL << index; }
    }
    g_state_sink = faults;
}

static void StarCanPackingKernel(uint32_t count)
{
    uint32_t index;
    uint8_t crc = 0xFFU;
    for (index = 0U; index < count; ++index)
    {
        uint32_t bit;
        g_payload[index] = (uint8_t)(g_input[index] >> (index & 7U));
        crc ^= g_payload[index];
        for (bit = 0U; bit < 8U; ++bit)
        {
            crc = ((crc & 0x80U) != 0U)
                ? (uint8_t)((crc << 1U) ^ 0x1DU)
                : (uint8_t)(crc << 1U);
        }
    }
    g_state_sink = (uint32_t)crc;
}

void StarCalibration_TorqueMap_8(void) { StarTorqueMapKernel(8U); }
void StarCalibration_TorqueMap_16(void) { StarTorqueMapKernel(16U); }
void StarCalibration_TorqueMap_32(void) { StarTorqueMapKernel(32U); }
void StarCalibration_Diagnostics_4(void) { StarDiagnosticsKernel(4U); }
void StarCalibration_Diagnostics_8(void) { StarDiagnosticsKernel(8U); }
void StarCalibration_Diagnostics_16(void) { StarDiagnosticsKernel(16U); }
void StarCalibration_CanPacking_4(void) { StarCanPackingKernel(4U); }
void StarCalibration_CanPacking_8(void) { StarCanPackingKernel(8U); }
void StarCalibration_CanPacking_16(void) { StarCanPackingKernel(16U); }
