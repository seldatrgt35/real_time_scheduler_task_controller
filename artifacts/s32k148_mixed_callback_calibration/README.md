# S32K148 mixed callback calibration

This image measures two independent training families at 8, 16 and 32
iterations, with eight warm-ups and 40 samples per point.

- family_id 0: callback transform
- family_id 1: callback plus payload packing/shift

Read:

```text
g_star_mixed_callback_complete
g_star_mixed_callback_current
g_star_mixed_callback_results.point_count
g_star_mixed_callback_results.sample_count
g_star_mixed_callback_results.measurement_overhead_cycles
g_star_mixed_callback_results.error_flags
g_star_mixed_callback_results.points
```

Success requires completion=1, point_count=6, sample_count=40 and
error_flags=0. Times are microseconds multiplied by 1000.
