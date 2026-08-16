# S32K148 O0 body/chassis compound holdout

The board run completed all 40 samples for all five tasks with `error_flags = 0`.
Predictions were frozen before the ELF was measured; these results were not used
to fit the model.

| Task | Predicted (us) | Admission (us) | Board (us) | APE | Covered |
|---|---:|---:|---:|---:|:---:|
| Wheel/brake 5 ms | 20.832 | 23.957 | 29.125 | 28.47% | No |
| Thermal actuator 10 ms | 10.711 | 12.318 | 23.500 | 54.42% | No |
| Stability control 20 ms | 17.852 | 20.529 | 33.416 | 46.58% | No |
| Fault manager 50 ms | 22.437 | 25.802 | 11.812 | 89.95% | Yes |
| Status communication 100 ms | 51.286 | 58.979 | 41.312 | 24.14% | Yes |

- MAPE: **48.7131%**
- Maximum APE: **89.9509%**
- Admission-margin coverage: **2/5**

The isolated execution-component holdout remains valid for its exact component
shapes, but it does not generalize additively to realistic compound task bodies.
Consequently component-derived compound estimates are marked `UNVERIFIED` until
an interaction-aware compound model passes an independent holdout.
