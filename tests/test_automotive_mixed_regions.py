from pathlib import Path
import unittest

from task_admission_framework.analyzer.analyzer import StaticAnalyzer
from task_admission_framework.calibration.contextual_integer_execution import (
    estimate_contextual_integer,
)


class AutomotiveMixedRegionRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        examples = Path(__file__).parents[1] / "task_admission_framework" / "examples"
        sources = (
            examples / "automotive_feature_reference.c",
            examples / "body_chassis_control_holdout.c",
        )
        cls.profiles = {
            profile.task_name: profile
            for source in sources
            for profile in StaticAnalyzer().analyze_file(source)
        }

    def test_realistic_clamp_loops_remain_structurally_visible(self) -> None:
        expected_iterations = {
            "AppTask_TorqueCoordination_20ms": (
                16, "interpolation", True, 48.937
            ),
            "BccTask_ThermalActuator_10ms": (
                12, "actuator", True, 22.288392857142854
            ),
            "BccTask_StabilityRequest_20ms": (
                20, "accumulator", True, 33.958
            ),
        }
        for task_name, (
            iterations, shape, verified, nominal_us
        ) in expected_iterations.items():
            with self.subTest(task=task_name):
                profile = self.profiles[task_name]
                counts = profile.contextual_integer_counts

                self.assertEqual(verified, profile.dynamic_bound_verified)
                self.assertNotIn("powertrain_saturation_clamp_i32", counts)
                self.assertEqual(1, counts[f"mixed_region_shape_{shape}"])
                self.assertEqual(iterations, counts["mixed_region_bounded_iterations"])
                self.assertGreater(counts["mixed_region_array_access"], 0)
                self.assertGreater(counts["mixed_region_branch"], 0)
                self.assertGreater(counts["mixed_region_direct_call"], 0)
                self.assertGreater(counts["mixed_region_body_add_sub"], 0)
                self.assertGreater(counts["mixed_region_body_compare"], 0)
                self.assertGreater(counts["mixed_region_callee_multiply"], 0)
                self.assertGreater(counts["mixed_region_callee_divide_modulo"], 0)

                estimate = estimate_contextual_integer(counts)
                self.assertEqual(verified, estimate.verified)
                if verified:
                    self.assertAlmostEqual(nominal_us, estimate.nominal_us)
                    self.assertNotIn(
                        "unsupported_mixed_execution_region", counts
                    )
                else:
                    self.assertIsNone(estimate.nominal_us)
                    self.assertIsNone(estimate.safe_us)
                    self.assertEqual(
                        1, counts["unsupported_mixed_execution_region"]
                    )

    def test_training_matrix_covers_three_shapes_and_three_bounds(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "mixed_helper_saturation_calibration.c"
        )
        profiles = {
            profile.task_name: profile
            for profile in StaticAnalyzer().analyze_file(source)
        }
        for family in ("Actuator", "Accumulator", "Interpolation"):
            for bound in (8, 16, 32):
                with self.subTest(family=family, bound=bound):
                    counts = profiles[
                        f"MixedCalibration_{family}_{bound}"
                    ].contextual_integer_counts
                    self.assertEqual(
                        bound, counts["mixed_region_bounded_iterations"]
                    )
                    self.assertGreater(counts["mixed_region_array_access"], 0)
                    self.assertGreater(counts["mixed_region_branch"], 0)
                    self.assertGreater(counts["mixed_region_direct_call"], 0)
                    self.assertNotIn(
                        "unsupported_mixed_execution_region", counts
                    )
                    self.assertEqual(
                        bound,
                        counts[f"mixed_region_{family.lower()}_i32"],
                    )

        actuator = profiles[
            "MixedCalibration_Actuator_16"
        ].contextual_integer_counts
        accumulator = profiles[
            "MixedCalibration_Accumulator_16"
        ].contextual_integer_counts
        interpolation = profiles[
            "MixedCalibration_Interpolation_16"
        ].contextual_integer_counts
        self.assertGreater(
            actuator["mixed_region_array_access"],
            accumulator["mixed_region_array_access"],
        )
        self.assertIn("mixed_region_body_bitwise", interpolation)
        self.assertIn("mixed_region_callee_add_sub", interpolation)

    def test_interpolation_blind_holdout_is_verified_after_board_pass(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "task_admission_framework"
            / "examples"
            / "mixed_interpolation_blind_holdout.c"
        )
        profile = next(
            item for item in StaticAnalyzer().analyze_file(source)
            if item.task_name == "MixedInterpolationHoldout_24"
        )
        counts = profile.contextual_integer_counts

        self.assertEqual(24, counts["mixed_region_bounded_iterations"])
        self.assertEqual(1, counts["mixed_region_shape_interpolation"])
        self.assertEqual(24, counts["mixed_region_interpolation_i32"])
        self.assertNotIn("unsupported_mixed_execution_region", counts)
        estimate = estimate_contextual_integer(counts)
        self.assertTrue(estimate.verified)
        self.assertAlmostEqual(72.708, estimate.nominal_us)
        self.assertAlmostEqual(83.6142, estimate.safe_us)


if __name__ == "__main__":
    unittest.main()
