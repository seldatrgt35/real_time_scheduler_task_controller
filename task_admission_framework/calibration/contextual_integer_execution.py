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
    administrative = {"loop_iterations", "loop_invocations", "memory_group_loop_iterations", "memory_group_loop_invocations", "fixed_group_loop_iterations", "fixed_group_loop_invocations", "floating_group_loop_iterations", "floating_group_loop_invocations", "communication_group_loop_iterations", "communication_group_loop_invocations", "powertrain_group_loop_iterations", "powertrain_group_loop_invocations", "compound_group_loop_iterations", "compound_group_loop_invocations", "mixed_shape_group_loop_iterations", "mixed_shape_group_loop_invocations"}
    memory_costs = profile.get("memory_group_cost_us_per_work_unit", {})
    fixed_costs = profile.get("fixed_group_cost_us_per_work_unit", {})
    floating_costs = profile.get("floating_group_cost_us_per_work_unit", {})
    communication_costs = profile.get("communication_group_cost_us_per_work_unit", {})
    powertrain_costs = profile.get("powertrain_group_cost_us_per_work_unit", {})
    compound_costs = profile.get("automotive_compound_cost_us_per_work_unit", {})
    compound_intercepts = profile.get("automotive_compound_intercept_us", {})
    mixed_shape_costs = profile.get("mixed_shape_cost_us_per_work_unit", {})
    component_costs = profile.get("component_cost_us_per_work_unit", {})
    mixed_region_costs = profile.get(
        "mixed_region_cost_us_per_iteration", {}
    )
    mixed_region_intercepts = profile.get(
        "mixed_region_intercept_us", {}
    )
    mixed_shape_intercepts = profile.get("mixed_shape_intercept_us", {})
    unsupported_set = {
        name for name, count in counts.items()
        if count > 0 and name not in administrative and name not in costs and name not in memory_costs and name not in fixed_costs and name not in floating_costs and name not in communication_costs and name not in powertrain_costs and name not in compound_costs and name not in mixed_shape_costs and name not in component_costs and name not in mixed_region_costs and not name.startswith("mixed_region_") and not name.endswith("_invocations")
    }
    mixed_shapes = {
        name.removeprefix("mixed_region_shape_")
        for name, count in counts.items()
        if count > 0 and name.startswith("mixed_region_shape_")
    }
    calibrated_mixed = {
        name.removeprefix("mixed_region_").removesuffix("_i32")
        for name, count in counts.items()
        if count > 0 and name in mixed_region_costs
    }
    has_mixed_description = any(
        count > 0 and name.startswith("mixed_region_")
        for name, count in counts.items()
    )
    if (
        has_mixed_description
        and "unsupported_mixed_execution_region" not in counts
        and (
            len(mixed_shapes) != 1
            or calibrated_mixed != mixed_shapes
            or counts.get("mixed_region_group_loop_iterations", 0)
            != counts.get("mixed_region_bounded_iterations", 0)
        )
    ):
        unsupported_set.add("inconsistent_mixed_execution_region")
    unsupported = tuple(sorted(unsupported_set))
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
    grouped_iterations += counts.get("powertrain_group_loop_iterations", 0)
    grouped_invocations += counts.get("powertrain_group_loop_invocations", 0)
    grouped_iterations += counts.get("compound_group_loop_iterations", 0)
    grouped_invocations += counts.get("compound_group_loop_invocations", 0)
    grouped_iterations += counts.get("mixed_shape_group_loop_iterations", 0)
    grouped_invocations += counts.get("mixed_shape_group_loop_invocations", 0)
    grouped_iterations += counts.get("mixed_region_group_loop_iterations", 0)
    grouped_invocations += counts.get("mixed_region_group_loop_invocations", 0)
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
    mixed_limits = profile.get("mixed_memory_communication_correction", {})
    mixed_memory_communication = (
        memory_raw > 0.0
        and communication_raw > 0.0
        and counts.get("memory_group_loop_iterations", 0)
        <= mixed_limits.get("maximum_memory_iterations", 0)
        and counts.get("communication_group_loop_iterations", 0)
        <= mixed_limits.get("maximum_communication_iterations", 0)
    )
    if mixed_memory_communication:
        correction = profile["mixed_memory_communication_correction"]
        communication_time = (
            (memory_raw + communication_raw) * correction["scale"]
            + correction["intercept_us"]
        )
        memory_time = 0.0
    powertrain_time = sum(count * powertrain_costs[name] for name, count in counts.items() if name in powertrain_costs)
    compound_time = sum(
        count * compound_costs[name]
        for name, count in counts.items() if name in compound_costs
    ) + sum(
        counts.get(f"{name}_invocations", 0) * intercept
        for name, intercept in compound_intercepts.items()
    )
    mixed_shape_time = sum(
        count * mixed_shape_costs[name]
        for name, count in counts.items() if name in mixed_shape_costs
    ) + sum(
        counts.get(f"{name}_invocations", 0) * intercept
        for name, intercept in mixed_shape_intercepts.items()
    )
    component_time = sum(
        count * component_costs[name]
        for name, count in counts.items() if name in component_costs
    )
    mixed_region_time = sum(
        count * mixed_region_costs[name]
        for name, count in counts.items() if name in mixed_region_costs
    ) + sum(
        counts.get(
            "mixed_region_shape_"
            + name.removeprefix("mixed_region_").removesuffix("_i32"),
            0,
        ) * intercept
        for name, intercept in mixed_region_intercepts.items()
    )
    callback_memory_correction = False
    callback_memory_out_of_range = False
    callback_memory_profile = profile.get("mixed_callback_memory_correction", {})
    callback_family = next(
        (
            family for family in ("callback", "callback_pack")
            if counts.get(f"mixed_region_{family}_i32", 0) > 0
        ),
        None,
    )
    callback_iterations = (
        counts.get(f"mixed_region_{callback_family}_i32", 0)
        if callback_family is not None else 0
    )
    if callback_iterations > 0 and memory_raw > 0.0:
        callback_memory_correction = (
            counts.get(f"mixed_region_shape_{callback_family}", 0) == 1
            and callback_memory_profile.get("memory_iterations_min", 0)
            <= counts.get("memory_group_loop_iterations", 0)
            <= callback_memory_profile.get("memory_iterations_max", -1)
            and callback_memory_profile.get("callback_iterations_min", 0)
            <= callback_iterations
            <= callback_memory_profile.get("callback_iterations_max", -1)
        )
        if callback_memory_correction:
            mixed_region_time = (
                (mixed_region_time + memory_raw)
                * callback_memory_profile["scale"]
                + callback_memory_profile["intercept_us"]
            )
            memory_time = 0.0
        else:
            callback_memory_out_of_range = True
    component_profile = profile.get("component_validation", {})
    component_units = max(
        (count for name, count in counts.items() if name in component_costs),
        default=0,
    )
    component_in_range = (
        component_units == 0
        or component_profile.get("work_units_min", 0)
        <= component_units
        <= component_profile.get("work_units_max", 0)
    )
    mixed_shape_profile = profile.get("mixed_shape_validation", {})
    mixed_shape_in_range = all(
        counts.get(name, 0) == 0
        or (
            counts.get(f"{name}_invocations", 0) == 1
            and mixed_shape_profile.get("work_units_min", 0)
            <= counts[name]
            <= mixed_shape_profile.get("work_units_max", 0)
        )
        for name in mixed_shape_costs
    )
    mixed_region_profile = profile.get("mixed_region_validation", {})
    validated_mixed_families = set(
        mixed_region_profile.get("validated_families", ())
    )
    mixed_region_in_range = all(
        family in validated_mixed_families
        and mixed_region_profile.get("iterations_min", 0)
        <= counts.get(f"mixed_region_{family}_i32", 0)
        <= mixed_region_profile.get("iterations_max", -1)
        for family in mixed_shapes
    )
    nominal = operations + loop_control + loop_setup + memory_time + fixed_time + floating_time + communication_time + powertrain_time + compound_time + mixed_shape_time + component_time + mixed_region_time
    margin = profile["engineering_margin_percent"] / 100.0
    powertrain_validated = bool(
        profile.get("powertrain_group_validation", {}).get("validated", False)
    )
    mixed_validated = bool(
        profile.get("mixed_memory_communication_correction", {}).get(
            "validated", False
        )
    )
    estimate_verified = (
        (powertrain_time == 0.0 or powertrain_validated)
        and (not mixed_memory_communication or mixed_validated)
        and (not mixed_shapes or mixed_region_in_range)
        and not callback_memory_out_of_range
        and (
            not callback_memory_correction
            or callback_memory_profile.get("validated", False)
        )
        and (
            mixed_shape_time == 0.0
            or (
                mixed_shape_profile.get("validated", False)
                and mixed_shape_in_range
            )
        )
        and (
            component_time == 0.0
            or (component_profile.get("validated", False) and component_in_range)
        )
    )
    note = (
        "Component costs passed isolated holdout but failed the independent compound holdout; this estimate is advisory only."
        if component_time != 0.0 and not component_profile.get("validated", False)
        else "Powertrain numeric coefficients are calibration-derived; independent holdout is pending."
        if powertrain_time != 0.0 and not powertrain_validated
        else (
            "Mixed memory and communication correction has an independent holdout pending."
            if mixed_memory_communication and not mixed_validated
            else (
                "Mixed shape is outside the validated 16-128 work-unit range."
                if mixed_shape_time != 0.0 and not mixed_shape_in_range
                else (
                    "Mixed execution region is outside its validated family or iteration range."
                    if mixed_shapes and not mixed_region_in_range
                    else "Validated for the S32K148 ARM GCC 11.4 O0 contextual subset."
                )
            )
        )
    )
    return ContextualIntegerEstimate(
        nominal, nominal * (1.0 + margin), estimate_verified,
        {"loop_setup": loop_setup, "loop_control": loop_control,
         "contextual_operations": operations, "memory_group": memory_time,
         "fixed_point_group": fixed_time, "floating_point_group": floating_time,
         "communication_group": communication_time,
         "powertrain_numeric_group": powertrain_time,
         "automotive_compound_group": compound_time,
         "mixed_shape_group": mixed_shape_time,
         "component_group": component_time,
         "mixed_region_group": mixed_region_time},
        (), note,
    )
