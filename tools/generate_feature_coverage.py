"""Generate the user-facing STAR feature coverage inventory from profiles."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "task_admission_framework" / "calibration" / "profiles"
OUTPUT = ROOT / "docs" / "S32K148_O0_feature_coverage.json"

CATEGORIES = {
    "integer_and_control": "cost_us_per_occurrence",
    "memory": "memory_group_cost_us_per_work_unit",
    "fixed_point": "fixed_group_cost_us_per_work_unit",
    "floating_point": "floating_group_cost_us_per_work_unit",
    "communication": "communication_group_cost_us_per_work_unit",
    "powertrain": "powertrain_group_cost_us_per_work_unit",
    "automotive_compound": "automotive_compound_cost_us_per_work_unit",
    "mixed_shape": "mixed_shape_cost_us_per_work_unit",
}

# These families are detected from Clang AST types/operators and do not depend
# on project-specific function or variable names.
NAME_INDEPENDENT = {
    "add_constant_u32", "add_local_u32", "add_index_u32", "add_memory_u32",
    "multiply_local_u32", "divide_small_u32", "divide_large_u32",
    "modulo_small_u32", "modulo_large_u32", "subtract_local_u32",
    "bitwise_and_u32", "bitwise_or_u32", "bitwise_xor_u32",
    "shift_left_u32", "shift_right_u32", "branch_evaluation_u32",
    "sequential_memory_u32", "random_indexed_memory_u32",
    "bulk_memory_copy_u32", "bulk_memory_set_u32",
    "float32_add_sub_u32", "float32_multiply_u32", "float32_divide_u32",
    "float64_add_sub_u32", "float64_multiply_u32", "float64_divide_u32",
    "int32_to_float32_u32", "direct_function_call_u32",
    "indirect_function_call_u32", "switch_case_4_u32",
}


def recognition_mode(feature: str) -> str:
    if feature in NAME_INDEPENDENT:
        return "name_independent_ast"
    if feature.startswith(("powertrain_", "automotive_", "mixed_")):
        return "restricted_structural_signature"
    return "restricted_structural_signature"


def main() -> None:
    contextual = json.loads(
        (PROFILE_DIR / "S32K148_contextual_integer_O0.json").read_text(
            encoding="utf-8"
        )
    )
    workload = json.loads(
        (PROFILE_DIR / "S32K148_workload_costs.json").read_text(encoding="utf-8")
    )
    categories = {}
    for category, profile_key in CATEGORIES.items():
        categories[category] = [
            {
                "feature": feature,
                "cost_us_per_unit": cost,
                "recognition": recognition_mode(feature),
            }
            for feature, cost in contextual.get(profile_key, {}).items()
        ]

    protocol_contracts = []
    protocol_names = {
        "bounded_byte_copy", "switch_dispatch", "direct_helper_call",
        "indirect_callback", "isotp_compound",
    }
    corrections = {
        item["workload_classes"][0]: item
        for item in workload["group_corrections"]
        if len(item.get("workload_classes", [])) == 1
    }
    for feature in sorted(protocol_names):
        correction = corrections[feature]
        protocol_contracts.append({
            "feature": feature,
            "slope_us_per_unit": workload["execution_time_us_per_work_unit"][feature],
            "intercept_us": correction["intercept_us"],
            "minimum_work_units": correction["minimum_work_units"],
            "maximum_work_units": correction["maximum_work_units"],
            "recognition": "explicit_contract_pending_structural_promotion",
        })

    document = {
        "target": "S32K148",
        "core_frequency_hz": 48_000_000,
        "compiler": "ARM GCC 11.4",
        "optimization": "O0",
        "engineering_margin_percent": 15.0,
        "contextual_feature_count": sum(map(len, categories.values())),
        "categories": categories,
        "protocol_runtime_contracts": protocol_contracts,
        "decision_policy": {
            "accepted": "all reachable execution work is covered by validated contracts",
            "unverified": "any unknown bound, unresolved callback body, external cost, or unmatched structure",
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({document['contextual_feature_count']} contextual features)")


if __name__ == "__main__":
    main()
