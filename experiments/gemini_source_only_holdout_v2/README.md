# Gemini source-only holdout v2

Freeze all three `--no-rag` Gemini predictions before inspecting board results:

```powershell
$source = "experiments/gemini_source_only_holdout_v2/automotive_holdout_v2.c"

python -m gemini_rag_cycle_prototype.cli --source $source --function BatteryContactorSupervisor_Task10ms --no-rag --output gemini_rag_cycle_prototype/results/holdout_v2_contactor.json
python -m gemini_rag_cycle_prototype.cli --source $source --function WheelSpeedFusion_Task5ms --no-rag --output gemini_rag_cycle_prototype/results/holdout_v2_wheel.json
python -m gemini_rag_cycle_prototype.cli --source $source --function DiagnosticEventAging_Task100ms --no-rag --output gemini_rag_cycle_prototype/results/holdout_v2_dtc.json
```

Prompt-v2 path-constrained diagnostic runs must use new output names so the
frozen baseline files above are not overwritten:

```powershell
$evidence = "experiments/gemini_source_only_holdout_v2/timing_evidence_source_only.txt"

python -m gemini_rag_cycle_prototype.cli --source $source --function BatteryContactorSupervisor_Task10ms --no-rag --input-constraints-file experiments/gemini_source_only_holdout_v2/constraints/contactor_constraints.txt --timing-evidence-file $evidence --output gemini_rag_cycle_prototype/results/holdout_v2_contactor_prompt_v2.json
python -m gemini_rag_cycle_prototype.cli --source $source --function WheelSpeedFusion_Task5ms --no-rag --input-constraints-file experiments/gemini_source_only_holdout_v2/constraints/wheel_constraints.txt --timing-evidence-file $evidence --output gemini_rag_cycle_prototype/results/holdout_v2_wheel_prompt_v2.json
python -m gemini_rag_cycle_prototype.cli --source $source --function DiagnosticEventAging_Task100ms --no-rag --input-constraints-file experiments/gemini_source_only_holdout_v2/constraints/dtc_constraints.txt --timing-evidence-file $evidence --output gemini_rag_cycle_prototype/results/holdout_v2_dtc_prompt_v2.json
```

Board ELF:

`artifacts/s32k148_source_only_holdout_v2/star_s32k148_source_only_holdout_v2.elf`

Debugger expressions:

- `g_star_holdout_v2_complete`
- `g_star_holdout_v2_current`
- `g_star_holdout_v2_results.point_count`
- `g_star_holdout_v2_results.sample_count`
- `g_star_holdout_v2_results.measurement_overhead_cycles`
- `g_star_holdout_v2_results.error_flags`
- `g_star_holdout_v2_results.points`

Point mapping:

- `points[0]`: `BatteryContactorSupervisor_Task10ms`
- `points[1]`: `WheelSpeedFusion_Task5ms`
- `points[2]`: `DiagnosticEventAging_Task100ms`

Valid completion is `complete=1`, `current=2`, `point_count=3`,
`sample_count=40`, and `error_flags=0`. Divide `_us_x1000` by 1000.

ELF SHA-256:
`11B2C695E9EF154843A5EA07925904520081BF7009F61C500F2D65086972C0C1`
