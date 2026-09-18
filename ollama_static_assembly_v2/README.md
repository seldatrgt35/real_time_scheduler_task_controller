# Ollama static assembly V2

This is an isolated experiment. It does not replace or modify
`ollama_staged_cycle_prototype`.

V2 phase 1 gives each reachable C function to the model separately and asks
only for a normal static GCC 11.4 `-O0` Cortex-M4 Thumb-2 function body. The
model does not choose a path, unroll loops, count executions, or calculate
cycles. Python rejects missing calls/control flow and repeated-generation
collapse, then reports static instruction-class counts.

`static_core_cycle_sum` is the cost of executing every emitted static
instruction once. It is a diagnostic for comparing assembly shape, not a task
execution-time prediction. Dynamic CFG/path evaluation will be a separate V2
phase after the assembly output is validated on the benchmark set.

Example:

```powershell
$env:OLLAMA_MODEL = "qwen3-coder:30b"
python -m ollama_static_assembly_v2.cli `
  --source "experiments/gemini_compact_blind_v9/automotive_blind_v9_tasks.c" `
  --function "TorqueVectoringAllocation_Task2ms" `
  --output "ollama_static_assembly_v2/results/v9_torque_static_assembly.json"
```

The report is saved even when an assembly audit fails. By default the command
still exits normally, so a notebook does not turn a useful
`VALIDATION_REQUIRED` artifact into an opaque `CalledProcessError`. Add
`--strict` when automation should return exit code `2` for that status. No
execution-cycle estimate is published for failed assembly.
