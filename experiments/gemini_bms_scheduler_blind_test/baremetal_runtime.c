/* Minimal runtime glue for the shared, board-proven S32K148 startup file. */

extern int main(void);

void NMI_Handler(void)
{
    for (;;)
    {
        __asm__ volatile ("nop");
    }
}

void HardFault_Handler(void)
{
    for (;;)
    {
        __asm__ volatile ("nop");
    }
}

void SVC_Handler(void)
{
}

void PendSV_Handler(void)
{
}

void SysTick_Handler(void)
{
}

void LPTMR0_IRQHandler(void)
{
}

__attribute__((noreturn)) void rts_s32k148_reset_entry(void)
{
    __asm__ volatile ("cpsie i" ::: "memory");
    (void)main();
    for (;;)
    {
        __asm__ volatile ("nop");
    }
}
