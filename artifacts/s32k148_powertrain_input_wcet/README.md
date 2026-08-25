# S32K148 PowertrainInput WCET blind check

Frozen before board execution: 19.812 us nominal and 22.7838 us WCET.

Debugger expressions:

- `g_star_powertrain_input_wcet_complete`
- `g_star_powertrain_input_wcet_results.completed_samples`
- `g_star_powertrain_input_wcet_results.measurement_overhead_cycles`
- `g_star_powertrain_input_wcet_results.error_flags`
- `g_star_powertrain_input_wcet_results.mean_execution_us_x1000`
- `g_star_powertrain_input_wcet_results.max_execution_us_x1000`

Success is `complete=1`, `completed_samples=40`, `error_flags=0`, and maximum
execution no greater than 22.7838 us.

ELF SHA-256:
`60F84B7C8B3A7E89D5EA24C4094E2997E9052313D793BB0E3AFAE88854EE67BC`
