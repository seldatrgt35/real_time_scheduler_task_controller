# Structured Blind V8

This suite is a source-only blind evaluation set. Freeze all three Gemini
predictions before reading the board measurements.

Task mapping:

- `points[0]`: `RadarObjectAssociation_Task20ms`
- `points[1]`: `EgrAdaptiveControl_Task10ms`
- `points[2]`: `SecureCanFreshness_Task5ms`

The board harness enables S32K148 code cache, performs eight warm-up calls and
then records 40 DWT measurements per task. The build uses GCC 11.4 at `-O0`
with interprocedural, inline and link-time optimizations disabled.

## Frozen blind results

| Task | Gemini cycles | Board max cycles | Error |
|---|---:|---:|---:|
| Radar object association | 3465 | 4288 | -19.19% |
| EGR adaptive control | 489 | 490 | -0.20% |
| Secure CAN freshness | 3844 | 2766 | +38.97% |

The three-task MAPE is 19.46%. No result was adjusted with a fitted margin.

## Structural root-cause evidence

For radar, Gemini emitted 1,813 dynamic instruction events across the task and
its callees. The GCC 11.4 `-O0` disassembly executes approximately 2,572 events
on the seeded path. The main task is under-described (533 predicted versus
approximately 840 actual), `RadarAssociationCost` is under-described (500
versus 780), and the 40 `AbsoluteDifferenceS16` calls are under-described (780
versus approximately 952). This is a predicted-assembly completeness error,
not a Cortex-M4 timing coefficient error.

For Secure CAN, Gemini predicts 1,888 events in `ComputeCrc8`; the real seeded
path executes approximately 1,544. The 12-byte by 8-bit CRC has 217 conditional
branch executions in both the real and predicted structures. Gemini also adds
217 unconditional branches, whereas GCC executes only 53: one loop-entry
branch, twelve inner-loop-entry branches, and forty polynomial-path join
branches for the seeded data. The excess 164 unconditional branches are the
principal source of the overestimate.
