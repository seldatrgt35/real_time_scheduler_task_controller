# STAR Framework

STAR (Static Task Admission for Real-time Systems) is a static analysis and admission-control framework for real-time embedded tasks. It analyzes C/C++ task code before scheduler admission and produces a static, explainable complexity-based decision.

The current target platform is:

- NXP S32K148
- Arm Cortex-M4F
- FreeRTOS-style automotive embedded systems

STAR is not a WCET tool. It does not estimate execution time and it does not prove real-time schedulability. It provides a static complexity-based admission and task-set risk indicator.

Raw complexity is hardware independent. Hardware metadata may adjust the rule
threshold used by static admission, but it must not modify the raw complexity
score extracted from source code.

## Current Status

The project currently supports:

- C and C++ source analysis through Clang AST
- Recursive helper-function traversal
- C++ method/function call recovery for incomplete ASTs
- Complexity score calculation
- YAML task descriptor loading
- JSON hardware profile loading
- JSON rule database loading
- Single-task `ACCEPT` / `REJECT` admission decisions
- Multi-task STAR load analysis
- Fixed-priority scheduler result models
- CLI usage
- Tkinter GUI usage

FreeRTOS integration, real board calibration, and validated execution budgets
are not implemented yet. Scheduler feasibility is therefore `UNVERIFIED` unless
synthetic test budgets are supplied directly to the scheduler analyzer.

## Package Structure

The project is a real Python package:

```text
task_admission_framework/
  admission/
  analyzer/
  complexity/
  cost/
  database/
  descriptor/
  examples/
  feature/
  hardware/
  model/
  pipeline/
  report/
  rules/
  scheduling/
  taskset/
  utils/
  gui.py
  main.py
```

Run commands from the repository root, not from inside the package directory.

## Architecture

The main analysis and admission flow is:

```text
C/C++ source
-> Clang AST parser
-> recursive call graph
-> TaskProfile
-> FeatureExtractor
-> FeatureVector
-> CostDatabase
-> ComplexityCalculator
-> ComplexityReport
-> TaskDescriptor
-> HardwareProfile
-> AnalysisPipeline
-> AnalysisSession
-> RuleDatabase
-> AdmissionController
-> AdmissionDecision
-> FixedPriorityAnalyzer
-> SchedulerSetResult
```

Responsibilities are separated:

- `AnalysisPipeline` remains decision-free.
- `RuleDatabase` only stores and retrieves rules.
- `AdmissionController` is the first layer allowed to produce `ACCEPT` or `REJECT`.
- `TaskSetAnalyzer` combines multiple single-task results into a static STAR load indicator.
- `FixedPriorityAnalyzer` is the only layer that uses priority for scheduler analysis.

## Installation

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Dependencies:

- `clang`
- `PyYAML`

The analyzer uses `clang.cindex`, so a compatible native `libclang` runtime must also be available. On Windows, if you see an error such as `libclang.dll not found`, install a compatible LLVM/libclang runtime or install/configure a package that provides `libclang.dll`.

## Single-Task CLI

Run the built-in demo:

```bash
python -m task_admission_framework.main
```

Analyze a specific task:

```bash
python -m task_admission_framework.main analyze \
  --source task_admission_framework/examples/sensor_task.c \
  --descriptor task_admission_framework/examples/sensor_task.yaml \
  --hardware task_admission_framework/hardware/profiles/S32K148.json \
  --rules task_admission_framework/rules/profiles/S32K148_rules.json \
  --hardware-adjustment calibrated
```

The single-task result focuses on the user-facing admission summary:

```text
Code Complexity Score: 5.0 / 60.00
Complexity Load: 8%
Static Admission: ACCEPT
```

Hardware reference details are still shown separately:

```text
S32K148 Reference Limit
Hardware Scaling
Adjusted Limit
Hardware Model
```

The result is a static complexity-based result, not a WCET or scheduler
guarantee.

## GUI

Open the desktop GUI:

```bash
python -m task_admission_framework.main gui
```

The GUI supports both single-task and task-set workflows.

