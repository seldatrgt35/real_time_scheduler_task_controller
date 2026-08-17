# S32K148 basic gap calibration

Nine independent training points. The existing 32-iteration V2 measurements
are excluded and remain the final holdout.

| Point | Family | Iterations |
|---:|---|---:|
| 0 | Arithmetic | 8 |
| 1 | Arithmetic | 16 |
| 2 | Arithmetic | 64 |
| 3 | MaskedDivide | 8 |
| 4 | MaskedDivide | 16 |
| 5 | MaskedDivide | 64 |
| 6 | MaskedModulo | 8 |
| 7 | MaskedModulo | 16 |
| 8 | MaskedModulo | 64 |

Debugger expressions:

- `g_star_gap_complete`
- `g_star_gap_current`
- `g_star_gap_results.point_count`
- `g_star_gap_results.sample_count`
- `g_star_gap_results.measurement_overhead_cycles`
- `g_star_gap_results.error_flags`
- `g_star_gap_results.points`

Success is `complete=1`, `current=8`, `point_count=9`, `sample_count=40`, and
`error_flags=0`.

ELF SHA-256:
`F116C2B98673CB47255A5480FB489AF8E4436C41D8300E7CC27DB656B2E95ABD`
