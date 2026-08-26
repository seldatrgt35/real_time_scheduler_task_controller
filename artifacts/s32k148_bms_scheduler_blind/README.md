# S32K148 BMS scheduler blind benchmark

Built with S32DS ARM GCC 11.4, Cortex-M4, soft-float ABI and `-O0`.

The image uses the board-proven S32K148 startup and linker script from the
`real_time_scheduler` repository. The reset clock source is retained at 48 MHz.

Files:

- `star_s32k148_bms_scheduler_blind.elf`
- `star_s32k148_bms_scheduler_blind.hex`
- `star_s32k148_bms_scheduler_blind.map`

Debugger expressions:

- `g_star_bms_scheduler_complete`
- `g_star_bms_scheduler_results.completed_samples`
- `g_star_bms_scheduler_results.measurement_overhead_cycles`
- `g_star_bms_scheduler_results.error_flags`
- `g_star_bms_scheduler_results.mean_execution_us_x1000`
- `g_star_bms_scheduler_results.max_execution_us_x1000`

Valid completion is `complete=1`, `completed_samples=40`, `error_flags=0`.

ELF SHA-256:
`AD098F61F530B95B3324FA62618D93889D929AD74606E3E835000446D63AD2E6`

HEX SHA-256:
`732AD77DF9B1C7954FCD8552C439EB3E047AE1E7A81E4DA40072DC137F733A8B`
