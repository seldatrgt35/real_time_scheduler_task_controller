"""Command-line entry point for the STAR analysis pipeline."""

from __future__ import annotations

from pathlib import Path

from task_admission_framework.descriptor.task_descriptor import TaskDescriptor
from task_admission_framework.hardware.hardware_profile import HardwareProfile
from task_admission_framework.pipeline.analysis_pipeline import AnalysisPipeline
from task_admission_framework.pipeline.exceptions import PipelineError
from task_admission_framework.report.complexity_report import ComplexityReport


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


def main() -> None:
    base_path = Path(__file__).parent
    source_path = base_path / "examples" / "sensor_task.c"
    descriptor_path = base_path / "examples" / "sensor_task.yaml"
    hardware_profile_path = base_path / "hardware" / "profiles" / "S32K148.json"

    pipeline = AnalysisPipeline()

    try:
        session = pipeline.analyze(
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


if __name__ == "__main__":
    main()
