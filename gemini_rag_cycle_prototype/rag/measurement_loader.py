from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from gemini_rag_cycle_prototype.schemas import Measurement, RagRecord, StructuralSummary


HARDWARE_PROFILE_ID = "S32K148_GCC11_4_O0_48MHz_source_only"


@dataclass(frozen=True)
class DatasetSpec:
    csv_name: str
    source_name: str | None
    split: str


DATASETS = (
    DatasetSpec("basic_control_calibration_board_results.csv", "basic_control_calibration.c", "calibration"),
    DatasetSpec("basic_gap_calibration_board_results.csv", "basic_gap_calibration.c", "calibration"),
    DatasetSpec("basic_memory_calibration_board_results.csv", "basic_memory_calibration.c", "calibration"),
    DatasetSpec("basic_feature_wcet_board_results.csv", "basic_feature_wcet_suite.c", "validation"),
    DatasetSpec("body_chassis_wcet_board_result.csv", "body_chassis_control_holdout.c", "holdout"),
    DatasetSpec("deterministic_automotive_wcet_board_result.csv", "deterministic_automotive_task.c", "holdout"),
    DatasetSpec("github_isotp_c_blind_board_results.csv", "github_isotp_c_blind_holdout.c", "blind_holdout"),
    DatasetSpec("github_uds_real_task_board_results.csv", "github_uds_ecu_blind_holdout.c", "blind_holdout"),
    DatasetSpec("iso14229_real_automotive_blind_board_results.csv", "iso14229_real_automotive_blind_suite.c", "blind_holdout"),
    DatasetSpec("mixed_callback_calibration_measurements.csv", "mixed_callback_calibration.c", "calibration"),
    DatasetSpec("mixed_integer_float_calibration_board_results.csv", "mixed_integer_float_calibration.c", "calibration"),
    DatasetSpec("mixed_interpolation_holdout_board_result.csv", "mixed_interpolation_blind_holdout.c", "holdout"),
    DatasetSpec("mixed_plausibility_calibration_measurements.csv", "mixed_plausibility_calibration.c", "calibration"),
    DatasetSpec("mixed_region_calibration_measurements.csv", "mixed_helper_saturation_calibration.c", "calibration"),
    DatasetSpec("powertrain_input_wcet_board_result.csv", "automotive_feature_reference.c", "holdout"),
    DatasetSpec("torque_coordination_wcet_board_result.csv", "automotive_feature_reference.c", "holdout"),
    DatasetSpec(
        "learning_feedback_board_results.csv",
        "experiments/gemini_source_only_holdout_v3/automotive_holdout_v3_tasks.c",
        "learning_feedback",
    ),
)


def strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"//[^\n]*", " ", source)


def normalize_source(source: str) -> str:
    return re.sub(r"\s+", "", strip_comments(source))


def source_fingerprint(source: str) -> str:
    return hashlib.sha256(normalize_source(source).encode("utf-8")).hexdigest()


def extract_function(source: str, function_name: str) -> str | None:
    match = re.search(
        rf"\b(?:void|[A-Za-z_]\w*(?:\s*\*)?)\s+{re.escape(function_name)}\s*\([^;]*?\)\s*\{{",
        source,
        flags=re.S,
    )
    if not match:
        return None
    start = match.start()
    brace = source.find("{", match.start())
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    return None


def function_names(source: str) -> list[str]:
    return list(dict.fromkeys(re.findall(
        r"\b(?:void|[A-Za-z_]\w*(?:\s*\*)?)\s+([A-Za-z_]\w*)\s*\([^;]*?\)\s*\{",
        source,
        flags=re.S,
    )))


def called_functions(function_source: str) -> list[str]:
    calls = re.findall(r"\b([A-Za-z_]\w*)\s*\(", strip_comments(function_source))
    keywords = {"for", "while", "if", "switch", "sizeof", "return"}
    return [name for name in calls[1:] if name not in keywords]


def extract_reachable_helpers(source: str, root_function: str) -> str:
    available = set(function_names(source))
    pending = list(called_functions(extract_function(source, root_function) or ""))
    visited = {root_function}
    helpers: list[str] = []
    while pending:
        name = pending.pop(0)
        if name in visited or name not in available:
            continue
        visited.add(name)
        body = extract_function(source, name)
        if body is None:
            continue
        helpers.append(body)
        pending.extend(called_functions(body))
    return "\n\n".join(helpers)


def extract_relevant_defines(source: str, relevant_source: str) -> str:
    definitions: dict[str, str] = {}
    for match in re.finditer(
        r"^[ \t]*#define[ \t]+([A-Za-z_]\w*)([^\r\n]*)",
        source,
        flags=re.M,
    ):
        remainder = match.group(2)
        # In C, a function-like macro has no whitespace between its name and
        # opening parenthesis. Object-like values commonly use spaced `(8U)`.
        if remainder.startswith("("):
            continue
        definitions[match.group(1)] = match.group(0).strip()
    selected: list[str] = []
    search_text = relevant_source
    changed = True
    while changed:
        changed = False
        for name, line in definitions.items():
            if line in selected:
                continue
            if re.search(rf"\b{re.escape(name)}\b", search_text):
                selected.append(line)
                search_text += "\n" + line
                changed = True
    return "\n".join(selected)


