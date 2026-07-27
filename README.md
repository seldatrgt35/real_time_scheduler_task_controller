# STAR Framework

STAR (Static Task Admission for Real-time Systems) is a static analysis and admission-control framework for real-time embedded tasks. It analyzes C/C++ task code before scheduler admission and produces a static, explainable complexity-based decision.

> **S32K148 calibration update:** raw structural complexity is no longer treated
> as a universal execution-time proxy. STAR now infers bounded workload classes
> and counts directly from the AST; users do not enter `workload_class` or
> `work_units`. See
> [`docs/S32K148_WORKLOAD_CALIBRATION_REPORT.md`](docs/S32K148_WORKLOAD_CALIBRATION_REPORT.md).

The current target platform is:

- NXP S32K148
- Arm Cortex-M4F
- FreeRTOS-style automotive embedded systems

STAR is not a WCET tool and it does not prove real-time schedulability. With
an optional calibration profile, it can estimate execution time from STAR
complexity points for scheduler simulation. Those estimates are engineering
calibration estimates, not WCET guarantees.

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
- Complexity-time calibration profiles
- Estimated execution-time generation from complexity score
- Fixed-priority scheduler simulation for calibrated task sets
- Fixed-priority scheduler result models
- CLI usage
- Tkinter GUI usage

FreeRTOS integration and validated WCET budgets are not implemented yet.
Scheduler output that uses complexity-time calibration must be treated as a
calibration-based estimate.

## Quick Start

Always run STAR commands from the repository root:

```powershell
cd "C:\Users\nxg19748\OneDrive - NXP\Desktop\real_time_scheduler_task_controller"
```

Do not run module commands from inside `task_admission_framework/`. Python needs
the repository root on `PYTHONPATH` so it can resolve the package name.

Install dependencies:

```powershell
pip install -r requirements.txt
```

Open the GUI:

```powershell
python -m task_admission_framework.main gui
```

Run the built-in demo:

```powershell
python -m task_admission_framework.main
```

Analyze the bundled example from the CLI:

```powershell
python -m task_admission_framework.main analyze `
  --source task_admission_framework/examples/sensor_task.c `
  --descriptor task_admission_framework/examples/sensor_task.yaml `
  --hardware task_admission_framework/hardware/profiles/S32K148.json `
  --rules task_admission_framework/rules/profiles/S32K148_rules.json `
  --hardware-adjustment calibrated
```

Analyze a task set from the CLI:

```powershell
python -m task_admission_framework.main analyze-taskset `
  --config task_admission_framework/examples/taskset_config.json `
  --hardware-adjustment calibrated
```

Analyze the automotive calibration benchmark task set:

```powershell
python -m task_admission_framework.main analyze-complexity-taskset `
  --config task_admission_framework/examples/automotive_taskset_config.json
```

This command is the recommended first step for S32K148 calibration work. It
does not use hardware adjustment, rules, admission, execution-time estimation,
or scheduler simulation. It only prints raw STAR complexity scores and
breakdowns for each benchmark task.

Run the full calibrated task-set path only after raw complexity collection is
understood:

```powershell
python -m task_admission_framework.main analyze-taskset `
  --config task_admission_framework/examples/automotive_taskset_config.json `
  --hardware-adjustment calibrated
```

The bundled task-set config already points to the example complexity-time
calibration profile:

```text
task_admission_framework/calibration/profiles/S32K148_complexity_time.json
```

Common Windows note: if `clang` is installed but STAR reports
`libclang.dll not found`, install/configure a compatible LLVM/libclang runtime
and make sure `libclang.dll` is visible to Python.

## Package Structure

The project is a real Python package:

```text
task_admission_framework/
  admission/
  analyzer/
  calibration/
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

The single-task result uses the A-H board-calibrated mixed-workload model:

```text
Measurement-Calibrated Execution Admission
Result: PASS
Estimated Cycles: 8915
Estimated Execution: 185.7 us
80% Period Budget: 192000 cycles (4000.0 us)
Budget Used: 4.64%
```

The raw structural score and its legacy threshold are shown only under
`Structural Review`; they do not determine timing admission.

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

The task-set GUI shows the inferred mixed workload, calibrated cycle subtotal
for each operation class, estimated execution time, 80% period budget, and
fixed-priority response time. Priority does not multiply complexity; it affects
the interference term in response-time analysis.

## Legacy Structural Review Database

The bundled S32K148 rule profile is:

```text
task_admission_framework/rules/profiles/S32K148_rules.json
```

It supports these periods for backward-compatible structural review:

```text
5 ms, 10 ms, 20 ms, 25 ms, 50 ms, 100 ms, 200 ms, 250 ms, 500 ms, 1000 ms
```

Its thresholds are unvalidated engineering placeholders. They produce only a
`NORMAL`/`HIGH` code-review indicator. Timing limits are calculated from the
validated S32K148 profile as
`period_ms * 1000 * 48 cycles/us * 0.80`.

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
converts the task score into an S32K148-equivalent score for the selected
hardware.

```text
HardwareAdjustedScore =
  ComputationScore    * ComputationFactor
