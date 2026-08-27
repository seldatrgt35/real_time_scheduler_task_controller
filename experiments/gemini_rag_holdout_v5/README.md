# Gemini + RAG blind holdout v5

Run and freeze all Gemini predictions before flashing the board ELF. These task
measurements must not enter RAG feedback until comparison is complete.

## 1. Rebuild the index with validated v4 board feedback

```powershell
python -m gemini_rag_cycle_prototype.cli --rebuild-index
```

Expected record count: `88`.

## 2. Freeze Prompt v3 + RAG predictions

```powershell
$source = "experiments/gemini_rag_holdout_v5/automotive_holdout_v5_tasks.c"

python -m gemini_rag_cycle_prototype.cli --source $source --function WheelPulseCoherence_Task2ms --output gemini_rag_cycle_prototype/results/holdout_v5_wheel.json
python -m gemini_rag_cycle_prototype.cli --source $source --function EvapPurgeDiagnostic_Task100ms --output gemini_rag_cycle_prototype/results/holdout_v5_evap.json
python -m gemini_rag_cycle_prototype.cli --source $source --function MotorCurrentDerating_Task5ms --output gemini_rag_cycle_prototype/results/holdout_v5_motor.json
```

## 3. Build and flash the single ELF

```powershell
powershell -ExecutionPolicy Bypass -File experiments/gemini_rag_holdout_v5/build_s32k148.ps1
```

Flash:

`artifacts/s32k148_gemini_rag_holdout_v5/star_s32k148_gemini_rag_holdout_v5.elf`

Debugger expressions:

```text
g_star_holdout_v5_complete
g_star_holdout_v5_current
g_star_holdout_v5_results.point_count
g_star_holdout_v5_results.sample_count
g_star_holdout_v5_results.measurement_overhead_cycles
g_star_holdout_v5_results.error_flags
g_star_holdout_v5_results.points
g_star_holdout_v5_exception_number
g_star_holdout_v5_fault_cfsr
g_star_holdout_v5_fault_hfsr
g_star_holdout_v5_fault_mmfar
g_star_holdout_v5_fault_bfar
```

Point mapping:

- `points[0]`: `WheelPulseCoherence_Task2ms`
- `points[1]`: `EvapPurgeDiagnostic_Task100ms`
- `points[2]`: `MotorCurrentDerating_Task5ms`

A valid run has `complete=1`, `current=3`, `point_count=3`, 40 completed
samples per point, and `error_flags=0`. Initialization is outside every timed
interval.
