"""Rule-based admission controller for STAR."""

from __future__ import annotations

from task_admission_framework.admission.admission_decision import (
    AdmissionDecision,
    AdmissionStatus,
    HardwareAdjustmentBreakdown,
)
from task_admission_framework.admission.exceptions import CalibrationProfileMissingError
from task_admission_framework.admission.hardware_adjustment_mode import (
    HardwareAdjustmentMode,
)
from task_admission_framework.pipeline.analysis_session import AnalysisSession
from task_admission_framework.rules.rule_database import RuleDatabase
from task_admission_framework.scheduling.scheduler_status import SchedulerStatus


class AdmissionController:
    """Compares an analysis session with a matching rule threshold."""

    _REFERENCE_CPU_FREQUENCY_MHZ = 112
    _PROTOTYPE_WARNING = (
        "Warning: CPU-frequency scaling is an unvalidated prototype heuristic "
        "and is not a schedulability guarantee."
    )

    def __init__(
        self,
        hardware_adjustment_mode: HardwareAdjustmentMode = HardwareAdjustmentMode.CALIBRATED,
    ) -> None:
        self._hardware_adjustment_mode = hardware_adjustment_mode

    def evaluate(
        self,
        session: AnalysisSession,
        rule_database: RuleDatabase,
    ) -> AdmissionDecision:
        """Evaluate one analysis session and return ACCEPT or REJECT."""

        hardware = session.hardware_profile.name
        period_ms = session.task_descriptor.period_ms
        criticality = session.task_descriptor.criticality.name
        complexity_score = float(session.complexity_result.total_score)

        rule = rule_database.find_rule(
            hardware=hardware,
            period_ms=period_ms,
            criticality=criticality,
        )

        hardware_scaling_factor = self._calculate_hardware_scaling_factor(
            session,
            rule.validated,
        )
        hardware_adjusted_score, hardware_adjustment_breakdown = (
            self._calculate_hardware_adjusted_score(session, hardware_scaling_factor)
        )
        hardware_adjusted_max_complexity = self._calculate_adjusted_max_complexity(
            rule.max_complexity,
            hardware_scaling_factor,
        )
        warning = self._build_warning(session, rule.validated)
        availability_errors = self._check_peripheral_availability(session)
        admission_score = self._select_admission_score(
            complexity_score,
            hardware_adjusted_score,
        )
        star_load_indicator = admission_score / hardware_adjusted_max_complexity

        if availability_errors:
            status = AdmissionStatus.REJECT
            reason = " ".join(availability_errors)
        elif admission_score <= hardware_adjusted_max_complexity:
            status = AdmissionStatus.ACCEPT
            reason = (
                f"Adjusted score {admission_score:.1f} is within the reference limit "
                f"{hardware_adjusted_max_complexity:.2f}."
            )
        else:
            status = AdmissionStatus.REJECT
            reason = (
                f"Adjusted score {admission_score:.1f} exceeds the reference limit "
                f"{hardware_adjusted_max_complexity:.2f}."
            )

        return AdmissionDecision(
            task_name=session.task_descriptor.task_name,
            hardware=hardware,
            period_ms=period_ms,
            criticality=criticality,
            complexity_score=complexity_score,
            hardware_adjusted_score=admission_score,
            max_complexity=rule.max_complexity,
            hardware_adjusted_max_complexity=hardware_adjusted_max_complexity,
            hardware_scaling_factor=hardware_scaling_factor,
            hardware_adjustment_breakdown=hardware_adjustment_breakdown,
            hardware_adjustment_mode=self._hardware_adjustment_mode,
            warning=warning,
            star_load_indicator=star_load_indicator,
            scheduler_status=SchedulerStatus.UNVERIFIED.name,
            scheduler_reason=(
                "No validated execution-budget calibration exists. "
                "Static admission uses reference complexity thresholds only."
            ),
            status=status,
            reason=reason,
            rule_source=rule.source,
            rule_validated=rule.validated,
        )

    @staticmethod
    def calculate_cpu_frequency_scaling_factor(cpu_frequency_mhz: int) -> float:
        """Return the CPU-frequency ratio relative to the S32K148 reference."""

        return cpu_frequency_mhz / AdmissionController._REFERENCE_CPU_FREQUENCY_MHZ

    calculate_prototype_frequency_scaling_factor = calculate_cpu_frequency_scaling_factor

    @staticmethod
    def calculate_cpu_score_factor(cpu_frequency_mhz: int) -> float:
        """Return the S32K148-equivalent score factor for CPU-bound categories."""

        return AdmissionController._REFERENCE_CPU_FREQUENCY_MHZ / cpu_frequency_mhz

    def _calculate_hardware_scaling_factor(
        self,
        session: AnalysisSession,
        reference_rule_validated: bool,
    ) -> float:
        del reference_rule_validated

        if self._hardware_adjustment_mode is HardwareAdjustmentMode.NONE:
            return 1.0

        if (
            self._hardware_adjustment_mode
            is HardwareAdjustmentMode.PROTOTYPE_FREQUENCY_SCALING
        ):
            # Raw complexity remains hardware independent. This factor only
            # adjusts the static rule threshold for prototype demonstrations.
            return self.calculate_cpu_frequency_scaling_factor(
                session.hardware_profile.cpu_frequency_mhz,
            )

        if self._hardware_adjustment_mode is HardwareAdjustmentMode.CALIBRATED:
            # CALIBRATED here means S32K148 reference thresholds are treated as
            # the reference data set. Scores for CPU-bound categories are
            # converted into S32K148-equivalent score units.
            return self.calculate_cpu_score_factor(
                session.hardware_profile.cpu_frequency_mhz,
            )

        raise CalibrationProfileMissingError(
            f"Unsupported hardware adjustment mode: {self._hardware_adjustment_mode}."
        )

    def _calculate_adjusted_max_complexity(
        self,
        rule_max_complexity: float,
        hardware_scaling_factor: float,
    ) -> float:
        if self._hardware_adjustment_mode is HardwareAdjustmentMode.NONE:
            return rule_max_complexity

        if (
            self._hardware_adjustment_mode
            is HardwareAdjustmentMode.PROTOTYPE_FREQUENCY_SCALING
        ):
            return rule_max_complexity * hardware_scaling_factor

        if self._hardware_adjustment_mode is HardwareAdjustmentMode.CALIBRATED:
            return rule_max_complexity

        raise CalibrationProfileMissingError("Unsupported hardware adjustment mode.")

    def _calculate_hardware_adjusted_score(
        self,
        session: AnalysisSession,
        cpu_score_factor: float,
    ) -> tuple[float, list[HardwareAdjustmentBreakdown]]:
        if self._hardware_adjustment_mode is not HardwareAdjustmentMode.CALIBRATED:
            raw_score = float(session.complexity_result.total_score)
            return (
                raw_score,
                [
                    HardwareAdjustmentBreakdown(
                        category="Raw Complexity",
                        raw_score=raw_score,
                        factor=1.0,
                        adjusted_score=raw_score,
                    )
                ],
            )

        category_scores = self._category_scores(session)
        factors = {
            "Computation": cpu_score_factor,
            "Control Flow": cpu_score_factor,
            "Floating Point": self._floating_point_factor(
                category_scores["Floating Point"],
                session.hardware_profile.fpu,
                cpu_score_factor,
            ),
            "Memory": 1.0,
            "RTOS": 1.0,
            "Peripheral": 1.0,
            "Other": 1.0,
        }
        breakdown = [
            HardwareAdjustmentBreakdown(
                category=category,
                raw_score=score,
                factor=factors[category],
                adjusted_score=score * factors[category],
            )
            for category, score in category_scores.items()
        ]
        return sum(item.adjusted_score for item in breakdown), breakdown

    @staticmethod
    def _floating_point_factor(
        floating_point_score: float,
        hardware_has_fpu: bool,
        cpu_score_factor: float,
    ) -> float:
        if floating_point_score <= 0:
            return 1.0
        if hardware_has_fpu:
            return cpu_score_factor
        return max(cpu_score_factor, 1.0)

    @staticmethod
    def _category_scores(session: AnalysisSession) -> dict[str, float]:
        report = getattr(session, "complexity_report", None)
        if report is None:
            return {
                "Computation": float(session.complexity_result.total_score),
                "Control Flow": 0.0,
                "Floating Point": 0.0,
                "Memory": 0.0,
                "RTOS": 0.0,
                "Peripheral": 0.0,
                "Other": 0.0,
            }

        return {
            "Computation": float(report.computation_cost),
            "Control Flow": float(report.control_flow_cost),
            "Floating Point": float(report.floating_point_cost),
            "Memory": float(report.memory_cost),
            "RTOS": float(report.rtos_cost),
            "Peripheral": float(report.peripheral_cost),
            "Other": float(report.other_cost),
        }

    def _select_admission_score(
        self,
        complexity_score: float,
        hardware_adjusted_score: float,
    ) -> float:
        if self._hardware_adjustment_mode is HardwareAdjustmentMode.CALIBRATED:
            return hardware_adjusted_score
        return complexity_score

    @staticmethod
    def _check_peripheral_availability(session: AnalysisSession) -> list[str]:
        api_names = set(session.feature_vector.api_call_counts)
        hardware = session.hardware_profile
        requirements = (
            ("ADC_", hardware.adc_units, "ADC"),
            ("CAN_", hardware.can_units, "CAN"),
            ("SPI_", hardware.spi_units, "SPI"),
            ("UART_", hardware.uart_units, "UART"),
            ("I2C_", hardware.i2c_units, "I2C"),
        )
        errors: list[str] = []
        for prefix, unit_count, label in requirements:
            if unit_count <= 0 and any(name.startswith(prefix) for name in api_names):
                errors.append(
                    f"Task uses {label} API but selected hardware has no {label} unit."
                )
        return errors

    def _build_warning(
        self,
        session: AnalysisSession,
        reference_rule_validated: bool,
    ) -> str | None:
        warnings: list[str] = []
        if (
            self._hardware_adjustment_mode
            is HardwareAdjustmentMode.PROTOTYPE_FREQUENCY_SCALING
        ):
            warnings.append(self._PROTOTYPE_WARNING)

        if self._hardware_adjustment_mode is HardwareAdjustmentMode.CALIBRATED:
            if not reference_rule_validated:
                warnings.append(
                    "Warning: reference rule thresholds are not validated yet; "
                    "hardware-adjusted admission remains a reference-scaling "
                    "estimate."
                )

            if (
                session.feature_vector.floating_point_operations > 0
                and not session.hardware_profile.fpu
            ):
                warnings.append(
                    "Warning: task uses floating-point operations but selected "
                    "hardware has no FPU; threshold scaling may be optimistic."
                )

            if session.hardware_profile.cache:
                warnings.append(
                    "Warning: selected hardware has cache; cache effects are "
                    "configuration-dependent and are not treated as a timing "
                    "guarantee."
                )

            if session.hardware_profile.flash_wait_states is not None:
                warnings.append(
                    "Note: flash_wait_states is recorded as metadata but does "
                    "not currently change the raw complexity score."
                )

        if not warnings:
            return None
        return " ".join(warnings)
