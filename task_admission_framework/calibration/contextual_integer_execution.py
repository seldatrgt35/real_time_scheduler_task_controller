"""Execution estimate for the board-validated S32K148 O0 uint32 subset."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


DEFAULT_PROFILE = Path(__file__).with_name("profiles") / "S32K148_contextual_integer_O0.json"


@dataclass(frozen=True, slots=True)
class ContextualIntegerEstimate:
    nominal_us: float | None
    safe_us: float | None
    verified: bool
    breakdown_us: dict[str, float]
    unsupported_features: tuple[str, ...]
    note: str


def estimate_contextual_integer(
    counts: dict[str, int], profile_path: Path = DEFAULT_PROFILE
) -> ContextualIntegerEstimate:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    costs = profile["cost_us_per_occurrence"]
    administrative = {"loop_iterations", "loop_invocations", "memory_group_loop_iterations", "memory_group_loop_invocations", "fixed_group_loop_iterations", "fixed_group_loop_invocations", "floating_group_loop_iterations", "floating_group_loop_invocations", "communication_group_loop_iterations", "communication_group_loop_invocations"}
    memory_costs = profile.get("memory_group_cost_us_per_work_unit", {})
    fixed_costs = profile.get("fixed_group_cost_us_per_work_unit", {})
    floating_costs = profile.get("floating_group_cost_us_per_work_unit", {})
    communication_costs = profile.get("communication_group_cost_us_per_work_unit", {})
    unsupported = tuple(sorted(
        name for name, count in counts.items()
        if count > 0 and name not in administrative and name not in costs and name not in memory_costs and name not in fixed_costs and name not in floating_costs and name not in communication_costs
    ))
    if unsupported:
        return ContextualIntegerEstimate(
            None, None, False, {}, unsupported,
            "Unsupported contextual integer features prevent a safe estimate.",
        )
    operations = sum(
        count * costs[name] for name, count in counts.items() if name in costs
    )
    grouped_iterations = counts.get("memory_group_loop_iterations", 0)
    grouped_invocations = counts.get("memory_group_loop_invocations", 0)
    grouped_iterations += counts.get("fixed_group_loop_iterations", 0)
    grouped_invocations += counts.get("fixed_group_loop_invocations", 0)
    grouped_iterations += counts.get("floating_group_loop_iterations", 0)
    grouped_invocations += counts.get("floating_group_loop_invocations", 0)
    grouped_iterations += counts.get("communication_group_loop_iterations", 0)
    grouped_invocations += counts.get("communication_group_loop_invocations", 0)
    loop_control = max(0, counts.get("loop_iterations", 0) - grouped_iterations) * profile["loop_iteration_us"]
    loop_setup = max(0, counts.get("loop_invocations", 0) - grouped_invocations) * profile["loop_invocation_intercept_us"]
    memory_raw = sum(count * memory_costs[name] for name, count in counts.items() if name in memory_costs)
    memory_time = 0.0
    if memory_raw:
        correction = profile["memory_group_correction"]
        memory_time = memory_raw * correction["scale"] + correction["intercept_us"]
    fixed_raw = sum(count * fixed_costs[name] for name, count in counts.items() if name in fixed_costs)
    fixed_time = 0.0
    if fixed_raw:
        correction = profile["fixed_group_correction"]
        fixed_time = fixed_raw * correction["scale"] + correction["intercept_us"]
    floating_time = sum(count * floating_costs[name] for name, count in counts.items() if name in floating_costs)
    communication_raw = sum(count * communication_costs[name] for name, count in counts.items() if name in communication_costs)
    communication_time = 0.0
    if communication_raw:
        correction = profile["communication_group_correction"]
        communication_time = communication_raw * correction["scale"] + correction["intercept_us"]
    nominal = operations + loop_control + loop_setup + memory_time + fixed_time + floating_time + communication_time
    margin = profile["engineering_margin_percent"] / 100.0
    return ContextualIntegerEstimate(
        nominal, nominal * (1.0 + margin), True,
        {"loop_setup": loop_setup, "loop_control": loop_control,
         "contextual_operations": operations, "memory_group": memory_time,
         "fixed_point_group": fixed_time, "floating_point_group": floating_time,
         "communication_group": communication_time},
        (), (
            "Validated for the S32K148 ARM GCC 11.4 O0 contextual subset."
        ),
    )
