# S32K148 Workload Complexity and Execution-Time Calibration

## Executive summary

Eight automotive-style task kernels were measured on S32K148 at 48 MHz. The
experiment tested whether STAR's static structural complexity can be converted
directly into execution time.

The result is clear: raw structural complexity alone is not a reliable WCET
predictor across mixed workload types. The A-H dataset has a Pearson
correlation of only `r = 0.23` between structural score and measured cycles.
Within comparable integer/control kernels, bounded dynamic work units predict
cycles strongly (`R² = 0.99984`).

STAR therefore reports two independent concepts:

1. structural complexity, which remains hardware-independent; and
2. target-calibrated dynamic execution cost, for which STAR automatically
   infers workload classes and bounded kernel-invocation counts from the AST.

The execution result is an engineering estimate, not a measured or formally
proven WCET.

## Platform and admission rule

- Target: NXP S32K148
- Measurement clock: 48 MHz
- Conversion: 48 cycles per microsecond
- Engineering safety limit: 80% of task period

The board admission test was:

`measured_max_cycles <= period_ms * 1000 * 48 * 0.80`

## Validated measurements

| Task | Period | Workload class | Work units | Structural score | Max cycles | Max time | 80% budget used |
|---|---:|---|---:|---:|---:|---:|---:|
| A | 1 ms | Integer/control | 274 | 306 | 38,305 | 798 us | 99.75% |
| B | 2 ms | Integer/control | 559 | 595 | 76,728 | 1,598 us | 99.91% |
| C | 5 ms | Fixed-point/filter | 1,255 | 1,291 | 191,989 | 3,999 us | 99.99% |
| D | 10 ms | Integer/control | 2,889 | 2,919 | 383,957 | 7,999 us | 99.99% |
| E | 20 ms | Integer/control | 5,632 | 5,664 | 760,457 | 15,842 us | 99.02% |
| F | 50 ms | Floating-point IIR | 3,264 | 3,328 | 1,898,740 | 39,557 us | 98.89% |
| G | 100 ms | Integer/control | 26,624 | 26,660 | 3,808,598 | 79,345 us | 99.18% |
| H | 200 ms | CAN/checksum | 48,000 | 35 | 7,660,690 | 159,597 us | 99.75% |

Tasks A-D identify an observed pass/fail boundary. Tasks E-H are conservative
validated passes.

## Why structural complexity is separate

Task H uses a compact runtime loop. Its source topology has structural
complexity 35, but its loop executes 48,000 CAN/checksum work units. It consumes
7,660,690 cycles. Static topology cannot encode that dynamic count unless a
loop bound is explicitly supplied or proven.

Task F provides a second counterexample. Its floating-point IIR work costs
approximately 581.72 cycles per unit, while integer/control work costs roughly
133-143 cycles per unit. Equal structural scores can therefore produce very
different execution times.

## Conservative calibrated coefficients

The first STAR workload profile uses:

| Workload class | Coefficient |
|---|---:|
| `integer_control` | 155 cycles/work unit |
| `fixed_point_filter` | 160 cycles/work unit |
| `can_checksum` | 160 cycles/work unit |
| `floating_point_iir` | 600 cycles/work unit |

The estimate is:

`estimated_cycles = inferred_bounded_operations * class_coefficient`

`estimated_execution_us = estimated_cycles / 48`

`safety_budget_cycles = period_ms * 1000 * 48 * 0.80`

The coefficient is deliberately conservative relative to the observed mean
cost per unit. It does not include an independently calibrated fixed intercept;
this version therefore avoids claiming more precision than the experiment
supports.

## STAR input contract

A task-set entry contains scheduler metadata only:

```json
{
  "name": "CanGateway",
  "source_file": "can_gateway.c",
  "entry_function": "CanGatewayTask",
  "period_ms": 200,
  "deadline_ms": 200,
  "priority": 2
}
```

The task-set config selects:

```json
{
  "workload_cost_profile_file":
    "task_admission_framework/calibration/profiles/S32K148_workload_costs.json"
}
```

Priority is restricted to `1` (LOW), `2` (MEDIUM), or `3` (HIGH).
`criticality` is not required for scheduler simulation; STAR internally uses
the existing HIGH rule class until a separate ISO 26262 model is introduced.

STAR derives kernel classes and counts from constant loop bounds, nested-loop
products, call structure, operand types, operators, and automotive token
patterns. Floating-point, fixed-point, CAN/checksum, and integer/control work
are accumulated separately.

If a `while`/`do` loop, recursion, or data-dependent `for` loop has no
statically proven maximum, execution estimation is `UNVERIFIED`. The user fixes
the source by expressing and enforcing a real engineering maximum; the user
does not manually enter a work-unit number.

## Limitations

- Results apply to the measured S32K148 clock, compiler/build configuration,
  harness, and kernel implementations.
- The estimate is not a formal WCET proof.
- Cache, memory placement, interrupts, preemption, compiler flags, and changed
  implementations require revalidation.
- The 80% ceiling is an engineering policy. Production projects may require a
  larger reserve.
- Workload classes must not be mixed merely to obtain a lower estimate.

## Conclusion

The corrected project hypothesis is supported: execution cost is predictable
from bounded dynamic work when functions are grouped by operation class. A
single raw structural-complexity-to-time mapping is not supported. STAR now
keeps structural complexity and target-specific execution estimation separate.