def extract_initialization_context(source: str) -> str:
    initializers = [
        name for name in function_names(source)
        if "initialize" in name.casefold() or name.casefold().endswith("_init")
    ]
    return "\n\n".join(
        body for name in initializers
        if (body := extract_function(source, name)) is not None
    )


def build_reference_context(
    source: str, task_name: str
) -> tuple[str, str]:
    task_source = extract_function(source, task_name) or ""
    callee_source = extract_reachable_helpers(source, task_name)
    initialization = extract_initialization_context(source)
    defines = extract_relevant_defines(
        source, "\n".join((task_source, callee_source, initialization))
    )
    sections = []
    if defines:
        sections.append("Relevant object-like defines:\n" + defines)
    if initialization:
        sections.append("Initialization context (outside timed interval):\n" + initialization)
    return callee_source, "\n\n".join(sections)


def structural_summary(source: str) -> StructuralSummary:
    clean = strip_comments(source)
    loops = list(re.finditer(r"\b(for|while|do)\b", clean))
    depth = 0
    max_depth = 0
    pending_loop = False
    for token in re.finditer(r"\b(?:for|while|do)\b|[{}]", clean):
        value = token.group(0)
        if value in {"for", "while", "do"}:
            pending_loop = True
        elif value == "{":
            if pending_loop:
                depth += 1
                max_depth = max(max_depth, depth)
                pending_loop = False
        elif value == "}" and depth:
            depth -= 1
    families = []
    for label, pattern in (
        ("add_sub", r"\+|-"), ("multiply", r"\*"),
        ("divide_modulo", r"/|%"), ("shift", r"<<|>>"),
        ("bitwise", r"\^|\||&"), ("compare", r"==|!=|<=|>=|<|>"),
    ):
        if re.search(pattern, clean):
            families.append(label)
    types = sorted(set(re.findall(r"\b(?:u?int(?:8|16|32|64)_t|float|double)\b", clean)))
    arrays = re.findall(r"\b[A-Za-z_]\w*\s*\[[^\]]+\]", clean)
    calls = re.findall(r"\b([A-Za-z_]\w*)\s*\(", clean)
    keywords = {"for", "while", "if", "switch", "sizeof", "return"}
    helper_calls = [call for call in calls[1:] if call not in keywords]
    branch_count = len(re.findall(r"\b(?:if|switch)\s*\(", clean))
    branch_count += len(re.findall(r"\b(?:case|default)\b\s*:", clean))
    comparison_count = len(re.findall(r"==|!=|<=|>=|(?<!<)<(?!<)|(?<!>)>(?!>)", clean))
    arithmetic_count = len(re.findall(r"(?<!\+)(?:\+|-)(?![+=>])|\*(?!=)", clean))
    bitwise_count = len(re.findall(r"<<|>>|(?<!\|)\|(?!\|)|(?<!&)&(?!&)|\^", clean))
    divide_modulo_count = len(re.findall(r"/|%", clean))
    assignment_count = len(re.findall(r"(?<![=!<>+\-*/%&|^])=(?!=)", clean))
    return StructuralSummary(
        loop_count=len(loops),
        nested_loop_depth=max_depth,
        known_total_iterations=None,
        has_branches=branch_count > 0,
        has_helper_calls=bool(helper_calls),
        branch_count=branch_count,
        helper_call_count=len(helper_calls),
        array_access_count=len(arrays),
        assignment_count=assignment_count,
        comparison_count=comparison_count,
        arithmetic_operator_count=arithmetic_count,
        bitwise_operator_count=bitwise_count,
        divide_modulo_count=divide_modulo_count,
        data_types=types,
        operation_families=families,
        memory_access_patterns=["array"] if arrays else [],
    )


def _float(row: dict[str, str], *names: str, scale: float = 1.0) -> float | None:
    for name in names:
        value = row.get(name, "").strip()
        if value:
            try:
                return float(value) / scale
            except ValueError:
                return None
    return None


def _int(row: dict[str, str], *names: str) -> int | None:
    value = _float(row, *names)
    return int(value) if value is not None else None


def _measurement(row: dict[str, str], csv_path: Path) -> Measurement | None:
    mean = _float(row, "board_mean_us", "mean_us")
    maximum = _float(row, "board_max_us", "maximum_us", "board_us")
    if mean is None:
        mean = _float(row, "mean_execution_us_x1000", scale=1000.0)
    if maximum is None:
        maximum = _float(row, "max_execution_us_x1000", scale=1000.0)
    board = _float(row, "board_us")
    mean = mean if mean is not None else board
    maximum = maximum if maximum is not None else board
    if mean is None and maximum is None:
        return None
    return Measurement(
        sample_count=_int(row, "completed_samples", "sample_count"),
        mean_us=mean,
        maximum_us=maximum,
        measurement_overhead_cycles=_int(row, "measurement_overhead_cycles"),
        source_path=str(csv_path),
    )


