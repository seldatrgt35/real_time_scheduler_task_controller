# S32K148 holdout-v2 path-equivalent scenarios

This ELF measures the same three task functions under three input scenarios.
Scenario setup is outside the DWT timed interval.

Debugger expressions:

- `g_star_path_complete`
- `g_star_path_current`
- `g_star_path_results.point_count`
- `g_star_path_results.sample_count`
- `g_star_path_results.measurement_overhead_cycles`
- `g_star_path_results.error_flags`
- `g_star_path_results.points`

Point mapping:

| Point | Task | Scenario |
|---:|---|---|
| 0 | BatteryContactorSupervisor | typical |
| 1 | BatteryContactorSupervisor | boundary: voltage delta 85, coil thresholds 90/680 |
| 2 | BatteryContactorSupervisor | worst-path candidate: disagreement/current faults/state transitions |
| 3 | WheelSpeedFusion | typical: ascending median inputs |
| 4 | WheelSpeedFusion | boundary: equal median inputs |
| 5 | WheelSpeedFusion | worst-path: reverse-sorted median inputs |
| 6 | DiagnosticEventAging | typical |
| 7 | DiagnosticEventAging | boundary: confirm=2, heal=4 |
| 8 | DiagnosticEventAging | worst-path candidate: inactive, heal transition, confirmed status |

Valid completion is `complete=1`, `current=8`, `point_count=9`,
`sample_count=40`, and `error_flags=0`.

ELF SHA-256:
`7424134A92BF03CCAFF524F7EE6E7AA114EDFDAE52A547E7E3F76F094668EFC5`
