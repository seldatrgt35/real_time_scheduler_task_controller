# S32K148 basic memory calibration

Twelve independent training points. Existing 32-iteration V2 measurements are
excluded from fitting and remain holdouts.

Point order is three iterations (`8, 16, 64`) for each family:

- 0-2: sequential memory
- 3-5: random indexed memory
- 6-8: memory copy
- 9-11: memory set

Debugger expressions:

- `g_star_memory_complete`
- `g_star_memory_current`
- `g_star_memory_results.point_count`
- `g_star_memory_results.sample_count`
- `g_star_memory_results.measurement_overhead_cycles`
- `g_star_memory_results.error_flags`
- `g_star_memory_results.points`

Success is `complete=1`, `current=11`, `point_count=12`, `sample_count=40`, and
`error_flags=0`.

ELF SHA-256:
`2FA23A360AE86F0750DD18E476F027B5DA18650016A2F0A1B5478093B449D437`
