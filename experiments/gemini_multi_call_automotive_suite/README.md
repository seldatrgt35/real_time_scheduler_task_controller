# Gemini multi-call automotive blind suite

This suite contains three deterministic S32K148 automotive tasks that were not
used to create the current prompt. Each task is measured separately in one ELF,
while Gemini receives the exact same task source with `--no-rag`.

Freeze all Gemini predictions before reading the board measurements:

```powershell
$env:GEMINI_MODEL = "gemini-3.6-flash"
$source = "experiments/gemini_multi_call_automotive_suite/multi_call_automotive_tasks.c"

python -m gemini_rag_cycle_prototype.cli --source $source --function CoolingPumpDiagnostic_Task10ms --no-rag --output gemini_rag_cycle_prototype/results/multi_call_cooling.json
python -m gemini_rag_cycle_prototype.cli --source $source --function OccupantDoorSafety_Task20ms --no-rag --output gemini_rag_cycle_prototype/results/multi_call_occupant.json
python -m gemini_rag_cycle_prototype.cli --source $source --function CanSignalGateway_Task5ms --no-rag --output gemini_rag_cycle_prototype/results/multi_call_can_gateway.json
```

Board ELF:

`artifacts/s32k148_multi_call_automotive_suite/star_s32k148_multi_call_automotive_suite.elf`

Debugger expressions:

- `g_star_multi_call_complete`
- `g_star_multi_call_current`
- `g_star_multi_call_results.point_count`
- `g_star_multi_call_results.sample_count`
- `g_star_multi_call_results.measurement_overhead_cycles`
- `g_star_multi_call_results.error_flags`
- `g_star_multi_call_results.points`

Point mapping:

- `points[0]`: `CoolingPumpDiagnostic_Task10ms` (five helper calls per iteration)
- `points[1]`: `OccupantDoorSafety_Task20ms` (three helper calls per iteration)
- `points[2]`: `CanSignalGateway_Task5ms` (four helper calls per iteration, including a helper-local bounded loop)

A valid run has `complete=1`, `current=2`, `point_count=3`,
`sample_count=40`, and `error_flags=0`. Divide each `_us_x1000` value by
1000 to obtain microseconds.

The timed interval contains only the selected task call. Dataset initialization,
warm-up calls, DWT reads, result conversion, and result storage are outside the
timed interval. The ELF uses ARM GCC 11.4, Cortex-M4 Thumb code, and `-O0`.

ELF SHA-256:
`58FF85FC3EA340F4963DC71248CEA2CA903A918AE1EBBDD6E879A1983643B5A8`
