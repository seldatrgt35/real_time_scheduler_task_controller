# S32K148 GitHub UDS real-task holdout

This image measures five unchanged scheduler task bodies from the repository's
BSD-3-Clause `openxc/uds-c` derived holdout. Model predictions were frozen in
`tools/github_uds_real_task_frozen_predictions.csv` before board execution.

Task IDs:

- 0: UDS CAN RX dispatch (VERIFIED prediction)
- 1: OBD PID decode (UNVERIFIED diagnostic prediction)
- 2: UDS response validation (UNVERIFIED, outside validated range)
- 3: DTC/session maintenance (VERIFIED prediction)
- 4: OBD request and CPU-side CAN preparation (UNSUPPORTED, no prediction)

Read:

```text
g_star_github_uds_complete
g_star_github_uds_current
g_star_github_uds_results.point_count
g_star_github_uds_results.sample_count
g_star_github_uds_results.measurement_overhead_cycles
g_star_github_uds_results.error_flags
g_star_github_uds_results.points
```

Success requires completion=1, point_count=5, sample_count=40 and
error_flags=0. Times are microseconds multiplied by 1000. `CAN_Send` is a
noinline CPU stub; peripheral, arbitration and transmission latency are not
part of these task-body measurements.

ELF SHA-256:
`7CD1EC34FD7DEBB534E087DA90B5910452719143840614A41AAD7F764FB1421D`
