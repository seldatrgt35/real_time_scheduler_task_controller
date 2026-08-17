# S32K148 basic control calibration

Twelve independent training points. Existing 32-iteration V2 measurements are
excluded from fitting and remain holdouts.

- 0-2: branch, iterations 8/16/64
- 3-5: callback, iterations 8/16/64
- 6-8: switch, iterations 8/16/64
- 9-11: checksum, iterations 8/16/64

Debugger expressions:

- `g_star_control_complete`
- `g_star_control_current`
- `g_star_control_results.point_count`
- `g_star_control_results.sample_count`
- `g_star_control_results.measurement_overhead_cycles`
- `g_star_control_results.error_flags`
- `g_star_control_results.points`

Success is `complete=1`, `current=11`, `point_count=12`, `sample_count=40`, and
`error_flags=0`.

ELF SHA-256:
`47E13DBEC3C66CC7FEEE1481A6B4E265E97C7A774A9AA8B136961B071320936D`
