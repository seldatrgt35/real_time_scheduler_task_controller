# STAR Framework

STAR (Static Task Admission for Real-time Systems) is a static analysis and admission-control framework for real-time embedded tasks. It analyzes C/C++ task code before scheduler admission and produces a static, explainable complexity-based decision.

The current target platform is:

- NXP S32K148
- Arm Cortex-M4F
- FreeRTOS-style automotive embedded systems

STAR is not a WCET tool. It does not estimate execution time and it does not prove real-time schedulability. It provides a static complexity-based admission and task-set risk indicator.

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
- CLI usage
- Tkinter GUI usage

FreeRTOS integration and real board calibration are not implemented yet.

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
```

Responsibilities are separated:

- `AnalysisPipeline` remains decision-free.
- `RuleDatabase` only stores and retrieves rules.
- `AdmissionController` is the first layer allowed to produce `ACCEPT` or `REJECT`.
- `TaskSetAnalyzer` combines multiple single-task results into a static STAR load indicator.

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
  --rules task_admission_framework/rules/profiles/S32K148_rules.json
```

The single-task result includes task metadata, complexity score, matched rule threshold, admission decision, reason, and complexity breakdown.

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

The task-set GUI output includes each task's own analysis, per-task load, total STAR load, system status, and system reason. Priority is currently metadata in the task-set result. The Sprint 8 STAR load formula does not weight load by priority.

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

These values are engineering placeholders. They are not experimentally calibrated yet and do not represent measured execution time.

## Task-Set Analysis

Task-set analysis is a static complexity-based scheduler risk indicator. It is not WCET-based schedulability analysis.

For each task:

```text
TaskLoad = ComplexityScore / RuleMaximumComplexity
```

For the full task set:

```text
TotalSTARLoad = sum(TaskLoad_i)
```

System status:

```text
If any individual task is REJECT -> SYSTEM_REJECT
Else if TotalSTARLoad <= 1.0 -> FEASIBLE
Else if TotalSTARLoad <= 1.2 -> RISK
Else -> NOT_FEASIBLE
```

Run task-set analysis from the CLI:

```bash
python -m task_admission_framework.main analyze-taskset \
  --config task_admission_framework/examples/taskset_config.json
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
- Priority is shown but not used as a load multiplier.
- Hardware currently selects rule thresholds; it does not directly alter the complexity score.

## Next Steps

Planned next steps:

1. S32K148 board validation.
2. Experimental rule calibration.
3. Project-specific API cost classification.
4. FreeRTOS admission hook integration.
5. Evaluation against classic FreeRTOS task creation flow.
