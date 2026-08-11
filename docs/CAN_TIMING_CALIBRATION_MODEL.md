# CAN Timing Calibration Model

STAR separates a CAN transmit request into three timing domains:

1. **CPU driver time** — cycles spent executing `CAN_Send`/FlexCAN enqueue code.
   Only this component belongs in the scheduler execution budget.
2. **Peripheral latency** — maximum time from successful enqueue until the
   controller starts the frame (SOF). This is measured on the target and is not
   treated as CPU execution.
3. **Bus occupancy** — calculated from frame format, DLC, identifier width and
   configured bitrate. Worst-case bit stuffing is included.

The S32K148 `FLEXCAN_DRV_Send` CPU path is board-calibrated using NXP S32 SDK
RTM 4.0.2, ARM GCC 11.4, `-O0`, 48 MHz, Classical CAN, 11-bit ID, DLC 8 and
500 kbit/s. Forty internal-loopback samples measured 31.812 us mean/maximum
driver CPU time and 265.354 us maximum enqueue-to-controller-completion time.
STAR applies a 15% CPU margin, producing a 36.584 us scheduler budget per
bounded `CAN_Send` call.

Internal loopback does not measure enqueue-to-SOF on a physical bus. Real
arbitration, retransmission, transceiver delay and ISR-to-task notification
remain `UNVERIFIED`; therefore the calibration verifies scheduler CPU demand,
not the complete network deadline.

## Required board calibration

- Instrument immediately before and after the real non-blocking transmit API
  to obtain CPU cycles for successful, busy and queue-full paths.
- Capture the enqueue marker and CAN TX/SOF signal with a logic analyzer to
  obtain enqueue-to-SOF latency under an idle bus and a loaded bus.
- Record bitrate, identifier width, DLC, mailbox/queue depth and arbitration
  load with every result.
- Measure at least forty samples per path and preserve maximum values.

Arbitration delay from higher-priority frames, error frames and retransmission
must be supplied by a later network-level response-time model. Until those
bounds exist, STAR may verify CPU schedulability but must not claim a complete
CAN end-to-end deadline.
