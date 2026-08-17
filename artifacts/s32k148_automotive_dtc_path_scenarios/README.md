# S32K148 DTC sparse/dense path experiment

This image executes the same blind DTC snapshot task under two data scenarios.
Initialization runs outside the DWT measurement interval.

- point 0: sparse typical path, 3 of 16 records accepted;
- point 1: dense/WCET-oriented path, 16 of 16 records accepted.

The unchanged static model prediction frozen before either board run is
40.67722685005926 us nominal and 46.77881087756815 us safe. No coefficient was
changed after the sparse result.

Read:

```text
g_star_dtc_path_complete
g_star_dtc_path_current
g_star_dtc_path_results.point_count
g_star_dtc_path_results.sample_count
g_star_dtc_path_results.measurement_overhead_cycles
g_star_dtc_path_results.error_flags
g_star_dtc_path_results.points
```

Success requires `complete == 1`, `current == 1`, `point_count == 2`,
`sample_count == 40`, and `error_flags == 0`.

ELF SHA-256:
`02AE52DE52A077CC762B840EC386D30FBB3798F9C7A0C67FEFB070F9779E4C74`
