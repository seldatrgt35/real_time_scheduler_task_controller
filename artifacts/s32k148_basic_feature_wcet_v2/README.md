# S32K148 expanded basic feature WCET suite V2

This V2 ELF keeps task IDs 0-12 compatible with the first basic suite and adds
14 isolated model families at IDs 13-26. Predictions were frozen before board
execution in `tools/basic_feature_wcet_v2_frozen_predictions.csv`.

Task ID mapping:

| ID | Function |
|---:|---|
| 0 | `StarBasic_Arithmetic` |
| 1 | `StarBasic_DivideModulo` |
| 2 | `StarBasic_BitwiseShift` |
| 3 | `StarBasic_Branch` |
| 4 | `StarBasic_SequentialMemory` |
| 5 | `StarBasic_RandomMemory` |
| 6 | `StarBasic_MemoryCopy` |
| 7 | `StarBasic_MemorySet` |
| 8 | `StarBasic_FixedPoint` |
| 9 | `StarBasic_FloatingPoint` |
| 10 | `StarBasic_DirectCall` |
| 11 | `StarBasic_IndirectCall` |
| 12 | `StarBasic_Switch` |
| 13 | `StarBasic_MaskedMultiply` |
| 14 | `StarBasic_MaskedDivide` |
| 15 | `StarBasic_MaskedModulo` |
| 16 | `StarBasic_BitwiseNested` |
| 17 | `StarBasic_Checksum` |
| 18 | `StarBasic_Q15Multiply` |
| 19 | `StarBasic_Q31Multiply` |
| 20 | `StarBasic_Q31Mac` |
| 21 | `StarBasic_Float32Add` |
| 22 | `StarBasic_Float32Divide` |
| 23 | `StarBasic_Float64Add` |
| 24 | `StarBasic_Float64Multiply` |
| 25 | `StarBasic_Float64Divide` |
| 26 | `StarBasic_IntToFloat` |

Debugger expressions:

- `g_star_basic_complete`
- `g_star_basic_current`
- `g_star_basic_results.point_count`
- `g_star_basic_results.sample_count`
- `g_star_basic_results.measurement_overhead_cycles`
- `g_star_basic_results.error_flags`
- `g_star_basic_results.points`

Success before comparison is `complete=1`, `current=26`, `point_count=27`,
`sample_count=40`, and `error_flags=0`.

ELF SHA-256:
`9638054E9685BCE2F7425253E4DA0B5BCF4346F20AF8AD44C369DD4B22944831`
