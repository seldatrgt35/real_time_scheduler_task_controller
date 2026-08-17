# S32K148 O0 mixed execution-region model v1.1

## Scope

This correction addresses bounded loops that combine memory access, helper
calls, branches, accumulation and operators from both the loop body and the
callee. Such loops are no longer assigned the first matching single-family
coefficient. Unsupported shapes remain explicit and cannot produce a partial
nominal estimate.

`VERIFIED` means that the S32K148 48 MHz, ARM GCC 11.4, `-O0` measurement-based
CPU execution estimate passed an independent holdout with the mandatory 15%
engineering margin. It is not a formal WCET proof and does not cover scheduler
preemption, interrupt latency, peripheral latency or functional correctness.

## Training measurements

| Family | 8 iterations | 16 iterations | 32 iterations | Affine model (us) |
|---|---:|---:|---:|---|
| actuator | 15.229 | 29.312 | 57.979 | 0.8955 + 1.7827410714 n |
| accumulator | 14.458 | 27.458 | 53.458 | 1.458 + 1.625 n |
| interpolation | 25.166 | 48.937 | 96.479 | 1.395 + 2.971375 n |

Each point contains 40 samples after eight warm-up executions. The frozen
training source is `mixed_helper_saturation_calibration.c`.

## Independent holdouts

| Family/task | Iterations | Frozen nominal | Safe (+15%) | Board | APE | Result |
|---|---:|---:|---:|---:|---:|:---:|
| actuator / ThermalActuator | 12 | 22.288 | 25.632 | 23.500 | 5.156% | PASS |
| accumulator / StabilityRequest | 20 | 33.958 | 39.052 | 33.416 | 1.622% | PASS |
| interpolation / blind holdout | 24 | 72.708 | 83.614 | 71.729 | 1.365% | PASS |

The body/chassis measurements and the separate interpolation blind holdout
were excluded from fitting. Admission coverage is 3/3.

## Resulting task classifications

| Task | Family | Nominal | Safe (+15%) | Execution status |
|---|---|---:|---:|:---:|
| AppTask_TorqueCoordination_20ms | interpolation | 48.937 | 56.278 | PASS |
| BccTask_ThermalActuator_10ms | actuator | 22.288 | 25.632 | PASS |
| BccTask_StabilityRequest_20ms | accumulator | 33.958 | 39.052 | PASS |

The complete automotive-feature and body/chassis task sets remain
`UNVERIFIED` because other task families are outside this correction's scope.
