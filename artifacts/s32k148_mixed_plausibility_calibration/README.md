# S32K148 mixed plausibility calibration

This training image measures the mixed memory/accumulation/branch/bitwise
plausibility family at 8, 16 and 32 iterations. Each point has eight warm-ups
and 40 samples. WheelSpeedBrake is not included in this image and remains the
independent 24-iteration holdout.

Read these expressions after flashing:

```text
g_star_mixed_plausibility_complete
g_star_mixed_plausibility_current
g_star_mixed_plausibility_results.point_count
g_star_mixed_plausibility_results.sample_count
g_star_mixed_plausibility_results.measurement_overhead_cycles
g_star_mixed_plausibility_results.error_flags
g_star_mixed_plausibility_results.points
```

Success requires completion=1, point_count=3, sample_count=40 and
error_flags=0. Times are microseconds multiplied by 1000.
