# S32K148 TorqueCoordination WCET blind check

Frozen before board execution:

- nominal: 48.937 us
- WCET estimate with 15% margin: 56.27755 us
- deadline: 20000 us

Debugger expressions:

- `g_star_torque_wcet_complete`
- `g_star_torque_wcet_results.completed_samples`
- `g_star_torque_wcet_results.measurement_overhead_cycles`
- `g_star_torque_wcet_results.error_flags`
- `g_star_torque_wcet_results.mean_execution_us_x1000`
- `g_star_torque_wcet_results.max_execution_us_x1000`

Success before comparison is `complete=1`, `completed_samples=40`, and
`error_flags=0`. WCET coverage passes only if maximum execution is no greater
than 56.27755 us.

ELF SHA-256:
`4E2023F53C750E1A6AB5BAAD3562BFDC3BD985F37EC3E27587244CF8E6F021BA`
