# S32K148 nested-loop WCET blind holdout

The measured task has an 8-iteration outer sensor loop and a 4-iteration
inner sample loop. The model expands this to 32 inner memory/accumulation work
units plus the outer-loop post-processing.

Frozen before board execution: 33.7085767960 us nominal and 38.7648633154 us
WCET.

Debugger expressions:

- `g_star_nested_loop_complete`
- `g_star_nested_loop_results.completed_samples`
- `g_star_nested_loop_results.measurement_overhead_cycles`
- `g_star_nested_loop_results.error_flags`
- `g_star_nested_loop_results.mean_execution_us_x1000`
- `g_star_nested_loop_results.max_execution_us_x1000`

Success requires `complete=1`, 40 completed samples, `error_flags=0`, and a
maximum execution time no greater than 38.7648633154 us.

ELF SHA-256:
`968A5271FE5BA51473FFE7DC924FC1DAED391AF9EBD826A3CDEA8E962ACC53F2`
