# Gemini + RAG blind holdout v4

This suite contains three previously unmeasured query tasks. Freeze all Gemini
predictions before reading board timing. Do not add these tasks to learning
feedback until the comparison is complete.

## 1. Produce and freeze Prompt v3 predictions

```powershell
$source = "experiments/gemini_rag_holdout_v4/automotive_holdout_v4_tasks.c"

python -m gemini_rag_cycle_prototype.cli --source $source --function DcLinkRippleMonitor_Task1ms --output gemini_rag_cycle_prototype/results/holdout_v4_dc_link.json
python -m gemini_rag_cycle_prototype.cli --source $source --function NetworkSignalSupervision_Task10ms --output gemini_rag_cycle_prototype/results/holdout_v4_network.json
python -m gemini_rag_cycle_prototype.cli --source $source --function InjectorPulseCompensation_Task5ms --output gemini_rag_cycle_prototype/results/holdout_v4_injector.json
```

Keep each `.json`, `.raw.txt`, and `.retrieval.json` file unchanged until board
comparison is recorded.

## 2. Build and flash one ELF

```powershell
powershell -ExecutionPolicy Bypass -File experiments/gemini_rag_holdout_v4/build_s32k148.ps1
```

Flash:

`artifacts/s32k148_gemini_rag_holdout_v4/star_s32k148_gemini_rag_holdout_v4.elf`

## 3. Debugger expressions

```text
g_star_holdout_v4_complete
g_star_holdout_v4_current
g_star_holdout_v4_results.point_count
g_star_holdout_v4_results.sample_count
g_star_holdout_v4_results.measurement_overhead_cycles
g_star_holdout_v4_results.error_flags
g_star_holdout_v4_results.points
g_star_holdout_v4_exception_number
g_star_holdout_v4_fault_cfsr
g_star_holdout_v4_fault_hfsr
g_star_holdout_v4_fault_mmfar
g_star_holdout_v4_fault_bfar
```

Point mapping:

- `points[0]`: `DcLinkRippleMonitor_Task1ms`
- `points[1]`: `NetworkSignalSupervision_Task10ms`
- `points[2]`: `InjectorPulseCompensation_Task5ms`

Initialization runs outside each timed interval. Every point has 8 warmups and
40 measured samples. A valid completed run has `complete=1`, `current=3`, and
`error_flags=0`.
