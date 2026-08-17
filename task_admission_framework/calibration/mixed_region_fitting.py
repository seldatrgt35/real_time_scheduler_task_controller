"""Fit pending mixed-region families from training-only board measurements."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path


EXPECTED_POINTS = {
    "actuator": (8, 16, 32),
    "accumulator": (8, 16, 32),
    "interpolation": (8, 16, 32),
}


@dataclass(frozen=True, slots=True)
class MixedRegionPoint:
    family: str
    iterations: int
    mean_us: float
    maximum_us: float


def load_training_points(path: Path) -> tuple[MixedRegionPoint, ...]:
    """Load an explicit calibration dataset and reject holdout contamination."""
    points: list[MixedRegionPoint] = []
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row.get("dataset_role", "").strip().lower() != "calibration":
                raise ValueError("Every measurement must have dataset_role=calibration")
            source = row.get("source_file", "").strip().lower()
            if "holdout" in source:
                raise ValueError("Holdout sources cannot be used for model fitting")
            family = row.get("family", "").strip().lower()
            if family not in EXPECTED_POINTS:
                raise ValueError(f"Unknown mixed-region family: {family}")
            point = MixedRegionPoint(
                family=family,
                iterations=int(row["iterations"]),
                mean_us=float(row["mean_us"]),
                maximum_us=float(row["maximum_us"]),
            )
            if point.mean_us <= 0.0 or point.maximum_us < point.mean_us:
                raise ValueError("Measurements must satisfy 0 < mean_us <= maximum_us")
            points.append(point)
    _validate_matrix(points)
    return tuple(points)


def fit_mixed_region_families(
    points: tuple[MixedRegionPoint, ...],
) -> dict[str, object]:
    """Fit an affine mean-time model independently for each structural family."""
    _validate_matrix(points)
    families: dict[str, object] = {}
    for family, expected in EXPECTED_POINTS.items():
        family_points = sorted(
            (point for point in points if point.family == family),
            key=lambda point: point.iterations,
        )
        xs = [float(point.iterations) for point in family_points]
        ys = [point.mean_us for point in family_points]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        denominator = sum((value - x_mean) ** 2 for value in xs)
        slope = sum(
            (x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)
        ) / denominator
        intercept = y_mean - (slope * x_mean)
        predictions = [intercept + slope * x for x in xs]
        errors = [
            abs(prediction - actual) / actual * 100.0
            for prediction, actual in zip(predictions, ys)
        ]
        families[family] = {
            "iteration_us": slope,
            "intercept_us": intercept,
            "training_iterations": list(expected),
            "training_mape_percent": sum(errors) / len(errors),
            "training_max_ape_percent": max(errors),
            "training_maximum_us": max(
                point.maximum_us for point in family_points
            ),
            "validated": False,
            "status": "fitted_training_only_independent_holdout_pending",
        }
    return {
        "schema_version": 1,
        "model_kind": "mixed_region_affine_candidate",
        "dataset_role": "calibration_only",
        "families": families,
    }


def write_candidate_profile(points_path: Path, output_path: Path) -> None:
    candidate = fit_mixed_region_families(load_training_points(points_path))
    output_path.write_text(
        json.dumps(candidate, indent=2) + "\n", encoding="utf-8"
    )


def _validate_matrix(points: list[MixedRegionPoint] | tuple[MixedRegionPoint, ...]) -> None:
    actual = {
        family: tuple(sorted(
            point.iterations for point in points if point.family == family
        ))
        for family in EXPECTED_POINTS
    }
    if actual != EXPECTED_POINTS:
        raise ValueError(
            f"Calibration matrix must contain exactly {EXPECTED_TEXT}; got {actual}"
        )


EXPECTED_TEXT = ", ".join(
    f"{family}=8/16/32" for family in EXPECTED_POINTS
)
