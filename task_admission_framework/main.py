"""Command-line entry point for the STAR analysis pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from task_admission_framework.admission.admission_controller import AdmissionController
from task_admission_framework.admission.admission_decision import AdmissionDecision
from task_admission_framework.admission.hardware_adjustment_mode import (
    HardwareAdjustmentMode,
)
from task_admission_framework.calibration.complexity_time_loader import (
    ComplexityTimeLoader,
)
from task_admission_framework.descriptor.task_descriptor import TaskDescriptor
from task_admission_framework.hardware.hardware_profile import HardwareProfile
from task_admission_framework.pipeline.exceptions import PipelineError
from task_admission_framework.report.complexity_report import ComplexityReport
from task_admission_framework.rules.admission_rule import AdmissionRule
from task_admission_framework.rules.exceptions import RuleError
from task_admission_framework.rules.rule_database import RuleDatabase
from task_admission_framework.rules.rule_loader import RuleLoader


def print_complexity_report(report: ComplexityReport) -> None:
    """Print the explainable STAR complexity report."""

    print("-" * 72)
    print("STAR Complexity Report")
    print(f"Task: {report.task_name}")
    print(f"Complexity Score: {report.total_score}")
    print(f"Total Features: {report.total_features}")
    print("Category Breakdown:")
    print(f"  Computation: {report.computation_cost}")
    print(f"  Control Flow: {report.control_flow_cost}")
    print(f"  Memory: {report.memory_cost}")
    print(f"  RTOS: {report.rtos_cost}")
    print(f"  Peripheral: {report.peripheral_cost}")
    print(f"  Floating Point: {report.floating_point_cost}")
    print(f"  API: {report.api_cost}")
    print(f"  Other: {report.other_cost}")
    print("Detailed Breakdown:")
    for item in report.breakdown:
        print(
            f"  {item.name}: "
            f"{item.occurrences} x {item.base_cost} = {item.subtotal}"
        )
    print("-" * 72)


def print_task_descriptor(
    descriptor: TaskDescriptor,
    validation_status: str,
) -> None:
    """Print the source-independent task descriptor."""

    print("-" * 72)
    print("Task Descriptor")
    print(f"Task Name: {descriptor.task_name}")
    print(f"Entry Function: {descriptor.entry_function}")
    print(f"Period: {descriptor.period_ms} ms")
    print(f"Deadline: {descriptor.deadline_ms} ms")
    print(f"Priority: {descriptor.priority}")
    print(f"Stack Size: {descriptor.stack_size} bytes")
    print(f"Criticality: {descriptor.criticality.name}")
    print(f"Validation Status: {validation_status}")
    print("-" * 72)


def print_hardware_profile(
    profile: HardwareProfile,
    validation_status: str,
) -> None:
    """Print target hardware capabilities."""

    print("-" * 72)
    print("Hardware Profile")
    print(f"Name: {profile.name}")
    print(f"Vendor: {profile.vendor}")
    print(f"Family: {profile.family}")
    print(f"Architecture: {profile.architecture}")
    print(f"Core: {profile.core}")
    print(f"CPU Frequency: {profile.cpu_frequency_mhz} MHz")
    print(f"Flash: {profile.flash_kb} KB")
    print(f"RAM: {profile.ram_kb} KB")
    print(f"FPU: {'Yes' if profile.fpu else 'No'}")
    print(f"DMA: {'Yes' if profile.dma else 'No'}")
    print(f"MPU: {'Yes' if profile.mpu else 'No'}")
    print(f"Cache: {'Yes' if profile.cache else 'No'}")
    print(f"ADC Units: {profile.adc_units}")
    print(f"CAN Units: {profile.can_units}")
    print(f"UART Units: {profile.uart_units}")
    print(f"SPI Units: {profile.spi_units}")
    print(f"I2C Units: {profile.i2c_units}")
    print(f"Validation Status: {validation_status}")
    print("-" * 72)


def print_rules(rules: list[AdmissionRule]) -> None:
    """Print loaded admission threshold rules without evaluating a task."""

    print("-" * 120)
    print("STAR Rule Database")
    print(
        f"{'Hardware':<12}"
        f"{'Period':<10}"
        f"{'Criticality':<18}"
        f"{'Max Complexity':<18}"
        f"{'Validated':<12}"
        f"{'Description':<52}"
        "Source"
    )
    for rule in rules:
        criticality = rule.criticality if rule.criticality is not None else "ANY"
        print(
            f"{rule.hardware:<12}"
            f"{rule.period_ms:<10}"
            f"{criticality:<18}"
            f"{rule.max_complexity:<18.1f}"
            f"{str(rule.validated):<12}"
            f"{rule.description:<52}"
            f"{rule.source}"
        )
    print("-" * 120)


def print_admission_result(session, decision: AdmissionDecision) -> None:
    """Print CLI admission output."""

    descriptor = session.task_descriptor
    hardware = session.hardware_profile
    report = session.complexity_report

    print("-" * 72)
    print("STAR Admission Result")
    print(f"Task: {descriptor.task_name}")
    print(f"Entry Function: {descriptor.entry_function}")
    print(f"Hardware: {hardware.name}")
    print(f"Period: {descriptor.period_ms} ms")
    print(f"Deadline: {descriptor.deadline_ms} ms")
    print(f"Criticality: {descriptor.criticality.name}")
    print()
    print(
        "Hardware-Adjusted Score: "
        f"{decision.hardware_adjusted_score:.1f} / "
        f"{decision.hardware_adjusted_max_complexity:.2f}"
    )
    print(f"Raw Complexity Score: {decision.complexity_score:.1f}")
    print(f"Complexity Load: {decision.star_load_indicator:.0%}")
    print()
    print(f"Static Admission: {decision.status.name}")
    print(f"Reason: {decision.reason}")
    print()
    print("Hardware Details:")
    print(f"  S32K148 Reference Limit: {decision.max_complexity:.2f}")
    print(f"  CPU Score Factor: {decision.hardware_scaling_factor:.2f}")
    print(f"  Reference Limit Used: {decision.hardware_adjusted_max_complexity:.2f}")
    print(f"  Hardware Model: {decision.hardware_adjustment_mode.name}")
    if decision.warning is not None:
        print(f"  Note: {decision.warning}")
    print("  Category Adjustment:")
    for item in decision.hardware_adjustment_breakdown:
        print(
            f"    {item.category}: "
            f"{item.raw_score:.2f} x {item.factor:.2f} = {item.adjusted_score:.2f}"
        )
    print()
    print(
        "Note: This is a static complexity-based result, not a WCET or "
        "scheduler guarantee."
    )
    print()
    print("Complexity Breakdown:")
    for item in report.breakdown:
        print(
            f"  {item.name}: "
            f"{item.occurrences} x {item.base_cost} = {item.subtotal}"
        )
    print("-" * 72)


def build_parser() -> argparse.ArgumentParser:
    """Build the STAR command-line parser."""

    parser = argparse.ArgumentParser(
        prog="python -m task_admission_framework.main",
        description="STAR static task analysis command line interface.",
    )
    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze a C task source file and evaluate admission.",
    )
    analyze_parser.add_argument("--source", required=True, help="Path to the C file.")
    analyze_parser.add_argument(
        "--descriptor",
        required=True,
        help="Path to the task descriptor YAML file.",
    )
    analyze_parser.add_argument(
        "--hardware",
        required=True,
        help="Path to the hardware profile JSON file.",
    )
    analyze_parser.add_argument(
        "--rules",
        required=True,
        help="Path to the rule profile JSON file.",
    )
    add_hardware_adjustment_argument(analyze_parser)
    subparsers.add_parser("gui", help="Open the desktop file picker interface.")

    taskset_parser = subparsers.add_parser(
        "analyze-taskset",
        help="Analyze a group of tasks and compute total STAR load.",
    )
    taskset_parser.add_argument(
        "--config",
        required=True,
        help="Path to taskset_config.json.",
    )
    add_hardware_adjustment_argument(taskset_parser)

    complexity_parser = subparsers.add_parser(
        "analyze-complexity",
        help="Analyze only raw source complexity, without hardware or admission.",
    )
    complexity_parser.add_argument(
        "--source",
        required=True,
        help="Path to the C/C++ source file.",
    )
    complexity_parser.add_argument(
        "--entry",
        required=True,
        help="Entry function name to analyze.",
    )

    complexity_taskset_parser = subparsers.add_parser(
        "analyze-complexity-taskset",
        help="Analyze raw complexity for each task in a task-set config.",
    )
    complexity_taskset_parser.add_argument(
        "--config",
        required=True,
        help="Path to taskset config JSON. Hardware and rule fields are ignored.",
    )

    return parser


def add_hardware_adjustment_argument(parser: argparse.ArgumentParser) -> None:
    """Add common hardware adjustment mode CLI option."""

    parser.add_argument(
        "--hardware-adjustment",
        choices=("calibrated", "none", "prototype-frequency-scaling"),
        default="calibrated",
        help=(
            "Hardware threshold adjustment mode. Default 'calibrated' uses "
            "S32K148 reference thresholds with hardware metadata scaling."
        ),
    )


def parse_hardware_adjustment_mode(raw_mode: str) -> HardwareAdjustmentMode:
    """Convert CLI hardware adjustment mode text to enum."""

    normalized = raw_mode.strip().lower()
    if normalized == "none":
        return HardwareAdjustmentMode.NONE
    if normalized == "prototype-frequency-scaling":
        return HardwareAdjustmentMode.PROTOTYPE_FREQUENCY_SCALING
    if normalized == "calibrated":
        return HardwareAdjustmentMode.CALIBRATED

    raise ValueError(f"Unknown hardware adjustment mode: {raw_mode}")


def load_rule_database(rule_path: Path) -> RuleDatabase:
    """Load rules and create the in-memory rule database."""

    rules = RuleLoader().load(rule_path)
    return RuleDatabase(rules)


def run_demo() -> None:
    """Run the built-in STAR demo using example files."""

    base_path = Path(__file__).parent
    source_path = base_path / "examples" / "sensor_task.c"
    descriptor_path = base_path / "examples" / "sensor_task.yaml"
    hardware_profile_path = base_path / "hardware" / "profiles" / "S32K148.json"
    rule_profile_path = base_path / "rules" / "profiles" / "S32K148_rules.json"

    try:
        from task_admission_framework.pipeline.analysis_pipeline import AnalysisPipeline

        session = AnalysisPipeline().analyze(
            source_file=source_path,
            descriptor_file=descriptor_path,
            hardware_profile_file=hardware_profile_path,
        )
    except PipelineError as exc:
        print(f"STAR analysis failed: {exc}")
        return

    print_complexity_report(session.complexity_report)
    print_task_descriptor(session.task_descriptor, "Valid")
    print_hardware_profile(session.hardware_profile, "Valid")

    try:
        rule_database = load_rule_database(rule_profile_path)
        rule_database.find_rule("S32K148", 10, "HIGH")
    except RuleError as exc:
        print(f"STAR rule database failed: {exc}")
        return

    print_rules(rule_database.list_rules())


def run_analyze(args: argparse.Namespace) -> None:
    """Run CLI analysis for user-provided input paths."""

    source_path = Path(args.source)
    descriptor_path = Path(args.descriptor)
    hardware_path = Path(args.hardware)
    rule_path = Path(args.rules)

    missing_paths = [
        path
        for path in (source_path, descriptor_path, hardware_path, rule_path)
        if not path.exists()
    ]
    if missing_paths:
        for path in missing_paths:
            print(f"STAR CLI error: file not found: {path}")
        return

    try:
        from task_admission_framework.pipeline.analysis_pipeline import AnalysisPipeline

        session = AnalysisPipeline().analyze(
            source_file=source_path,
            descriptor_file=descriptor_path,
            hardware_profile_file=hardware_path,
        )
    except PipelineError as exc:
        print(f"STAR analysis failed: {exc}")
        return

    try:
        rule_database = load_rule_database(rule_path)
        decision = AdmissionController(
            hardware_adjustment_mode=parse_hardware_adjustment_mode(
                args.hardware_adjustment,
            ),
        ).evaluate(session, rule_database)
    except RuleError as exc:
        print(f"STAR rule database failed: {exc}")
        return

    print_admission_result(session, decision)


def run_analyze_taskset(args: argparse.Namespace) -> None:
    """Run static complexity-based task-set analysis from JSON config."""

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"STAR task-set error: file not found: {config_path}")
        return

    try:
        from task_admission_framework.taskset.exceptions import TaskSetError
        from task_admission_framework.taskset.taskset_analyzer import TaskSetAnalyzer

        entries = load_taskset_entries(config_path)
        calibration_profile = load_taskset_calibration_profile(config_path)
        simulation_window_ms = load_taskset_simulation_window_ms(config_path)
        result = TaskSetAnalyzer(
            admission_controller=AdmissionController(
                hardware_adjustment_mode=parse_hardware_adjustment_mode(
                    args.hardware_adjustment,
                ),
            ),
            calibration_profile=calibration_profile,
            simulation_window_ms=simulation_window_ms,
        ).analyze(entries)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"STAR task-set config failed: {exc}")
        return
    except (PipelineError, RuleError, TaskSetError) as exc:
        print(f"STAR task-set analysis failed: {exc}")
        return

    print_taskset_result(result)


def run_analyze_complexity(args: argparse.Namespace) -> None:
    """Run source-only complexity analysis without hardware or admission."""

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"STAR complexity error: file not found: {source_path}")
        return

    try:
        report = analyze_source_complexity(source_path, str(args.entry))
    except PipelineError as exc:
        print(f"STAR complexity analysis failed: {exc}")
        return

    print_complexity_only_report(report)


def run_analyze_complexity_taskset(args: argparse.Namespace) -> None:
    """Run source-only complexity analysis for a task-set config."""

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"STAR complexity task-set error: file not found: {config_path}")
        return

    try:
        items = load_complexity_taskset_items(config_path)
        reports = [
            (
                item,
                analyze_source_complexity(
                    Path(item["source_file"]),
                    str(item["entry_function"]),
                ),
            )
            for item in items
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"STAR complexity task-set config failed: {exc}")
        return
    except PipelineError as exc:
        print(f"STAR complexity task-set analysis failed: {exc}")
        return

    print_complexity_taskset_result(reports)


def analyze_source_complexity(source_path: Path, entry_function: str) -> ComplexityReport:
    """Analyze raw STAR complexity without descriptor, hardware, rules, or admission."""

    from task_admission_framework.analyzer.analyzer import StaticAnalyzer
    from task_admission_framework.complexity.complexity_calculator import (
        ComplexityCalculator,
    )
    from task_admission_framework.cost.cost_database import CostDatabase
    from task_admission_framework.feature.feature_extractor import FeatureExtractor
    from task_admission_framework.report.report_generator import ReportGenerator

    try:
        profiles = StaticAnalyzer().analyze_file(source_path)
    except Exception as exc:
        raise PipelineError(f"Source analysis failed: {exc}") from exc

    task_profile = next(
        (profile for profile in profiles if profile.task_name == entry_function),
        None,
    )
    if task_profile is None:
        available = ", ".join(sorted(profile.task_name for profile in profiles))
        raise PipelineError(
            f"No function named '{entry_function}' found. Available: {available}"
        )

    feature_vector = FeatureExtractor().extract(task_profile)
    complexity_result = ComplexityCalculator().calculate(
        feature_vector,
        CostDatabase(),
    )
    return ReportGenerator().generate(
        complexity_result,
        feature_vector,
        task_name=task_profile.task_name,
    )


def load_taskset_entries(config_path: Path):
    """Load TaskSetEntry objects from a JSON task-set config."""

    from task_admission_framework.taskset.taskset_entry import TaskSetEntry

    data = _load_taskset_config_json(config_path)

    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("taskset config must contain a non-empty 'tasks' list.")

    return [
        TaskSetEntry(
            name=str(item["name"]),
            source_file=resolve_taskset_path(config_path, item["source_file"]),
            entry_function=str(item["entry_function"]),
            period_ms=int(item["period_ms"]),
            deadline_ms=int(item["deadline_ms"]),
            priority=int(item["priority"]),
            criticality=str(item["criticality"]).upper(),
            hardware_profile_file=resolve_taskset_path(
                config_path,
                item["hardware_profile_file"],
            ),
            rules_file=resolve_taskset_path(config_path, item["rules_file"]),
        )
        for item in tasks
    ]


def load_complexity_taskset_items(config_path: Path) -> list[dict[str, Any]]:
    """Load source/function/period metadata for complexity-only task-set analysis."""

    data = _load_taskset_config_json(config_path)
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("taskset config must contain a non-empty 'tasks' list.")

    items: list[dict[str, Any]] = []
    for task in tasks:
        items.append(
            {
                "name": str(task["name"]),
                "source_file": resolve_taskset_path(config_path, task["source_file"]),
                "entry_function": str(task["entry_function"]),
                "period_ms": int(task.get("period_ms", 0)),
                "deadline_ms": int(task.get("deadline_ms", task.get("period_ms", 0))),
                "priority": int(task.get("priority", 0)),
            }
        )
    return items


def load_taskset_calibration_profile(config_path: Path):
    """Load optional task-independent complexity-time calibration profile."""

    data = _load_taskset_config_json(config_path)
    raw_path = data.get("calibration_profile_file")
    if raw_path is None:
        return None
    return ComplexityTimeLoader().load(resolve_taskset_path(config_path, raw_path))


def load_taskset_simulation_window_ms(config_path: Path) -> int:
    """Load optional scheduler simulation window from task-set config."""

    data = _load_taskset_config_json(config_path)
    return int(data.get("simulation_window_ms", 100))


def _load_taskset_config_json(config_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON config: {config_path}") from exc
    if not isinstance(data, dict):
        raise ValueError("taskset config must contain a JSON object.")
    return data


def resolve_taskset_path(config_path: Path, raw_path: Any) -> Path:
    """Resolve config paths from CWD first, then relative to config file."""

    path = Path(str(raw_path))
    if path.is_absolute() or path.exists():
        return path

    relative_to_config = config_path.parent / path
    if relative_to_config.exists():
        return relative_to_config

    return path


def print_taskset_result(result) -> None:
    """Print a table for task-set STAR load analysis."""

    print("-" * 128)
    print("Task Set Result")
    print(
        f"{'Task':<24}"
        f"{'Function':<34}"
        f"{'Period':<10}"
        f"{'Deadline':<10}"
        f"{'Priority':<10}"
        f"{'Criticality':<16}"
        f"{'Raw':<10}"
        f"{'Adj':<10}"
        f"{'Adj Max':<12}"
        f"{'STAR Load':<12}"
        f"{'Static':<10}"
        "Scheduler"
    )
    for task in result.task_results:
        print(
            f"{task.task_name:<24}"
            f"{task.entry_function:<34}"
            f"{task.period_ms:<10}"
            f"{task.deadline_ms:<10}"
            f"{task.priority:<10}"
            f"{task.criticality:<16}"
            f"{task.complexity_score:<10.2f}"
            f"{task.hardware_adjusted_score:<10.2f}"
            f"{task.rule_max_complexity:<12.2f}"
            f"{task.task_load:<12.2f}"
            f"{task.admission_status:<10}"
            f"{task.scheduler_status}"
        )
        if task.estimated_execution_time_us is not None:
            print(
                f"  Estimated Execution: "
                f"{task.estimated_execution_time_us / 1000.0:.3f} ms"
            )
    print("-" * 128)
    print(f"STAR Complexity Load Indicator: {result.total_star_load:.2f}")
    print(f"System Status: {result.system_status}")
    print(f"System Reason: {result.system_reason}")
    print(f"Scheduler Feasibility: {result.scheduler_status}")
    print(f"Scheduler Reason: {result.scheduler_reason}")
    if result.scheduler_deadline_misses:
        print("Scheduler Deadline Misses:")
        for line in result.scheduler_deadline_misses:
            print(f"  {line}")
    if result.scheduler_preemptions:
        print("Scheduler Preemptions:")
        for line in result.scheduler_preemptions:
            print(f"  {line}")
    if result.scheduler_timeline:
        print("Scheduler Timeline:")
        for line in result.scheduler_timeline:
            print(f"  {line}")
    print(
        "This is a static complexity-based risk indicator, not a WCET-based "
        "scheduler guarantee."
    )


def print_complexity_only_report(report: ComplexityReport) -> None:
    """Print raw complexity output without hardware/admission wording."""

    print("-" * 72)
    print("STAR Raw Complexity Result")
    print(f"Task: {report.task_name}")
    print(f"Raw Complexity Score: {report.total_score}")
    print(f"Total Features: {report.total_features}")
    print()
    print("Category Breakdown:")
    print(f"  Computation: {report.computation_cost}")
    print(f"  Control Flow: {report.control_flow_cost}")
    print(f"  Memory: {report.memory_cost}")
    print(f"  RTOS: {report.rtos_cost}")
    print(f"  Peripheral: {report.peripheral_cost}")
    print(f"  Floating Point: {report.floating_point_cost}")
    print(f"  API: {report.api_cost}")
    print(f"  Other: {report.other_cost}")
    print()
    print("Detailed Breakdown:")
    for item in report.breakdown:
        print(
            f"  {item.name}: "
            f"{item.occurrences} x {item.base_cost} = {item.subtotal}"
        )
    print("-" * 72)


def print_complexity_taskset_result(
    reports: list[tuple[dict[str, Any], ComplexityReport]],
) -> None:
    """Print raw complexity for a group of tasks."""

    print("-" * 112)
    print("STAR Raw Complexity Task Set")
    print(
        f"{'Task':<24}"
        f"{'Function':<34}"
        f"{'Period':<10}"
        f"{'Deadline':<10}"
        f"{'Priority':<10}"
        f"{'Raw Score':<12}"
        "Features"
    )
    for item, report in reports:
        print(
            f"{item['name']:<24}"
            f"{item['entry_function']:<34}"
            f"{item['period_ms']:<10}"
            f"{item['deadline_ms']:<10}"
            f"{item['priority']:<10}"
            f"{report.total_score:<12}"
            f"{report.total_features}"
        )
    print("-" * 112)
    print("Per-task breakdown:")
    for item, report in reports:
        print(f"{item['name']} ({item['entry_function']}):")
        for breakdown in report.breakdown:
            print(
                f"  {breakdown.name}: "
                f"{breakdown.occurrences} x {breakdown.base_cost} = "
                f"{breakdown.subtotal}"
            )
    print("-" * 112)
    print("Hardware, rules, admission, and scheduler analysis are not used here.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        run_analyze(args)
        return

    if args.command == "gui":
        from task_admission_framework.gui import run_gui

        run_gui()
        return

    if args.command == "analyze-taskset":
        run_analyze_taskset(args)
        return

    if args.command == "analyze-complexity":
        run_analyze_complexity(args)
        return

    if args.command == "analyze-complexity-taskset":
        run_analyze_complexity_taskset(args)
        return

    run_demo()


if __name__ == "__main__":
    main()
