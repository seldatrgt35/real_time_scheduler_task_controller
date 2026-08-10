# S32K148 Contextual O0 Model v1.0

This is the frozen board-calibrated model for ARM GCC 11.4, S32K148 at
48 MHz, `-O0`. It produces a nominal execution estimate and a required 15%
engineering-margin estimate. It is measurement-based and is not a formal WCET
proof.

## Add a task

1. Add the C source and entry function to the project.
2. Add one item to a task-set JSON file with `source_file`, `entry_function`,
   `period_ms`, `deadline_ms`, `priority`, hardware profile, and rules profile.
3. Keep loop bounds constant or statically derivable. Unknown bounds produce
   `UNVERIFIED` rather than an invented duration.

Example:

```json
{
  "name": "MyTask10ms",
  "source_file": "my_tasks.c",
  "entry_function": "MyTask10ms",
  "period_ms": 10,
  "deadline_ms": 10,
  "priority": 2,
  "hardware_profile_file": "../hardware/profiles/S32K148.json",
  "rules_file": "../rules/profiles/S32K148_rules.json"
}
```

## Analyze

```powershell
python -m task_admission_framework.main analyze-taskset --config path/to/taskset.json
```

Use `Admission Execution (with margin)` as the scheduler budget. A task is
eligible for admission only when the estimate is verified.

## Board comparison contract

- Compile the exact analyzed source with ARM GCC 11.4 and `-O0`.
- Run initialization outside the timed region.
- Subtract the calibrated cycle-counter overhead.
- Compare both mean and maximum time against the frozen nominal and safe values.
- Do not change coefficients after seeing a holdout result; create a new model
  version if recalibration is required.

## Frozen validation summary

- Five-task automotive suite revised MAPE: 6.344%.
- Independent mixed automotive holdout error: +5.926%.
- Independent holdout safe result: PASS.
- Engineering margin: 15%.
