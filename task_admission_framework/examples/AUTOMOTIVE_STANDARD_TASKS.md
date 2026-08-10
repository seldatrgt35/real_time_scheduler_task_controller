# Automotive Standard Task Module

The module contains five deterministic automotive-style C tasks intended for
S32K148 `-O0` static-estimate versus board-measurement comparison.

## Entry functions

| Function | Period | Priority | Current nominal estimate |
|---|---:|---:|---:|
| `StarTask_5ms_SensorFusion` | 5 ms | 3 | 208.442 us |
| `StarTask_10ms_SignalFilter` | 10 ms | 3 | 308.889 us |
| `StarTask_20ms_MotorControl` | 20 ms | 2 | 130.366 us |
| `StarTask_50ms_StateEstimator` | 50 ms | 2 | 527.688 us |
| `StarTask_100ms_Diagnostics` | 100 ms | 1 | 134.524 us |

Call `StarAutomotive_Initialize()` once before starting the scheduler or board
measurements. Do not include initialization in the timed task region.

## Analyze

From the `real_time_scheduler_task_controller` directory:

```powershell
python -m task_admission_framework.main analyze-taskset --config task_admission_framework/examples/automotive_standard_taskset.json
```

For the board comparison, compile the same `.c` file with ARM GCC 11.4 and
`-O0`, measure each entry function independently after resetting the module,
and report mean/max time in microseconds.
