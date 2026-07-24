"""Target-calibrated dynamic workload cost model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkloadCostProfile:
    """Conservative cycle costs for bounded dynamic work on one target."""

    profile_id: str
    reference_hardware: str
    clock_frequency_mhz: float
    safety_limit_ratio: float
    validated: bool
    cycles_per_work_unit: dict[str, float]
    source: str = ""

    def coefficient_for(self, workload_class: str) -> float:
        """Return the calibrated coefficient for a normalized workload class."""

        normalized = workload_class.strip().lower().replace("-", "_")
        try:
            return self.cycles_per_work_unit[normalized]
        except KeyError as exc:
            available = ", ".join(sorted(self.cycles_per_work_unit))
            raise ValueError(
                f"Unknown workload class '{workload_class}'. Available: {available}"
            ) from exc
