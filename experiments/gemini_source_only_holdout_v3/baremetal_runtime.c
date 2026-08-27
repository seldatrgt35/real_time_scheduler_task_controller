typedef __UINT32_TYPE__ uint32_t;

#define STAR_SCB_CFSR  (*(volatile uint32_t *)0xE000ED28UL)
#define STAR_SCB_HFSR  (*(volatile uint32_t *)0xE000ED2CUL)
#define STAR_SCB_MMFAR (*(volatile uint32_t *)0xE000ED34UL)
#define STAR_SCB_BFAR  (*(volatile uint32_t *)0xE000ED38UL)

extern int main(void);
extern uint32_t __bss_start__;
extern uint32_t __bss_end__;
extern uint32_t __data_start__;
extern uint32_t __data_end__;
extern uint32_t __data_load__;

volatile uint32_t g_star_holdout_v3_exception_number;
volatile uint32_t g_star_holdout_v3_fault_cfsr;
volatile uint32_t g_star_holdout_v3_fault_hfsr;
volatile uint32_t g_star_holdout_v3_fault_mmfar;
volatile uint32_t g_star_holdout_v3_fault_bfar;

__attribute__((naked, noreturn)) void Reset_Handler(void)
{
    __asm__ volatile (
        "cpsid i\n"
        "ldr r0, =0x40052004\n"
        "ldr r1, =0xD928C520\n"
        "str r1, [r0]\n"
        "ldr r0, =0x40052000\n"
        "ldr r1, =0x00002520\n"
        "str r1, [r0]\n"
        "ldr r0, =0x40052008\n"
        "ldr r1, =0x0000FFFF\n"
        "str r1, [r0]\n"
        "ldr r0, =0xE000ED08\n"
        "ldr r1, =g_pfnVectors\n"
        "str r1, [r0]\n"
        "dsb\n"
        "isb\n"
        "b rts_s32k148_reset_entry\n"
    );
}

void Default_Handler(void)
{
    uint32_t exception_number;
    __asm__ volatile ("mrs %0, ipsr" : "=r" (exception_number));
    g_star_holdout_v3_exception_number = exception_number;
    g_star_holdout_v3_fault_cfsr = STAR_SCB_CFSR;
    g_star_holdout_v3_fault_hfsr = STAR_SCB_HFSR;
    g_star_holdout_v3_fault_mmfar = STAR_SCB_MMFAR;
    g_star_holdout_v3_fault_bfar = STAR_SCB_BFAR;
    for (;;)
    {
        __asm__ volatile ("nop");
    }
}

void rts_s32k148_reset_entry(void)
{
    uint32_t *destination;
    const uint32_t *source;

    destination = &__bss_start__;
    while (destination < &__bss_end__)
    {
        *destination = 0U;
        ++destination;
    }
    source = &__data_load__;
    destination = &__data_start__;
    while (destination < &__data_end__)
    {
        *destination = *source;
        ++destination;
        ++source;
    }
    __asm__ volatile ("cpsie i" ::: "memory");
    (void)main();
    Default_Handler();
}

extern uint32_t __StackTop;

__attribute__((section(".isr_vector"), used))
const void *g_pfnVectors[256] =
{
    [0] = &__StackTop,
    [1] = Reset_Handler,
    [2 ... 255] = Default_Handler
};

__attribute__((section(".flash_config"), used))
const unsigned char g_s32k148_flash_config[16] =
{
    0xFFU, 0xFFU, 0xFFU, 0xFFU, 0xFFU, 0xFFU, 0xFFU, 0xFFU,
    0xFFU, 0xFFU, 0xFFU, 0xFFU, 0xFEU, 0xFFU, 0xFFU, 0xFFU
};
