# S32K148 deterministic automotive task WCET check

The task combines bounded sensor acquisition, sequential memory access,
plausibility branches, fixed-point control, saturation, floating-point work,
direct and deterministic indirect calls, checksum/rotate operations, a switch,
and output bit packing.

Frozen before board execution: 97.083 us nominal and 111.645 us WCET.

Debugger expressions:

- `g_star_deterministic_automotive_complete`
- `g_star_deterministic_automotive_results.completed_samples`
- `g_star_deterministic_automotive_results.measurement_overhead_cycles`
- `g_star_deterministic_automotive_results.error_flags`
- `g_star_deterministic_automotive_results.mean_execution_us_x1000`
- `g_star_deterministic_automotive_results.max_execution_us_x1000`

Success is `complete=1`, `completed_samples=40`, `error_flags=0`, and maximum
execution no greater than 111.645 us.

ELF SHA-256:
`B6D07C5BA93BA596F789822EC42B0B7E3F4EA70B1D747DE5925EB2536CA5CA91`
