# S32K148 conditional memory-write calibration

This training image isolates the interaction between a three-condition branch,
indexed payload reads, indexed destination writes, and destination/sequence
updates. It does not contain or fit the GitHub ISO-TP holdout.

## Matrix

- points 0..2: 1 write per accepted iteration at 8, 16, 32 iterations;
- points 3..5: 2 writes per accepted iteration at 8, 16, 32 iterations;
- points 6..8: 4 writes per accepted iteration at 8, 16, 32 iterations.

Each point uses 8 warm-ups followed by 40 measured samples. The build uses ARM
GCC 11.4, `-O0`, Cortex-M4 Thumb, soft-float ABI, and a 48 MHz core-clock
conversion. Times are stored as microseconds multiplied by 1000.

Flash `star_s32k148_conditional_memory_write_calibration.elf`, wait in the final
loop, then read:

```text
g_star_conditional_memory_write_complete
g_star_conditional_memory_write_current
g_star_conditional_memory_write_results.point_count
g_star_conditional_memory_write_results.sample_count
g_star_conditional_memory_write_results.measurement_overhead_cycles
g_star_conditional_memory_write_results.error_flags
g_star_conditional_memory_write_results.points
```

Success requires `complete == 1`, `current == 8`, `point_count == 9`,
`sample_count == 40`, and `error_flags == 0`.

ELF SHA-256:
`48EB7D8DD4934A09D3B0CC6B167A45F7D857E4DAD38450BFD5D3A750CA24E7D2`

Board measurements from this image may train a conditional memory-write
interaction term. The independent ISO-TP and body/chassis holdouts remain
validation-only and must not be included in fitting.
