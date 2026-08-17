# S32K148 automotive DTC snapshot blind holdout

This validation-only image measures a bounded diagnostic scheduler task that
filters 16 DTC snapshots and packs accepted 24-bit codes plus status bytes into
a UDS response buffer. It was created after the conditional memory-write model
was finalized and is excluded from coefficient fitting.

The prediction frozen before board execution is:

- nominal: 40.67722685005926 us;
- safe: 46.77881087756815 us;
- overall estimate status: unverified atomic fallback.

Flash `star_s32k148_automotive_dtc_snapshot_blind_holdout.elf`, wait in the
final loop, and read:

```text
g_star_dtc_snapshot_blind_complete
g_star_dtc_snapshot_blind_results.iterations
g_star_dtc_snapshot_blind_results.completed_samples
g_star_dtc_snapshot_blind_results.measurement_overhead_cycles
g_star_dtc_snapshot_blind_results.error_flags
g_star_dtc_snapshot_blind_results.mean_execution_us_x1000
g_star_dtc_snapshot_blind_results.max_execution_us_x1000
```

Success requires `complete == 1`, `iterations == 16`,
`completed_samples == 40`, and `error_flags == 0`. Times are microseconds
multiplied by 1000.

ELF SHA-256:
`D31D09D548D31A13697F30F10790339A134B4DB6BF2DCD662542A630B366DFB9`
