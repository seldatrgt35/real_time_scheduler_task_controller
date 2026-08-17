# S32K148 mixed interpolation blind holdout

This image is the independent 24-iteration interpolation holdout. Its frozen
prediction, recorded before board measurement, is 72.708 us nominal and
83.6142 us with the mandatory 15 percent admission margin.

After flashing the ELF, read:

```text
g_star_mixed_interpolation_holdout_complete
g_star_mixed_interpolation_holdout_results.iterations
g_star_mixed_interpolation_holdout_results.completed_samples
g_star_mixed_interpolation_holdout_results.measurement_overhead_cycles
g_star_mixed_interpolation_holdout_results.error_flags
g_star_mixed_interpolation_holdout_results.mean_execution_us_x1000
g_star_mixed_interpolation_holdout_results.max_execution_us_x1000
```

Success requires completion=1, iterations=24, completed_samples=40 and
error_flags=0. The final two values are microseconds multiplied by 1000.
