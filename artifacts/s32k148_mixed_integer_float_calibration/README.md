# S32K148 mixed integer/float calibration

Nine independent points measure three loop bodies at 8, 16, and 32 bounded
iterations. Family IDs are:

- 0: integer add plus float add
- 1: integer multiply/add plus float multiply/add
- 2: sequential memory add plus integer-to-float and float multiply/add

Debugger expressions:

- `g_star_mixed_integer_float_complete`
- `g_star_mixed_integer_float_current`
- `g_star_mixed_integer_float_results.point_count`
- `g_star_mixed_integer_float_results.sample_count`
- `g_star_mixed_integer_float_results.measurement_overhead_cycles`
- `g_star_mixed_integer_float_results.error_flags`
- `g_star_mixed_integer_float_results.points`

Expected completion is `complete=1`, `point_count=9`, 40 completed samples per
point, and `error_flags=0`.

ELF SHA-256:
`425B15C55B9FCF87E005A01625362B3580D1249CE8F6DB4CB7237ECC6D84EBB1`
