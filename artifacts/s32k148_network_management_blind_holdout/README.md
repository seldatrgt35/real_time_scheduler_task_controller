# S32K148 NetworkManagement blind holdout

This image measures the unmodified
`AppTask_NetworkManagement_100ms` callback-plus-packing region at seven
iterations. The model prediction was frozen before this board measurement:
19.177551 us nominal and 22.054184 us with the 15 percent engineering margin.

Read these expressions after execution stops in the final loop:

```text
g_star_network_holdout_complete
g_star_network_holdout_results.iterations
g_star_network_holdout_results.completed_samples
g_star_network_holdout_results.measurement_overhead_cycles
g_star_network_holdout_results.error_flags
g_star_network_holdout_results.mean_execution_us_x1000
g_star_network_holdout_results.max_execution_us_x1000
```

Success requires completion=1, iterations=7, completed_samples=40 and
error_flags=0. Times are microseconds multiplied by 1000.

ELF SHA-256:
`73C64B13607A69D527D9980496AFCDE04CDBE2394F5A023C3B5A388E3DD52B1A`
