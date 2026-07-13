"""Rule-based admission controller for STAR."""

from __future__ import annotations

from task_admission_framework.admission.admission_decision import (
    AdmissionDecision,
    AdmissionStatus,
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
        hardware_adjusted_max_complexity = self._calculate_adjusted_max_complexity(
            rule.max_complexity,
            hardware_scaling_factor,
        )
        warning = self._build_warning(session, rule.validated)
        star_load_indicator = complexity_score / hardware_adjusted_max_complexity

        if complexity_score <= hardware_adjusted_max_complexity:
            status = AdmissionStatus.ACCEPT
            reason = (
                f"Score {complexity_score:.1f} is within the adjusted limit "
                f"{hardware_adjusted_max_complexity:.2f}."
            )
        else:
            status = AdmissionStatus.REJECT
            reason = (
                f"Score {complexity_score:.1f} exceeds the adjusted limit "
                f"{hardware_adjusted_max_complexity:.2f}."
            )

        return AdmissionDecision(
            task_name=session.task_descriptor.task_name,
            hardware=hardware,
            period_ms=period_ms,
            criticality=criticality,
            complexity_score=complexity_score,
            max_complexity=rule.max_complexity,
            hardware_adjusted_max_complexity=hardware_adjusted_max_complexity,
            hardware_scaling_factor=hardware_scaling_factor,
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
            # the reference data set. Other targets are scaled only by
            # documented hardware metadata; no execution time is fabricated.
            return self.calculate_cpu_frequency_scaling_factor(
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
            return rule_max_complexity * hardware_scaling_factor

        raise CalibrationProfileMissingError("Unsupported hardware adjustment mode.")

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
