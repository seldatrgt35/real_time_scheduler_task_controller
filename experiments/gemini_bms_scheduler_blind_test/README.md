# Gemini BMS scheduler blind test

This is a source-only blind task. It is intentionally absent from the RAG
measurement index. Do not add its board result to the index before freezing the
Gemini prediction.

## Timed scope

The DWT interval measures:

```text
BmsScheduler_RunDueTask(10)
  -> release check
  -> next-release update
  -> indirect callback dispatch
  -> BmsSupervision_Task10ms
```

Initialization and release preparation are outside the timed interval.

## Freeze the Gemini prediction first

```powershell
$env:GEMINI_MODEL = "gemini-3.6-flash"
python -m gemini_rag_cycle_prototype.cli `
  --source experiments/gemini_bms_scheduler_blind_test/bms_supervision_task.c `
  --function BmsScheduler_RunDueTask `
  --exclude-function BmsScheduler_RunDueTask `
  --exclude-source-path experiments/gemini_bms_scheduler_blind_test/bms_supervision_task.c `
  --top-k 5 `
  --output gemini_rag_cycle_prototype/results/bms_scheduler_blind.json
```

Do not edit the prediction after seeing the board result.

## S32DS board project

Add these files to the same S32K148, ARM GCC 11.4, `-O0`, 48 MHz project used
by the previous DWT harnesses:

- `bms_supervision_task.c`
- `bms_supervision_task.h`
- `s32k148_bms_scheduler_blind_main.c`

Use the existing startup code, linker script, clock initialization and debug
configuration. Only one `main` source may be enabled in the project.

Debugger expressions:

- `g_star_bms_scheduler_complete`
- `g_star_bms_scheduler_results.completed_samples`
- `g_star_bms_scheduler_results.measurement_overhead_cycles`
- `g_star_bms_scheduler_results.error_flags`
- `g_star_bms_scheduler_results.mean_execution_us_x1000`
- `g_star_bms_scheduler_results.max_execution_us_x1000`

Valid measurement prerequisites are `complete=1`, `completed_samples=40`, and
`error_flags=0`. Values ending in `_us_x1000` must be divided by 1000 to obtain
microseconds.

## Provenance

The benchmark is an original deterministic adaptation of common BMS
supervision responsibilities documented by open-source projects such as
foxBMS and Infineon's PSoC 6 BMS: cell voltage/temperature monitoring, passive
balancing decisions, fault aggregation, and contactor/precharge control. It is
not a copied upstream source file.
