# Gemini source-only automotive holdout v3

This blind suite contains three new deterministic automotive tasks. Gemini sees
only `automotive_holdout_v3_tasks.c`; the board measurement harness and startup
code are separate. The same task source is compiled into the board ELF.

Use one fixed Gemini model and `--no-rag`. Freeze all three JSON predictions
before reading the board results:

```powershell
$env:GEMINI_MODEL = "gemini-3.5-flash"
$source = "experiments/gemini_source_only_holdout_v3/automotive_holdout_v3_tasks.c"

python -m gemini_rag_cycle_prototype.cli --source $source --function BatteryBalancing_Task10ms --no-rag --output gemini_rag_cycle_prototype/results/holdout_v3_battery.json
python -m gemini_rag_cycle_prototype.cli --source $source --function EpsTorqueArbitration_Task5ms --no-rag --output gemini_rag_cycle_prototype/results/holdout_v3_eps.json
python -m gemini_rag_cycle_prototype.cli --source $source --function ThermalNetworkSupervision_Task20ms --no-rag --output gemini_rag_cycle_prototype/results/holdout_v3_thermal.json
```

Board ELF:

`artifacts/s32k148_source_only_holdout_v3/star_s32k148_source_only_holdout_v3.elf`

Debugger expressions:

- `g_star_holdout_v3_complete`
- `g_star_holdout_v3_current`
- `g_star_holdout_v3_results.point_count`
- `g_star_holdout_v3_results.sample_count`
- `g_star_holdout_v3_results.measurement_overhead_cycles`
- `g_star_holdout_v3_results.error_flags`
- `g_star_holdout_v3_results.points`
- `g_star_holdout_v3_exception_number`
- `g_star_holdout_v3_fault_cfsr`
- `g_star_holdout_v3_fault_hfsr`
- `g_star_holdout_v3_fault_mmfar`
- `g_star_holdout_v3_fault_bfar`

Point mapping:

- `points[0]`: `BatteryBalancing_Task10ms`
- `points[1]`: `EpsTorqueArbitration_Task5ms`
- `points[2]`: `ThermalNetworkSupervision_Task20ms`

A valid completed run has `complete=1`, `current=3`, `point_count=3`,
`sample_count=40`, and `error_flags=0`. Divide each `_us_x1000` value by 1000
to obtain microseconds.

`current=1/2/3` identifies the active or last task. A non-zero
`exception_number` means the CPU entered an exception; the four fault fields
then preserve the S32K148 SCB diagnostic registers.

The timed interval contains only the selected task call. Initialization,
warm-ups, DWT reads, result conversion, and result storage are outside the
timed interval. The ELF is built for Cortex-M4 Thumb with ARM GCC 11.4 at `-O0`.
The reset handler applies the same S32K148 watchdog unlock/configuration and
VTOR initialization sequence used by the previously validated board ELFs.

ELF SHA-256:
`082991228292E78F83119C5651EE2628AD8863D376FD9205CDABA958B17BABA7`