+ ControlFlowScore   * ControlFlowFactor
+ FloatingPointScore * FloatingPointFactor
+ MemoryScore        * MemoryFactor
+ RTOSScore          * RTOSFactor
+ PeripheralScore    * PeripheralFactor
+ OtherScore         * OtherFactor
```

The static admission decision then compares:

```text
HardwareAdjustedScore <= S32K148ReferenceMaximum
```

The reference maximum stays anchored to the S32K148 rule database. The selected
hardware changes the adjusted task score, not the raw complexity score.

The current calibrated category factors are intentionally conservative:

```text
ComputationFactor    = 112 / selected_cpu_frequency_mhz
ControlFlowFactor   = 112 / selected_cpu_frequency_mhz
FloatingPointFactor = 112 / selected_cpu_frequency_mhz, only when the task uses
                      floating point and the target has an FPU
FloatingPointFactor = max(112 / selected_cpu_frequency_mhz, 1.0), when the task
                      uses floating point and the target has no FPU
MemoryFactor        = 1.0
RTOSFactor          = 1.0
PeripheralFactor    = 1.0
OtherFactor         = 1.0
```

This means CPU-bound code benefits from a faster CPU, but RTOS and peripheral
operations are not automatically treated as faster only because the CPU clock is
higher.

The following hardware fields are used or recorded:

- `cpu_frequency_mhz`
- `fpu`
- `cache`
- `flash_wait_states`
- `adc_units`
- `can_units`
- `spi_units`
- `uart_units`
- `i2c_units`
- `dma`
- `compiler`
- `optimization_level`
- `execution_location`

`cpu_frequency_mhz` changes computation and control-flow score factors.

`fpu` is applied only when the task has floating-point score. If the task does
not use floating point, FPU does not affect the adjusted score. If the task uses
floating point but the selected hardware has no FPU, STAR does not give the task
a faster-CPU benefit for the floating-point category and reports a warning.

`cache`, `flash_wait_states`, `compiler`, `optimization_level`, and
`execution_location` are currently metadata and warning context. They do not
directly change the score in this conservative model.

Peripheral unit fields are used for availability checks. For example, if a task
uses `CAN_Send` but the selected hardware has `can_units: 0`, static admission
is rejected with a hardware compatibility reason.

If the S32K148 reference rule is not marked `validated: true`, STAR still runs
but reports that hardware-adjusted admission remains a reference-scaling
estimate. STAR must not fabricate execution-time values.

Example:

```text
Task category scores:
Computation      = 30
Control Flow     = 10
Floating Point   = 20
Memory           = 15
RTOS             = 5
Peripheral       = 20

Selected hardware:
170 MHz Cortex-M target with FPU

Factors:
Computation      = 112 / 170 = 0.66
Control Flow     = 112 / 170 = 0.66
Floating Point   = 112 / 170 = 0.66
Memory           = 1.00
RTOS             = 1.00
Peripheral       = 1.00

HardwareAdjustedScore =
30*0.66 + 10*0.66 + 20*0.66 + 15*1.00 + 5*1.00 + 20*1.00
= 79.6