def _synthetic_name(spec: DatasetSpec, row: dict[str, str]) -> str | None:
    family = row.get("family", "").strip()
    iterations = row.get("iterations", "").strip()
    if spec.csv_name.startswith("basic_control"):
        return f"StarControl_{family.title()}{iterations}"
    if spec.csv_name.startswith("basic_gap"):
        names = {"arithmetic": "Arithmetic", "masked_divide": "MaskedDivide", "masked_modulo": "MaskedModulo"}
        return f"StarGap_{names.get(family, family.title())}{iterations}"
    if spec.csv_name.startswith("basic_memory"):
        return f"StarMemory_{family.title()}{iterations}"
    if spec.csv_name.startswith("mixed_integer_float"):
        return f"StarMixedIntegerFloat_{family.title()}{iterations}"
    if spec.csv_name.startswith("mixed_callback"):
        prefix = "MixedCallbackPack" if family == "callback_pack" else "MixedCallback"
        return f"{prefix}_{iterations}"
    if spec.csv_name.startswith("mixed_plausibility"):
        return f"MixedPlausibilityCalibration_{iterations}"
    if spec.csv_name.startswith("mixed_region"):
        return f"MixedCalibration_{family.title()}_{iterations}"
    if spec.csv_name.startswith("mixed_interpolation"):
        return f"MixedInterpolationHoldout_{iterations}"
    return None


class MeasurementLoader:
    def __init__(self, repository_root: Path):
        self.root = repository_root.resolve()
        self.tools = self.root / "tools"
        self.examples = self.root / "task_admission_framework" / "examples"
        self.skipped: list[dict[str, str]] = []

    def load(self) -> list[RagRecord]:
        records: list[RagRecord] = []
        seen: set[tuple[str, str]] = set()
        source_cache: dict[Path, str] = {}
        for spec in DATASETS:
            csv_path = self.tools / spec.csv_name
            default_source_path = None
            if spec.source_name:
                candidate = Path(spec.source_name)
                default_source_path = (
                    self.root / candidate
                    if len(candidate.parts) > 1
                    else self.examples / candidate
                )
            if not csv_path.exists() or default_source_path is None or not default_source_path.exists():
                self.skipped.append({"dataset": spec.csv_name, "reason": "missing dataset or source"})
                continue
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                for row_number, row in enumerate(csv.DictReader(handle), start=2):
                    row_source = row.get("source_file", "").strip()
                    if row_source:
                        row_candidate = Path(row_source)
                        source_path = (
                            self.root / row_candidate
                            if len(row_candidate.parts) > 1
                            else self.examples / row_candidate
                        )
                    else:
                        source_path = default_source_path
                    if not source_path.exists():
                        self.skipped.append({
                            "dataset": spec.csv_name,
                            "row": str(row_number),
                            "reason": f"row source not found: {row_source}",
                        })
                        continue
                    full_source = source_cache.setdefault(
                        source_path, source_path.read_text(encoding="utf-8")
                    )
                    measurement = _measurement(row, csv_path)
                    task_name = row.get("task", "").strip() or _synthetic_name(spec, row)
                    if measurement is None or not task_name:
                        self.skipped.append({"dataset": spec.csv_name, "row": str(row_number), "reason": "no measured time or task mapping"})
                        continue
                    function_source = extract_function(full_source, task_name)
                    if function_source is None:
                        self.skipped.append({"dataset": spec.csv_name, "row": str(row_number), "task": task_name, "reason": "function body not found (possibly macro-generated)"})
                        continue
                    key = (task_name, source_fingerprint(function_source))
                    if key in seen:
                        continue
                    seen.add(key)
                    normalized = normalize_source(function_source)
                    callee_source, source_context = build_reference_context(
                        full_source, task_name
                    )
                    records.append(RagRecord(
                        task_id=f"{spec.csv_name}:{row_number}:{task_name}",
                        task_name=task_name,
                        source_path=str(source_path.relative_to(self.root)),
                        source_code=function_source,
                        callee_source=callee_source,
                        source_context=source_context,
                        context_fingerprint=source_fingerprint(
                            callee_source + "\n" + source_context
                        ),
                        source_fingerprint=source_fingerprint(function_source),
                        normalized_source=normalized,
                        hardware_profile_id=HARDWARE_PROFILE_ID,
                        structural_summary=structural_summary(
                            function_source + "\n" + callee_source
                        ),
                        measurement=measurement,
                        dataset_split=row.get("dataset_role", "").strip() or row.get("fit_role", "").strip().lower() or spec.split,
                    ))
        return records

    def discovery_report(self, records: list[RagRecord]) -> dict:
        return {
            "record_count": len(records),
            "skipped_count": len(self.skipped),
            "sources": sorted({record.source_path for record in records}),
            "measurement_sources": sorted({record.measurement.source_path for record in records}),
            "units": ["us", "us_x1000 converted by division by 1000"],
            "dataset_splits": sorted({record.dataset_split for record in records}),
            "skipped": self.skipped,
        }