For a single task:

1. Select a C/C++ source file.
2. Enter the method/function name.
3. Select hardware.
4. Select period.
5. Select priority.
6. Press `Analyze Current Only`.

For a task set:

1. Select a C/C++ source file.
2. Enter the method/function name.
3. Select hardware, period, and priority.
4. Press `Add Task`.
5. Repeat for each task.
6. Press `Analyze All Tasks`.

The task-set GUI output includes each task's own analysis, per-task STAR load
indicator, total STAR complexity load indicator, static risk status, scheduler
feasibility status, and reason. Priority does not affect raw complexity and is
not used as a complexity multiplier. Priority is used only by the separate
fixed-priority scheduler analyzer when validated execution budgets exist.

## Rule Database

The bundled S32K148 rule profile is:

```text
task_admission_framework/rules/profiles/S32K148_rules.json
```

It currently supports these placeholder periods:

```text
5 ms, 10 ms, 20 ms, 50 ms, 100 ms, 250 ms, 500 ms, 1000 ms
```

Initial thresholds:

```text
5 ms     -> max complexity 60
10 ms    -> max complexity 120
20 ms    -> max complexity 250
50 ms    -> max complexity 600
100 ms   -> max complexity 1200
250 ms   -> max complexity 3000
500 ms   -> max complexity 6000
1000 ms  -> max complexity 12000
```

These values are engineering placeholders. They are not experimentally
calibrated yet and do not represent measured execution time.

## Hardware Adjustment Modes

STAR supports explicit hardware adjustment modes:

```text
NONE
PROTOTYPE_FREQUENCY_SCALING
CALIBRATED
```

`NONE` uses the reference rule maximum directly:

```text
AdjustedMaximum = ReferenceRuleMaximum
```

`PROTOTYPE_FREQUENCY_SCALING` keeps the current prototype demonstration model:

```text
HardwareScalingFactor = selected_cpu_frequency_mhz / 112
AdjustedMaximum = ReferenceRuleMaximum * HardwareScalingFactor
```

This mode is not validated. Every result using it must be read with this
warning:

```text
Warning: CPU-frequency scaling is an unvalidated prototype heuristic and is not a schedulability guarantee.
```

Peripheral accesses, blocking operations, flash wait states, cache effects,
compiler settings, and RTOS behavior do not necessarily scale linearly with CPU
frequency.

`CALIBRATED` uses S32K148 reference thresholds as the reference data set and
scales the static threshold for another target using documented hardware
metadata. The current calibrated scaling factor is:

```text
HardwareScalingFactor = selected_cpu_frequency_mhz / 112
AdjustedMaximum = ReferenceRuleMaximum * HardwareScalingFactor
```

The following hardware fields are recorded and checked as metadata:

- `cpu_frequency_mhz`
- `fpu`
- `cache`
- `flash_wait_states`
- `compiler`
- `optimization_level`
- `execution_location`

Only CPU frequency changes the threshold in the current conservative model.
FPU/cache/flash/compiler metadata may produce warnings because those effects are
configuration-dependent and do not necessarily scale linearly. If a task uses
floating-point operations and the selected hardware has no FPU, STAR reports a
warning that the adjusted threshold may be optimistic.

If the S32K148 reference rule is not marked `validated: true`, STAR still runs
but reports that hardware-adjusted admission remains a reference-scaling
estimate. STAR must not fabricate execution-time values.

## Task-Set Analysis

Task-set analysis is a static complexity-based risk indicator. It is not
WCET-based schedulability analysis.

For each task:

```text
TaskLoad = ComplexityScore / AdjustedMaximumComplexity
```

The displayed name is:

```text
STAR Complexity Load Indicator
```

When the hardware adjustment mode is `PROTOTYPE_FREQUENCY_SCALING`,
`AdjustedMaximumComplexity` is derived from the reference rule threshold and the
selected hardware CPU frequency:

```text
HardwareScalingFactor = selected_cpu_frequency_mhz / 112
AdjustedMaximumComplexity = ReferenceRuleComplexity * HardwareScalingFactor
```