If the S32K148 5 ms reference maximum is 70:
79.6 <= 70 -> REJECT
```

## Task-Set Analysis

Task-set analysis is a static complexity-based risk indicator. It is not
WCET-based schedulability analysis.

For each task:

```text
TaskLoad = HardwareAdjustedScore / S32K148ReferenceMaximum
```

The displayed name is:

```text
STAR Complexity Load Indicator
```

When the hardware adjustment mode is `CALIBRATED`, the task-set load indicator
uses the same category-adjusted score as single-task admission:

```text
TaskLoad = HardwareAdjustedScore / S32K148ReferenceMaximum
```

When the hardware adjustment mode is `PROTOTYPE_FREQUENCY_SCALING`, STAR keeps
the older prototype threshold-scaling behavior:

```text
AdjustedMaximumComplexity = ReferenceRuleComplexity * (selected_cpu_frequency_mhz / 112)
```

For the full task set:

```text
TotalSTARComplexityLoadIndicator = sum(TaskLoad_i)
```

System status is based on calibrated execution estimates and fixed-priority
schedulability. Structural complexity is reported separately as a review-risk
indicator:

```text
If a calibrated execution budget exceeds its safety limit -> SYSTEM_REJECT
Else if any dynamic bound is unknown -> UNVERIFIED
Else if response-time analysis finds a deadline miss -> NOT_FEASIBLE
Else -> FEASIBLE
```

Legacy structural thresholds may independently produce a HIGH review indicator,
but never change a calibrated timing PASS into a scheduling failure.

## Legacy Complexity-Time Calibration

This section documents the backward-compatible interpolation path. New S32K148
task sets should use automatic AST-derived workload estimation instead.

STAR does not require users to enter execution time for every task. Instead,
users can provide one task-independent calibration profile that maps complexity
scores to execution time for the reference hardware class.

Example profile:

```json
{
  "profile_id": "s32k148_reference_v1",
  "reference_hardware": "S32K148",
  "source": "Initial example calibration data; replace with project measurements",
  "validated": false,
  "points": [
    {
      "complexity": 60,
      "execution_time_ms": 3.0
    },
    {
      "complexity": 120,
      "execution_time_ms": 6.0
    }
  ]
}
```

This means:

```text
60 STAR complexity points  -> approximately 3.0 ms
120 STAR complexity points -> approximately 6.0 ms
```

For each task, STAR uses:

```text
HardwareAdjustedScore -> ComplexityTimeProfile -> EstimatedExecutionTime
```

If the score is between two calibration points, STAR linearly interpolates. For
example:

```text
60 -> 3.0 ms
120 -> 6.0 ms
90 -> 4.5 ms
```

If the score is outside the calibrated range, STAR extrapolates and reports a
note. These estimates are engineering estimates for scheduler simulation, not
WCET guarantees.

## Automotive Calibration Benchmark

The repository includes a larger C benchmark intended for S32K148 calibration
work:

```text
task_admission_framework/examples/automotive_scheduler_smoke_model.c
task_admission_framework/examples/automotive_taskset_config.json
```

It defines eight automotive-style periodic tasks:

```text
5 ms     StarTask_5ms_BrakeControl
10 ms    StarTask_10ms_SteeringAssist
25 ms    StarTask_25ms_CrashSafety
50 ms    StarTask_50ms_BatteryThermal
100 ms   StarTask_100ms_PowertrainManager
200 ms   StarTask_200ms_Diagnostics
500 ms   StarTask_500ms_NetworkGateway
1000 ms  StarTask_1000ms_VehicleHealth
```

The active benchmark source mirrors the portable application-work functions
used by the scheduler smoke test. This is intentional: STAR must analyze the
same function body that the S32K148 scheduler measures. That keeps the
complexity-to-execution-time comparison meaningful.

The older high-complexity stress source remains available as:

```text
task_admission_framework/examples/automotive_complex_taskset.c
```

Use it only when you want a synthetic complexity stress test. Use
`automotive_scheduler_smoke_model.c` when comparing STAR complexity with board
execution-time measurements.

Current raw-complexity spread for the scheduler smoke model:

```text
5 ms     BrakeControl5ms          108
10 ms    SteeringAssist10ms        79
25 ms    CrashSafety25ms          147
50 ms    BatteryThermal50ms       155
100 ms   Powertrain100ms          160
200 ms   Diagnostics200ms         142
500 ms   NetworkGateway500ms       48
1000 ms  VehicleHealth1000ms      158
```

The values are intentionally spaced apart. Lower-period tasks are not always
the most complex; the benchmark includes several cases so measured execution
time can be compared against different complexity levels and different periods.

Run STAR analysis:

```bash
python -m task_admission_framework.main analyze-complexity-taskset \
  --config task_admission_framework/examples/automotive_taskset_config.json
```

This raw-complexity command ignores hardware, rules, admission, and scheduler
analysis. Use it first when collecting benchmark complexity values.

Run the later hardware/calibration path with:

```bash
python -m task_admission_framework.main analyze-taskset \
  --config task_admission_framework/examples/automotive_taskset_config.json \
  --hardware-adjustment calibrated
```

Use the same C functions on the S32K148 board to measure real execution time.
Then compare:

```text
STAR HardwareAdjustedScore  <->  measured execution time on S32K148
```

From those measurements, update:

```text
task_admission_framework/calibration/profiles/S32K148_complexity_time.json
```

Example calibration outcome:

```json
{
  "points": [
    { "complexity": 60, "execution_time_ms": 3.0 },
    { "complexity": 120, "execution_time_ms": 6.0 },
    { "complexity": 300, "execution_time_ms": 14.0 }
  ]
}
```

This is how STAR learns the approximate S32K148 relationship between static
complexity and measured execution time without asking users to enter execution
time for every new task.

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

When a complexity-time calibration profile is present, STAR estimates execution
budgets for the task set and runs fixed-priority response-time analysis.

## Scheduler Simulation

STAR also includes a simple fixed-priority scheduler simulator for task-set
analysis when estimated execution budgets are available.

The simulator models this FreeRTOS-style policy:

```text
READY tasks with the highest numeric priority run first.
A higher-priority READY task preempts a lower-priority running task.
Same-priority READY tasks are selected by FIFO order in the current simulator.
If no application task is READY, IDLE runs.
```

The simulator uses periodic releases:

```text
Task release times = 0, period, 2*period, ...
Absolute deadline = release time + deadline
```

The task-set config can define:

```json
{
  "calibration_profile_file": "task_admission_framework/calibration/profiles/S32K148_complexity_time.json",
  "simulation_window_ms": 50,
  "tasks": []
}
```

Simulation output includes a compact timeline such as:

```text
0.000-1.500 ms SensorTaskFast (run)
1.500-3.000 ms SensorTaskNominal (run)
3.000-5.000 ms IDLE (idle)
```

Delay, semaphore, queue, and event behavior are not exactly simulated yet
because static source analysis does not know the exact runtime block point or
external event timing. STAR reports blocking API usage separately and keeps
those limitations explicit.

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
