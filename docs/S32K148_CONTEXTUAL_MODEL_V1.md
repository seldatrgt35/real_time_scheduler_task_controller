# S32K148 Contextual O0 Model v1.2

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

## Mixed execution-region extension (v1.1)

Version 1.1 prevents realistic helper/memory/branch loops from being reduced
to the first matching single-family pattern. It retains bounded iterations,
array accesses, branches, direct and indirect calls, body operator classes and
callee operator classes.

Three independently measured structural families are supported:

| Family | Training points | Independent holdout | Holdout APE | Admission |
|---|---|---:|---:|:---:|
| actuator | 8, 16, 32 | body/chassis, 12 iterations | 5.156% | PASS |
| accumulator | 8, 16, 32 | body/chassis, 20 iterations | 1.622% | PASS |
| interpolation | 8, 16, 32 | blind, 24 iterations | 1.365% | PASS |

Every calibration and holdout point contains 40 board samples. Body/chassis
and blind holdout measurements were not used to fit coefficients. The
interpolation prediction was frozen at 72.708 us nominal and 83.6142 us with
margin before its 71.729 us board result was collected.

This extension verifies the execution-time model for TorqueCoordination,
ThermalActuator and StabilityRequest. It does not make the complete example
task sets schedulable: unrelated tasks with unsupported shapes still keep the
system result `UNVERIFIED`.

## Plausibility extension (v1.2)

Version 1.2 adds the mixed array-read, accumulation, branch, comparison,
bitwise-mask and shift family used by PowertrainInput and WheelSpeedBrake.
Calibration used independent 8/16/32-iteration kernels measured 40 times each.
The fitted model is `1.812 + 1.125 n` microseconds for the complete calibration
function. The production group intercept is 1.7495 us because the final
0.0625 us XOR remains separately represented by `bitwise_xor_u32`.

The frozen 24-iteration WheelSpeedBrake prediction was 28.812 us nominal and
33.1338 us with margin. Its previously frozen board result is 29.125 us, an
absolute error of 1.075%; the holdout passes. PowertrainInput is therefore
estimated at 19.812 us nominal and 22.784 us with margin.
