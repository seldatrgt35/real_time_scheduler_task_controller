# S32K148 basic feature WCET suite

This ELF measures isolated, bounded C feature families with ARM GCC 11.4,
`-O0`, at the model's 48 MHz S32K148 reference frequency. Forty samples are
recorded after eight warmups. Predictions were frozen before board execution in
`tools/basic_feature_wcet_frozen_predictions.csv`.

Task IDs:

| ID | Function | Feature family |
|---:|---|---|
| 0 | `StarBasic_Arithmetic` | add/subtract/multiply contexts |
| 1 | `StarBasic_DivideModulo` | divide and modulo |
| 2 | `StarBasic_BitwiseShift` | AND/OR/XOR/rotate |
| 3 | `StarBasic_Branch` | branch with bitwise bodies; advisory |
| 4 | `StarBasic_SequentialMemory` | sequential memory |
| 5 | `StarBasic_RandomMemory` | indexed memory |
| 6 | `StarBasic_MemoryCopy` | array copy |
| 7 | `StarBasic_MemorySet` | array set |
| 8 | `StarBasic_FixedPoint` | Q15 MAC |
| 9 | `StarBasic_FloatingPoint` | float32 multiply loop |
| 10 | `StarBasic_DirectCall` | direct call |
| 11 | `StarBasic_IndirectCall` | callback |
| 12 | `StarBasic_Switch` | four-case switch |

Debugger expressions:

- `g_star_basic_complete`
- `g_star_basic_current`
- `g_star_basic_results.point_count`
- `g_star_basic_results.sample_count`
- `g_star_basic_results.measurement_overhead_cycles`
- `g_star_basic_results.error_flags`
- `g_star_basic_results.points`

Success before comparison is `complete=1`, `current=12`, `point_count=13`,
`sample_count=40`, and `error_flags=0`.

ELF SHA-256:
`61B552C92E09E923FA349708EE8F9184540B45BD8E54B6DCC1F64F96D3879736`
