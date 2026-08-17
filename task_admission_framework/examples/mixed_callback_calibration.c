#include "mixed_callback_calibration.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT32_TYPE__ uint32_t;
typedef uint32_t (*Callback)(uint32_t state, uint8_t input);

static uint8_t g_callback_input[32U];
static uint8_t g_callback_output[32U];
static volatile uint32_t g_callback_sink;

static uint32_t CallbackXor(uint32_t state, uint8_t input)
{
    return state ^ (uint32_t)input;
}

static uint32_t CallbackRotate(uint32_t state, uint8_t input)
{
    return (state << 1U) | (state >> 31U) | (uint32_t)input;
}

static const Callback g_callbacks[2U] = {CallbackXor, CallbackRotate};

void MixedCallbackCalibration_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < 32U; ++index)
    {
        g_callback_input[index] = (uint8_t)((index * 11U) + 3U);
        g_callback_output[index] = 0U;
    }
    g_callback_sink = 0x12345678UL;
}

static void CallbackKernel(uint32_t count)
{
    uint32_t index;
    uint32_t state = g_callback_sink;
    for (index = 0U; index < count; ++index)
    {
        state = g_callbacks[index & 1U](state, g_callback_input[index]);
    }
    g_callback_sink = state;
}

static void CallbackPackKernel(uint32_t count)
{
    uint32_t index;
    uint32_t state = g_callback_sink;
    for (index = 0U; index < count; ++index)
    {
        const uint32_t shift = (index & 3U) * 8U;
        g_callback_output[index] = (uint8_t)(state >> shift);
        state = g_callbacks[index & 1U](state, g_callback_output[index]);
    }
    g_callback_sink = state;
}

void MixedCallback_8(void) { CallbackKernel(8U); }
void MixedCallback_16(void) { CallbackKernel(16U); }
void MixedCallback_32(void) { CallbackKernel(32U); }
void MixedCallbackPack_8(void) { CallbackPackKernel(8U); }
void MixedCallbackPack_16(void) { CallbackPackKernel(16U); }
void MixedCallbackPack_32(void) { CallbackPackKernel(32U); }
