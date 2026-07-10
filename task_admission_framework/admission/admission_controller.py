"""Rule-based admission controller for STAR."""

from __future__ import annotations

from task_admission_framework.admission.admission_decision import (
    AdmissionDecision,
    AdmissionStatus,
)
from task_admission_framework.pipeline.analysis_session import AnalysisSession
from task_admission_framework.rules.rule_database import RuleDatabase


class AdmissionController:
    """Compares an analysis session with a matching rule threshold."""

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

        if complexity_score <= rule.max_complexity:
            status = AdmissionStatus.ACCEPT
            reason = (
                f"Complexity score {complexity_score} is less than or equal to "
                f"rule maximum {rule.max_complexity}."
            )
        else:
            status = AdmissionStatus.REJECT
            reason = (
                f"Complexity score {complexity_score} exceeds "
                f"rule maximum {rule.max_complexity}."
            )

        return AdmissionDecision(
            task_name=session.task_descriptor.task_name,
            hardware=hardware,
            period_ms=period_ms,
            criticality=criticality,
            complexity_score=complexity_score,
            max_complexity=rule.max_complexity,
            status=status,
            reason=reason,
            rule_source=rule.source,
            rule_validated=rule.validated,
        )
