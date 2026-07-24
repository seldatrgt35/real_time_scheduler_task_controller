"""JSON loader for target-calibrated workload cost profiles."""

from __future__ import annotations

import json
from pathlib import Path

from task_admission_framework.calibration.workload_cost_profile import (
    WorkloadCostProfile,
)


class WorkloadCostLoader:
    """Load and validate a dynamic workload calibration profile."""

    def load(self, profile_path: str | Path) -> WorkloadCostProfile:
        path = Path(profile_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not load workload cost profile: {path}") from exc

        raw_costs = data.get("cycles_per_work_unit")
        if not isinstance(raw_costs, dict) or not raw_costs:
            raise ValueError("cycles_per_work_unit must be a non-empty object.")

        costs = {
            str(name).strip().lower().replace("-", "_"): float(value)
            for name, value in raw_costs.items()
        }
        if any(value <= 0 for value in costs.values()):
            raise ValueError("All workload cost coefficients must be greater than 0.")

        clock = float(data["clock_frequency_mhz"])
        safety_ratio = float(data.get("safety_limit_ratio", 0.8))
        if clock <= 0:
            raise ValueError("clock_frequency_mhz must be greater than 0.")
        if not 0 < safety_ratio <= 1:
            raise ValueError("safety_limit_ratio must be in the interval (0, 1].")

        return WorkloadCostProfile(
            profile_id=str(data["profile_id"]),
            reference_hardware=str(data["reference_hardware"]),
            clock_frequency_mhz=clock,
            safety_limit_ratio=safety_ratio,
            validated=bool(data.get("validated", False)),
            cycles_per_work_unit=costs,
            source=str(data.get("source", "")),
        )
