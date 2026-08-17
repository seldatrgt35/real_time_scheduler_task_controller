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
    administrative = {"loop_iterations", "loop_invocations", "memory_group_loop_iterations", "memory_group_loop_invocations", "fixed_group_loop_iterations", "fixed_group_loop_invocations", "floating_group_loop_iterations", "floating_group_loop_invocations", "communication_group_loop_iterations", "communication_group_loop_invocations", "powertrain_group_loop_iterations", "powertrain_group_loop_invocations", "compound_group_loop_iterations", "compound_group_loop_invocations", "mixed_shape_group_loop_iterations", "mixed_shape_group_loop_invocations", "atomic_fallback_region"}
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
    conditional_write_profile = profile.get(
        "atomic_conditional_memory_write_correction", {}
    )
    basic_gap_profile = profile.get("basic_gap_family_models", {})
    basic_memory_profile = profile.get("basic_memory_family_models", {})
    basic_control_profile = profile.get("basic_control_family_models", {})
    mixed_shape_intercepts = profile.get("mixed_shape_intercept_us", {})
    unsupported_set = {
        name for name, count in counts.items()
        if count > 0 and name not in administrative and name not in costs and name not in memory_costs and name not in fixed_costs and name not in floating_costs and name not in communication_costs and name not in powertrain_costs and name not in compound_costs and name not in mixed_shape_costs and name not in component_costs and name not in mixed_region_costs and not name.startswith("mixed_region_") and not name.startswith("atomic_region_") and not name.endswith("_invocations")
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
    conditional_write_time = 0.0
    conditional_iterations = counts.get("atomic_region_bounded_iterations", 0)
    conditional_writes = counts.get(
        "atomic_region_conditional_array_write", 0
    )
    if (
        counts.get("atomic_region_shape_conditional_memory", 0) == 1
        and conditional_write_profile.get("iterations_min", 0)
        <= conditional_iterations
        <= conditional_write_profile.get("iterations_max", -1)
        and conditional_iterations
        * conditional_write_profile.get("writes_per_iteration_min", 0)
        <= conditional_writes
        <= conditional_iterations
        * conditional_write_profile.get("writes_per_iteration_max", -1)
    ):
        conditional_write_time = (
            counts["atomic_region_shape_conditional_memory"]
            * conditional_write_profile.get("region_intercept_us", 0.0)
            + conditional_iterations
            * conditional_write_profile.get("iteration_us", 0.0)
            + conditional_writes
            * conditional_write_profile.get("write_iteration_us", 0.0)
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
    nominal = operations + loop_control + loop_setup + memory_time + fixed_time + floating_time + communication_time + powertrain_time + compound_time + mixed_shape_time + component_time + mixed_region_time + conditional_write_time
    basic_gap_family = None
    basic_gap_iterations = counts.get("loop_iterations", 0)
    basic_gap_payload = {
        name for name, count in counts.items()
        if count > 0
        and name not in administrative
        and not name.startswith("atomic_region_")
    }
    basic_gap_range_ok = (
        basic_gap_profile.get("iterations_min", 0)
        <= basic_gap_iterations
        <= basic_gap_profile.get("iterations_max", -1)
    )
    if basic_gap_range_ok and counts.get("loop_invocations", 0) == 1:
        if (
            counts.get("add_constant_u32", 0) == basic_gap_iterations
            and counts.get("add_local_u32", 0) == 2 * basic_gap_iterations
            and counts.get("multiply_local_u32", 0) == basic_gap_iterations
            and counts.get("subtract_local_u32", 0) == basic_gap_iterations
            and counts.get("atomic_fallback_region", 0) == 0
            and basic_gap_payload == {
                "add_constant_u32", "add_local_u32",
                "multiply_local_u32", "subtract_local_u32",
            }
        ):
            basic_gap_family = "arithmetic"
        elif (
            counts.get("atomic_region_shape_extended_masked_expression", 0)
            == 1
            and counts.get("divide_masked_index_u32", 0)
            == basic_gap_iterations
            and counts.get("basic_add_expression_u32", 0)
            == basic_gap_iterations
            and basic_gap_payload == {
                "divide_masked_index_u32", "basic_add_expression_u32",
            }
        ):
            basic_gap_family = "masked_divide"
        elif (
            counts.get("atomic_region_shape_extended_masked_expression", 0)
            == 1
            and counts.get("modulo_masked_index_u32", 0)
            == basic_gap_iterations
            and counts.get("basic_add_expression_u32", 0)
            == basic_gap_iterations
            and basic_gap_payload == {
                "modulo_masked_index_u32", "basic_add_expression_u32",
            }
        ):
            basic_gap_family = "masked_modulo"
    if basic_gap_family is not None:
        family_profile = basic_gap_profile[basic_gap_family]
        nominal = (
            family_profile["intercept_us"]
            + basic_gap_iterations * family_profile["iteration_us"]
        )
    basic_memory_family = None
    basic_memory_iterations = counts.get("memory_group_loop_iterations", 0)
    if (
        basic_gap_family is None
        and basic_memory_profile.get("iterations_min", 0)
        <= basic_memory_iterations
        <= basic_memory_profile.get("iterations_max", -1)
        and counts.get("loop_iterations", 0) == basic_memory_iterations
        and counts.get("loop_invocations", 0) == 1
        and counts.get("memory_group_loop_invocations", 0) == 1
    ):
        for family, feature in {
            "sequential": "sequential_memory_u32",
            "random": "random_indexed_memory_u32",
            "copy": "bulk_memory_copy_u32",
            "set": "bulk_memory_set_u32",
        }.items():
            allowed = {feature}
            if family in {"copy", "set"}:
                allowed.add("multiply_local_u32")
            if (
                counts.get(feature, 0) == basic_memory_iterations
                and basic_gap_payload
                and basic_gap_payload.issubset(allowed)
            ):
                basic_memory_family = family
                break
    if basic_memory_family is not None:
        family_profile = basic_memory_profile[basic_memory_family]
        nominal = (
            family_profile["intercept_us"]
            + basic_memory_iterations * family_profile["iteration_us"]
        )
    basic_control_family = None
    control_iterations = counts.get("loop_iterations", 0)
    if (
        basic_gap_family is None
        and basic_memory_family is None
        and basic_control_profile.get("iterations_min", 0)
        <= control_iterations
        <= basic_control_profile.get("iterations_max", -1)
        and counts.get("loop_invocations", 0) == 1
    ):
        if (
            counts.get("component_branch_bitwise_u32", 0) == control_iterations
            and basic_gap_payload == {"component_branch_bitwise_u32"}
        ):
            basic_control_family = "branch"
        elif (
            counts.get("mixed_region_callback_i32", 0) == control_iterations
            and counts.get("mixed_region_shape_callback", 0) == 1
            and counts.get("mixed_region_indirect_call", 0) == control_iterations
            and not counts.get("unsupported_mixed_execution_region", 0)
        ):
            basic_control_family = "callback"
        elif (
            counts.get("switch_case_4_u32", 0) == control_iterations
            and basic_gap_payload == {"switch_case_4_u32"}
        ):
            basic_control_family = "switch"
        elif (
            counts.get("checksum_processed_byte_u32", 0) == control_iterations
            and basic_gap_payload == {"checksum_processed_byte_u32"}
        ):
            basic_control_family = "checksum"
    if basic_control_family is not None:
        family_profile = basic_control_profile[basic_control_family]
        nominal = (
            family_profile["intercept_us"]
            + control_iterations * family_profile["iteration_us"]
        )
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
        (
            counts.get("atomic_fallback_region", 0) == 0
            or (
                basic_gap_family is not None
                and basic_gap_profile.get("validated", False)
            )
        )
        and
        (
            basic_control_family is None
            or basic_control_profile.get("validated", False)
        )
        and
        (
            basic_memory_family is None
            or basic_memory_profile.get("validated", False)
        )
        and
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
            or basic_control_family == "branch"
            or (component_profile.get("validated", False) and component_in_range)
        )
    )
    note = (
        "Validated by independent 32-iteration basic-control holdout."
        if basic_control_family is not None
        else "Validated by independent 32-iteration basic-memory holdout."
        if basic_memory_family is not None
        else "Validated by independent 32-iteration basic-family holdout."
        if basic_gap_family is not None
        else "Data-dependent conditional fallback reports an all-body structural estimate; typical-path occupancy is unknown."
        if counts.get("atomic_region_shape_conditional_memory", 0) > 0
        else
        "Atomic fallback preserves all recognized region work; independent holdout validation is pending."
        if counts.get("atomic_fallback_region", 0) > 0
        else
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
    breakdown = {"loop_setup": loop_setup, "loop_control": loop_control,
         "contextual_operations": operations, "memory_group": memory_time,
         "fixed_point_group": fixed_time, "floating_point_group": floating_time,
         "communication_group": communication_time,
         "powertrain_numeric_group": powertrain_time,
         "automotive_compound_group": compound_time,
         "mixed_shape_group": mixed_shape_time,
         "component_group": component_time,
         "mixed_region_group": mixed_region_time,
         "conditional_memory_write_correction": conditional_write_time}
    if (
        basic_gap_family is not None
        or basic_memory_family is not None
        or basic_control_family is not None
    ):
        breakdown = {
            name: 0.0 for name in breakdown
        }
        family_key = (
            "basic_control_family"
            if basic_control_family is not None
            else "basic_memory_family"
            if basic_memory_family is not None
            else "basic_gap_family"
        )
        breakdown[family_key] = nominal
    return ContextualIntegerEstimate(
        nominal, nominal * (1.0 + margin), estimate_verified,
        breakdown,
        (), note,
    )