S32K148 is the reference hardware. For S32K148, the scaling factor is `1.0`.
For an 80 MHz target, a 5 ms reference threshold of `60` becomes:

```text
60 * (80 / 112) = 42.86
```

For the full task set:

```text
TotalSTARComplexityLoadIndicator = sum(TaskLoad_i)
```

System status:

```text
If any individual task is REJECT -> SYSTEM_REJECT
Else if TotalSTARComplexityLoadIndicator <= 1.0 -> FEASIBLE
Else if TotalSTARComplexityLoadIndicator <= 1.2 -> RISK
Else -> NOT_FEASIBLE
```

These statuses are kept for backward compatibility as static risk indicators.
They are not scheduler guarantees.

## Scheduler Feasibility

Scheduler feasibility is separate from static admission. Priority is used only
in this layer.

The fixed-priority analyzer uses standard response-time iteration only when
every task has a validated `execution_budget_us`:

```text
R_i = C_i + B_i + sum(ceil(R_i / T_j) * C_j)
```

Terms:

- `R_i`: response time of task `i`
- `C_i`: validated execution budget of task `i`
- `B_i`: blocking budget of task `i`
- `T_j`: period of a higher-priority task `j`
- `C_j`: validated execution budget of a higher-priority task `j`

Assumptions:

- single-core
- preemptive fixed-priority scheduling
- higher numeric FreeRTOS priority means higher scheduling priority
- periodic or sporadic tasks
- deadlines are provided by the task descriptor

If any task has no validated execution budget, scheduler feasibility is:

```text
UNVERIFIED
```

Current S32K148 execution-budget calibration does not exist yet, so normal STAR
CLI and GUI task-set output reports scheduler feasibility as `UNVERIFIED`.

Run task-set analysis from the CLI:

```bash
python -m task_admission_framework.main analyze-taskset \
  --config task_admission_framework/examples/taskset_config.json \
  --hardware-adjustment calibrated
```

Example task-set config:

```json
{
  "tasks": [
    {
      "name": "SensorTaskFast",
      "source_file": "task_admission_framework/examples/sensor_task.c",
      "entry_function": "SensorTask",
      "period_ms": 5,
      "deadline_ms": 5,
      "priority": 3,
      "criticality": "HIGH",
      "hardware_profile_file": "task_admission_framework/hardware/profiles/S32K148.json",
      "rules_file": "task_admission_framework/rules/profiles/S32K148_rules.json"
    },
    {
      "name": "SensorTaskNominal",
      "source_file": "task_admission_framework/examples/sensor_task.c",
      "entry_function": "SensorTask",
      "period_ms": 10,
      "deadline_ms": 10,
      "priority": 2,
      "criticality": "HIGH",
      "hardware_profile_file": "task_admission_framework/hardware/profiles/S32K148.json",
      "rules_file": "task_admission_framework/rules/profiles/S32K148_rules.json"
    }
  ]
}
```

## Metrics

STAR currently extracts and scores structural metrics such as:

- function calls
- branches (`if`)
- loops (`for`, `while`, `do while`)
- switches
- returns
- pointer usage
- floating-point usage
- dynamic memory calls
- blocking API calls
- known API calls
- recursion detection

For C++ code, STAR also includes a token-based recovery pass to catch member calls that may be missing from incomplete Clang ASTs due to missing project or standard-library includes.

## Limitations

Current limitations:

- No FreeRTOS integration yet.
- No task creation or scheduler hook yet.
- No WCET estimation.
- No WCET-proven schedulability result.
- Rule thresholds are placeholders.
- CPU-frequency scaling is a prototype heuristic only.
- Priority does not affect complexity and is not used as a load multiplier.
- Priority is used only by fixed-priority scheduler analysis.
- Scheduler analysis requires validated execution budgets.

## Next Steps

Planned next steps:

1. S32K148 board validation.
2. Experimental rule calibration.
3. Project-specific API cost classification.
4. FreeRTOS admission hook integration.
5. Evaluation against classic FreeRTOS task creation flow.
