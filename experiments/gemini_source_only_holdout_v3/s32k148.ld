ENTRY(rts_s32k148_reset_entry)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = 0x00180000
    RAM   (rwx) : ORIGIN = 0x1FFE0000, LENGTH = 0x0003F000
}

__StackTop = ORIGIN(RAM) + LENGTH(RAM);

SECTIONS
{
    .isr_vector ORIGIN(FLASH) :
    {
        KEEP(*(.isr_vector))
    } > FLASH

    .flash_config 0x00000400 :
    {
        KEEP(*(.flash_config))
    } > FLASH

    .text 0x00000410 :
    {
        *(.text*)
        *(.rodata*)
        *(.ARM.extab*)
        *(.ARM.exidx*)
    } > FLASH

    .data : AT(LOADADDR(.text) + SIZEOF(.text))
    {
        . = ALIGN(4);
        __data_start__ = .;
        *(.data*)
        . = ALIGN(4);
        __data_end__ = .;
    } > RAM
    __data_load__ = LOADADDR(.data);

    .bss (NOLOAD) :
    {
        . = ALIGN(4);
        __bss_start__ = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        __bss_end__ = .;
    } > RAM
}
