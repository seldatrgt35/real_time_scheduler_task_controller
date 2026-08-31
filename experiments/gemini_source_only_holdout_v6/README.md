# Source-only prompt v2 blind holdout V6

Do not change the source-only prompt after freezing predictions. Do not add
these tasks or their board results to RAG until the comparison is complete.

## 1. Freeze source-only predictions before flashing

```powershell
$env:GEMINI_MODEL = "gemini-3.6-flash"
$source = "experiments/gemini_source_only_holdout_v6/automotive_holdout_v6_tasks.c"

python -m gemini_rag_cycle_prototype.cli --source $source --function BatteryImpedanceDerating_Task10ms --no-rag --output gemini_rag_cycle_prototype/results/holdout_v6_source_only_battery.json
python -m gemini_rag_cycle_prototype.cli --source $source --function SteeringSensorVoting_Task5ms --no-rag --output gemini_rag_cycle_prototype/results/holdout_v6_source_only_steering.json
python -m gemini_rag_cycle_prototype.cli --source $source --function CanGatewayFreshness_Task10ms --no-rag --output gemini_rag_cycle_prototype/results/holdout_v6_source_only_gateway.json
```

## 2. Flash the already-built single ELF

`artifacts/s32k148_gemini_source_only_holdout_v6/star_s32k148_gemini_source_only_holdout_v6.elf`

Debugger expressions:

```text
g_star_holdout_v6_complete
g_star_holdout_v6_current
g_star_holdout_v6_results.point_count
g_star_holdout_v6_results.sample_count
g_star_holdout_v6_results.measurement_overhead_cycles
g_star_holdout_v6_results.error_flags
g_star_holdout_v6_results.points
g_star_holdout_v6_exception_number
g_star_holdout_v6_fault_cfsr
g_star_holdout_v6_fault_hfsr
g_star_holdout_v6_fault_mmfar
g_star_holdout_v6_fault_bfar
```

Point mapping:

- `points[0]`: `BatteryImpedanceDerating_Task10ms`
- `points[1]`: `SteeringSensorVoting_Task5ms`
- `points[2]`: `CanGatewayFreshness_Task10ms`

A valid run has `complete=1`, `current=3`, `point_count=3`, 40 completed
samples per point, and `error_flags=0`. Initialization is outside each timed
interval.
