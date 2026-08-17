import csv
from pathlib import Path
import tempfile
import unittest

from task_admission_framework.calibration.mixed_region_fitting import (
    fit_mixed_region_families,
    load_training_points,
)


class MixedRegionFittingTest(unittest.TestCase):
    def test_affine_candidate_is_fitted_but_not_marked_validated(self) -> None:
        path = self._write_measurements()
        candidate = fit_mixed_region_families(load_training_points(path))

        actuator = candidate["families"]["actuator"]
        self.assertAlmostEqual(0.75, actuator["iteration_us"])
        self.assertAlmostEqual(2.0, actuator["intercept_us"])
        self.assertFalse(actuator["validated"])
        self.assertIn("holdout_pending", actuator["status"])

    def test_holdout_source_is_rejected_from_training(self) -> None:
        path = self._write_measurements(
            source_file="body_chassis_control_holdout.c"
        )
        with self.assertRaisesRegex(ValueError, "Holdout sources"):
            load_training_points(path)

    def test_non_calibration_role_is_rejected(self) -> None:
        path = self._write_measurements(dataset_role="holdout")
        with self.assertRaisesRegex(ValueError, "dataset_role=calibration"):
            load_training_points(path)

    def _write_measurements(
        self,
        source_file: str = "mixed_helper_saturation_calibration.c",
        dataset_role: str = "calibration",
    ) -> Path:
        directory = Path(tempfile.mkdtemp())
        path = directory / "measurements.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=(
                "dataset_role", "source_file", "family", "iterations",
                "mean_us", "maximum_us",
            ))
            writer.writeheader()
            slopes = {
                "actuator": (2.0, 0.75),
                "accumulator": (1.5, 0.625),
                "interpolation": (3.0, 1.5),
            }
            for family, (intercept, slope) in slopes.items():
                for iterations in (8, 16, 32):
                    mean = intercept + (slope * iterations)
                    writer.writerow({
                        "dataset_role": dataset_role,
                        "source_file": source_file,
                        "family": family,
                        "iterations": iterations,
                        "mean_us": mean,
                        "maximum_us": mean * 1.05,
                    })
        return path


if __name__ == "__main__":
    unittest.main()
