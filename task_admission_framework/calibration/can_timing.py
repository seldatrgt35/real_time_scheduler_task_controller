"""Separated timing model for Classical CAN transmission.

CPU execution, controller/peripheral latency and physical bus occupancy have
different scheduling meanings and must never be collapsed into one guessed
API cost.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class ClassicalCanFrame:
    """Classical CAN data-frame parameters supported by the first model."""

    payload_bytes: int
    bitrate_bps: int
    identifier_bits: int = 11

    def __post_init__(self) -> None:
        if not 0 <= self.payload_bytes <= 8:
            raise ValueError("Classical CAN payload must be between 0 and 8 bytes.")
        if self.bitrate_bps <= 0:
            raise ValueError("CAN bitrate must be positive.")
        if self.identifier_bits not in {11, 29}:
            raise ValueError("Classical CAN identifier width must be 11 or 29 bits.")


@dataclass(frozen=True, slots=True)
class CanDriverCalibration:
    """Board measurements that cannot be inferred from the C source."""

    cpu_driver_mean_us: float | None = None
    cpu_driver_max_us: float | None = None
    peripheral_enqueue_to_sof_max_us: float | None = None
    controller_completion_mean_us: float | None = None
    controller_completion_max_us: float | None = None
    send_return_to_irq_mean_us: float | None = None
    send_return_to_irq_max_us: float | None = None
    irq_handler_mean_us: float | None = None
    irq_handler_max_us: float | None = None
    irq_exit_to_task_mean_us: float | None = None
    irq_exit_to_task_max_us: float | None = None
    engineering_margin_percent: float = 15.0

    def __post_init__(self) -> None:
        values = (
            self.cpu_driver_mean_us,
            self.cpu_driver_max_us,
            self.peripheral_enqueue_to_sof_max_us,
            self.controller_completion_mean_us,
            self.controller_completion_max_us,
            self.send_return_to_irq_mean_us,
            self.send_return_to_irq_max_us,
            self.irq_handler_mean_us,
            self.irq_handler_max_us,
            self.irq_exit_to_task_mean_us,
            self.irq_exit_to_task_max_us,
        )
        if any(value is not None and value < 0.0 for value in values):
            raise ValueError("CAN calibration times cannot be negative.")
        if self.engineering_margin_percent < 0.0:
            raise ValueError("Engineering margin cannot be negative.")


@dataclass(frozen=True, slots=True)
class CanTimingEstimate:
    cpu_driver_mean_us: float | None
    cpu_driver_safe_us: float | None
    peripheral_enqueue_to_sof_max_us: float | None
    controller_completion_mean_us: float | None
    controller_completion_max_us: float | None
    send_return_to_irq_max_us: float | None
    irq_handler_max_us: float | None
    irq_exit_to_task_max_us: float | None
    bus_nominal_bits: int
    bus_worst_case_bits: int
    bus_nominal_us: float
    bus_worst_case_us: float
    scheduler_cpu_verified: bool
    end_to_end_verified: bool
    end_to_end_safe_us: float | None
    note: str


def estimate_classical_can_timing(
    frame: ClassicalCanFrame,
    calibration: CanDriverCalibration,
) -> CanTimingEstimate:
    """Return separated CPU, peripheral and bus timing components.

    The scheduler execution budget contains CPU driver time only. Peripheral
    waiting and frame transmission are reported as end-to-end/resource time.
    Worst-case bus time includes maximum bit stuffing and three intermission
    bits, but not arbitration delay caused by other frames or error-frame
    retransmission.
    """

    arbitration_bits = 12 if frame.identifier_bits == 11 else 32
    stuffed_region_bits = (
        1  # start of frame
        + arbitration_bits
        + 6  # control field
        + (8 * frame.payload_bytes)
        + 15  # CRC sequence
    )
    trailer_and_intermission_bits = 13  # CRC delimiter, ACK, EOF and IFS
    maximum_stuff_bits = math.floor((stuffed_region_bits - 1) / 4)
    nominal_bits = stuffed_region_bits + trailer_and_intermission_bits
    worst_bits = nominal_bits + maximum_stuff_bits
    nominal_us = nominal_bits * 1_000_000.0 / frame.bitrate_bps
    worst_us = worst_bits * 1_000_000.0 / frame.bitrate_bps

    cpu_verified = calibration.cpu_driver_max_us is not None
    cpu_safe_us = None
    if calibration.cpu_driver_max_us is not None:
        cpu_safe_us = calibration.cpu_driver_max_us * (
            1.0 + calibration.engineering_margin_percent / 100.0
        )
    end_to_end_verified = (
        cpu_safe_us is not None
        and calibration.peripheral_enqueue_to_sof_max_us is not None
    )
    end_to_end_safe_us = None
    if end_to_end_verified:
        end_to_end_safe_us = (
            cpu_safe_us
            + calibration.peripheral_enqueue_to_sof_max_us
            + worst_us
        )

    missing = []
    if calibration.cpu_driver_max_us is None:
        missing.append("board-measured CPU driver maximum")
    if calibration.peripheral_enqueue_to_sof_max_us is None:
        missing.append("board-measured peripheral enqueue-to-SOF maximum")
    note = (
        "UNVERIFIED: missing " + " and ".join(missing) + "."
        if missing
        else (
            "Verified measured components plus calculated Classical CAN frame "
            "occupancy; arbitration interference and retransmission remain external."
        )
    )
    return CanTimingEstimate(
        cpu_driver_mean_us=calibration.cpu_driver_mean_us,
        cpu_driver_safe_us=cpu_safe_us,
        peripheral_enqueue_to_sof_max_us=(
            calibration.peripheral_enqueue_to_sof_max_us
        ),
        controller_completion_mean_us=calibration.controller_completion_mean_us,
        controller_completion_max_us=calibration.controller_completion_max_us,
        send_return_to_irq_max_us=calibration.send_return_to_irq_max_us,
        irq_handler_max_us=calibration.irq_handler_max_us,
        irq_exit_to_task_max_us=calibration.irq_exit_to_task_max_us,
        bus_nominal_bits=nominal_bits,
        bus_worst_case_bits=worst_bits,
        bus_nominal_us=nominal_us,
        bus_worst_case_us=worst_us,
        scheduler_cpu_verified=cpu_verified,
        end_to_end_verified=end_to_end_verified,
        end_to_end_safe_us=end_to_end_safe_us,
        note=note,
    )


# S32K148 EVB, ARM GCC 11.4, -O0, 48 MHz, NXP S32 SDK RTM 4.0.2,
# FLEXCAN_DRV_Send, Classical CAN, 11-bit ID, DLC 8, 500 kbit/s, 40 samples.
S32K148_FLEXCAN_LOOPBACK_O0 = CanDriverCalibration(
    cpu_driver_mean_us=31.812,
    cpu_driver_max_us=31.812,
    controller_completion_mean_us=264.395,
    controller_completion_max_us=265.354,
    send_return_to_irq_mean_us=236.187,
    send_return_to_irq_max_us=236.312,
    irq_handler_mean_us=215.583,
    irq_handler_max_us=215.708,
    irq_exit_to_task_mean_us=272.791,
    irq_exit_to_task_max_us=275.020,
    engineering_margin_percent=15.0,
)
