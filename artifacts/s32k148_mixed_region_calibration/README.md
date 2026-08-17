# S32K148 mixed-region calibration image

- Toolchain: ARM GCC 11.4
- Optimization: `-O0`
- ABI: Cortex-M4 Thumb, soft-float
- Core clock: 48 MHz
- Samples: 40 per point, after 8 warm-ups
- Points: actuator, accumulator and interpolation at 8/16/32 iterations

Flash `star_s32k148_mixed_region_calibration.elf`. After the target stops in
the final loop, read these GDB expressions:

```text
g_star_mixed_region_complete
g_star_mixed_region_current
g_star_mixed_region_results.point_count
g_star_mixed_region_results.sample_count
g_star_mixed_region_results.measurement_overhead_cycles
g_star_mixed_region_results.error_flags
g_star_mixed_region_results.points
```

Success requires `g_star_mixed_region_complete == 1`, `error_flags == 0`,
`point_count == 9`, and `sample_count == 40`. Times are stored as microseconds
multiplied by 1000. Family IDs are actuator=0, accumulator=1,
interpolation=2.
