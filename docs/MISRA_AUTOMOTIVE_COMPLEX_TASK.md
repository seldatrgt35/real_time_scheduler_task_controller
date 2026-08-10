# MISRA-Oriented Automotive Complex Task

The module exposes five separate GUI task entry functions and is written in a
MISRA C:2012-oriented style for demonstrating STAR coverage. It uses
fixed-width compiler types, bounded loops, explicit casts,
static storage, typed function pointers, exhaustive `switch` handling, and no
recursion or dynamic allocation.

It exercises the currently calibrated STAR feature families:

- dense integer/control expressions;
- sequential and indexed memory access;
- bounded copy and set loops;
- Q31 fixed-point MAC;
- float32 multiplication and conversion;
- checksum processing;
- indirect function calls;
- four-way `switch` evaluation.

| GUI task | Entry function | Period | Priority |
|---|---|---:|---:|
| Control | `StarTask_5ms_MisraControl` | 5 ms | 3 |
| Memory | `StarTask_10ms_MisraMemory` | 10 ms | 3 |
| Fixed point | `StarTask_20ms_MisraFixedPoint` | 20 ms | 2 |
| Floating point | `StarTask_50ms_MisraFloatingPoint` | 50 ms | 2 |
| Diagnostics | `StarTask_100ms_MisraDiagnostics` | 100 ms | 1 |

Run the analysis with:

```powershell
python -m task_admission_framework.main analyze-taskset --config task_admission_framework/examples/misra_automotive_complex_taskset.json
```

This source has not been certified by a commercial MISRA checker. Formal MISRA
compliance requires the project-specific essential-type configuration,
deviation record, compiler configuration, and static-analysis report.
