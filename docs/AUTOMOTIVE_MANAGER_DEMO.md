# STAR Automotive Manager Demo

This demo shows the same five automotive C tasks in the STAR controller GUI
and on the S32K148 board.

## Demo assets

- Source: `task_admission_framework/examples/automotive_standard_tasks.c`
- Header: `task_admission_framework/examples/automotive_standard_tasks.h`
- Ready CLI task set: `task_admission_framework/examples/automotive_standard_taskset.json`
- Board ELF: `star-s32k148-benchmark/artifacts/star_s32k148_automotive_standard.elf`
- Board reference: `task_admission_framework/examples/automotive_standard_board_reference.csv`

## 1. Flash and run the board

Flash `star_s32k148_automotive_standard.elf`. Add these expressions:

```text
g_star_automotive_standard_complete
g_star_automotive_standard_results.error_flags
g_star_automotive_standard_results.points
```

Expected completion is `complete=1`, `error_flags=0`, and 40 completed samples
for every point. Point order is SensorFusion, SignalFilter, MotorControl,
StateEstimator, Diagnostics.

## 2. Start the GUI

From the controller repository:

```powershell
.\scripts\start_automotive_manager_demo.ps1
```

Use this source file for every row:

```text
task_admission_framework/examples/automotive_standard_tasks.c
```

Add the following tasks:

| Task | Function | Period | Priority |
|---|---|---:|---:|
| SensorFusion | `StarTask_5ms_SensorFusion` | 5 | 3 |
| SignalFilter | `StarTask_10ms_SignalFilter` | 10 | 3 |
| MotorControl | `StarTask_20ms_MotorControl` | 20 | 2 |
| StateEstimator | `StarTask_50ms_StateEstimator` | 50 | 2 |
| Diagnostics | `StarTask_100ms_Diagnostics` | 100 | 1 |

Select `S32K148`, press **Add Task** for each row, then press
**Analyze All Tasks**.

## 3. What to explain

The GUI parses the C AST, maps supported code patterns to S32K148 `-O0` board
costs, adds the frozen 15% engineering margin, and uses that safe budget in
fixed-priority response-time analysis and scheduler simulation.

Expected headline results:

- all five estimates are verified;
- all five safe estimates cover the measured board means;
- scheduler result is `FEASIBLE`;
- five-task nominal MAPE is 6.344%;
- independent mixed holdout error is 5.926%.

This is a measurement-based execution estimate, not a formal WCET proof.
