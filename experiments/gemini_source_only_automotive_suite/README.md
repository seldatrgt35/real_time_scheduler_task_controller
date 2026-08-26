# Gemini source-only automotive blind suite

These three tasks are intentionally absent from the RAG index. Run every
prediction with `--no-rag` before loading the board image.

```powershell
$env:GEMINI_MODEL = "gemini-3.6-flash"
$source = "experiments/gemini_source_only_automotive_suite/source_only_automotive_tasks.c"

python -m gemini_rag_cycle_prototype.cli --source $source `
  --function SteeringPlausibility_Task5ms --no-rag `
  --output gemini_rag_cycle_prototype/results/source_only_steering.json

python -m gemini_rag_cycle_prototype.cli --source $source `
  --function BrakePressureVoting_Task10ms --no-rag `
  --output gemini_rag_cycle_prototype/results/source_only_brake.json

python -m gemini_rag_cycle_prototype.cli --source $source `
  --function InverterThermalDerating_Task20ms --no-rag `
  --output gemini_rag_cycle_prototype/results/source_only_inverter.json
```

Board artifact:

`artifacts/s32k148_source_only_automotive_suite/star_s32k148_source_only_automotive_suite.elf`

Debugger expressions:

- `g_star_source_only_complete`
- `g_star_source_only_current`
- `g_star_source_only_results.point_count`
- `g_star_source_only_results.sample_count`
- `g_star_source_only_results.measurement_overhead_cycles`
- `g_star_source_only_results.error_flags`
- `g_star_source_only_results.points`

Task IDs:

- `0`: `SteeringPlausibility_Task5ms`
- `1`: `BrakePressureVoting_Task10ms`
- `2`: `InverterThermalDerating_Task20ms`

Valid completion is `complete=1`, `point_count=3`, `sample_count=40`, and
`error_flags=0`. Divide `_us_x1000` values by 1000 for microseconds.

ELF SHA-256:
`BEAA368C4FC1AC81CFCC9EDB36FBAE0B8F1A156CE38D75FB3DE756818C165021`
