# S32K148 lishen2/isotp-c blind holdout

This image measures two bounded scheduler tasks derived from the receive-side
behavior of MIT-licensed `lishen2/isotp-c` at pinned commit
`5593428d95af10dde1e565cebcda16089fc74857`.

The model predictions were frozen before board execution:

- task 0, consecutive-frame reassembly: 14.506486 us nominal,
  16.682459 us safe;
- task 1, protocol-error aging: 28.270000 us nominal, 32.510500 us safe.

Read:

```text
g_star_github_isotp_complete
g_star_github_isotp_current
g_star_github_isotp_results.point_count
g_star_github_isotp_results.sample_count
g_star_github_isotp_results.measurement_overhead_cycles
g_star_github_isotp_results.error_flags
g_star_github_isotp_results.points
```

Success requires completion=1, current=1, point_count=2, sample_count=40 and
error_flags=0. Times are microseconds multiplied by 1000.

ELF SHA-256:
`D752F35D8B13991A680E50D78EB94D84F8ACEE106AFC3B00AD96E5D59581FEE3`
