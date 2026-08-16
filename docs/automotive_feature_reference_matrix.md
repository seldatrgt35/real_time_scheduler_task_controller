# Automotive Feature Reference Matrix

This reference is realistic, deterministic scheduler-task code used to verify
STAR recognition independently of calibration function names. It is
MISRA-oriented but is not a formal MISRA compliance claim.

| Scheduler task | Automotive responsibility | Expected STAR structures |
|---|---|---|
| `AppTask_PowertrainInput_5ms` | ADC aggregation and pedal plausibility | bounded array access, integer add, branch, bitwise mask and shift |
| `AppTask_SignalConditioning_10ms` | Q15 low-pass filtering | sequential memory, signed arithmetic, multiply, divide and conversion |
| `AppTask_TorqueCoordination_20ms` | map interpolation and torque limiting | indexed lookup, direct helper call, 64-bit intermediate, divide and saturation |
| `AppTask_Diagnostics_50ms` | DTC debounce and diagnostic state machine | bounded memory update, nested branch, bitset and switch dispatch |
| `AppTask_NetworkManagement_100ms` | CAN payload packing and checksum preparation | buffer write, shift/packing, indirect callback and bounded checksum helper |

The CAN task deliberately stops at payload preparation. Real FlexCAN driver
CPU cost, peripheral completion, arbitration and bus transmission remain
separate calibrated/external timing components.
