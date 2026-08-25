# S32K148 body/chassis WCET blind holdout

Frozen predictions before board execution:

- point 0, WheelSpeedAndBrake: 33.1338 us WCET
- point 1, ThermalActuator: 25.6316517857 us WCET
- point 2, StabilityRequest: 39.0517 us WCET

Debugger expressions:

- `g_star_body_chassis_complete`
- `g_star_body_chassis_current`
- `g_star_body_chassis_results.point_count`
- `g_star_body_chassis_results.sample_count`
- `g_star_body_chassis_results.measurement_overhead_cycles`
- `g_star_body_chassis_results.error_flags`
- `g_star_body_chassis_results.points`

Success requires `complete=1`, `point_count=3`, 40 completed samples per point,
`error_flags=0`, and every measured maximum below its frozen WCET.

ELF SHA-256:
`81BC0274DED04B049BE6C130B3A21AAD5663D895D5FBAFA02EBC8F8BE92526BF`
