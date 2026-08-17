# S32K148 mixed plausibility model v1.2

The model covers bounded loops combining array reads, accumulation,
index-dependent comparisons, branches, bit masks and shifts. These loops are
no longer reduced to the advisory `component_branch_bitwise_u32` feature.

## Calibration

| Iterations | Board mean/max (us) |
|---:|---:|
| 8 | 10.812 |
| 16 | 19.812 |
| 32 | 37.812 |

All points completed 40 samples with zero error flags. The fitted full-function
model is `1.812 + 1.125 n` us. Since the analyzer separately represents the
final XOR at 0.0625 us, the mixed group uses a 1.7495 us intercept and the same
1.125 us iteration coefficient.

## Independent holdout

WheelSpeedBrake was excluded from fitting and retained as the frozen
24-iteration body/chassis holdout.

| Nominal | Safe (+15%) | Board | APE | Result |
|---:|---:|---:|---:|:---:|
| 28.812 us | 33.1338 us | 29.125 us | 1.075% | PASS |

Resulting estimates:

| Task | Nominal | Safe (+15%) | Execution status |
|---|---:|---:|:---:|
| AppTask_PowertrainInput_5ms | 19.812 us | 22.784 us | PASS |
| BccTask_WheelSpeedAndBrake_5ms | 28.812 us | 33.134 us | PASS |

`VERIFIED` remains limited to the S32K148 48 MHz, ARM GCC 11.4, `-O0`
measurement-based CPU model. It is not a formal WCET proof.
