import unittest

from task_admission_framework.calibration.can_timing import (
    CanDriverCalibration,
    ClassicalCanFrame,
    S32K148_FLEXCAN_LOOPBACK_O0,
    estimate_classical_can_timing,
)


class CanTimingTest(unittest.TestCase):
    def test_standard_eight_byte_frame_at_500_kbps(self):
        estimate = estimate_classical_can_timing(
            ClassicalCanFrame(payload_bytes=8, bitrate_bps=500_000),
            CanDriverCalibration(),
        )
        self.assertEqual(111, estimate.bus_nominal_bits)
        self.assertEqual(135, estimate.bus_worst_case_bits)
        self.assertAlmostEqual(222.0, estimate.bus_nominal_us)
        self.assertAlmostEqual(270.0, estimate.bus_worst_case_us)
        self.assertFalse(estimate.scheduler_cpu_verified)
        self.assertFalse(estimate.end_to_end_verified)

    def test_measured_driver_and_peripheral_produce_separated_budget(self):
        estimate = estimate_classical_can_timing(
            ClassicalCanFrame(payload_bytes=8, bitrate_bps=500_000),
            CanDriverCalibration(
                cpu_driver_mean_us=4.0,
                cpu_driver_max_us=5.0,
                peripheral_enqueue_to_sof_max_us=12.0,
            ),
        )
        self.assertAlmostEqual(5.75, estimate.cpu_driver_safe_us)
        self.assertAlmostEqual(287.75, estimate.end_to_end_safe_us)
        self.assertTrue(estimate.scheduler_cpu_verified)
        self.assertTrue(estimate.end_to_end_verified)

    def test_classical_can_rejects_can_fd_payload(self):
        with self.assertRaises(ValueError):
            ClassicalCanFrame(payload_bytes=64, bitrate_bps=500_000)

    def test_s32k148_board_calibration_keeps_cpu_and_completion_separate(self):
        estimate = estimate_classical_can_timing(
            ClassicalCanFrame(payload_bytes=8, bitrate_bps=500_000),
            S32K148_FLEXCAN_LOOPBACK_O0,
        )
        self.assertAlmostEqual(36.5838, estimate.cpu_driver_safe_us, places=4)
        self.assertAlmostEqual(265.354, estimate.controller_completion_max_us)
        self.assertAlmostEqual(236.312, estimate.send_return_to_irq_max_us)
        self.assertAlmostEqual(215.708, estimate.irq_handler_max_us)
        self.assertAlmostEqual(275.020, estimate.irq_exit_to_task_max_us)
        self.assertTrue(estimate.scheduler_cpu_verified)
        self.assertFalse(estimate.end_to_end_verified)


if __name__ == "__main__":
    unittest.main()
