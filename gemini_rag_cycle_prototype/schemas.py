from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class StructuralSummary(BaseModel):
    loop_count: int = 0
    nested_loop_depth: int = 0
    known_total_iterations: int | None = None
    has_branches: bool = False
    has_helper_calls: bool = False
    branch_count: int = 0
    helper_call_count: int = 0
    array_access_count: int = 0
    assignment_count: int = 0
    comparison_count: int = 0
    arithmetic_operator_count: int = 0
    bitwise_operator_count: int = 0
    divide_modulo_count: int = 0
    data_types: list[str] = Field(default_factory=list)
    operation_families: list[str] = Field(default_factory=list)
    memory_access_patterns: list[str] = Field(default_factory=list)


class Measurement(BaseModel):
    unit: Literal["us"] = "us"
    sample_count: int | None = None
    minimum_us: float | None = None
    mean_us: float | None = None
    maximum_us: float | None = None
    measurement_overhead_cycles: int | None = None
    source_path: str


class RagRecord(BaseModel):
    task_id: str
    task_name: str
    source_path: str
    source_code: str
    callee_source: str = ""
    source_context: str = ""
    context_fingerprint: str = ""
    source_fingerprint: str
    normalized_source: str
    hardware_profile_id: str
    structural_summary: StructuralSummary
    measurement: Measurement
    dataset_split: str
    warnings: list[str] = Field(default_factory=list)


class RetrievedExample(BaseModel):
    task_id: str
    similarity: float
    measured_mean_us: float | None
    measured_maximum_us: float | None
    reason_used: str


class SourceAnalysis(BaseModel):
    outer_iterations: int | None = None
    inner_iterations_per_outer: int | None = None
    total_inner_iterations: int | None = None
    worst_case_path: list[str] = Field(default_factory=list)
    estimated_source_memory_reads: int | None = None
    estimated_source_memory_writes: int | None = None
    dynamic_helper_calls: int | None = None
    dynamic_nested_helper_calls: int | None = None
    dynamic_divisions: int | None = None
    dynamic_branch_evaluations: int | None = None
    estimated_o0_stack_reads: int | None = None
    estimated_o0_stack_writes: int | None = None
    dominant_operations: list[str] = Field(default_factory=list)


class CycleComponent(BaseModel):
    name: str
    cycles: int | None = None
    evidence: str

    @model_validator(mode="after")
    def validate_signed_adjustment(self) -> "CycleComponent":
        if (
            self.cycles is not None
            and self.cycles < 0
            and self.name != "explicit_structural_adjustment"
        ):
            raise ValueError(
                "negative cycles are allowed only for explicit_structural_adjustment"
            )
        return self


class InstructionCycleEstimate(BaseModel):
    instruction_class: str
    dynamic_count: int = Field(ge=0)
    cycles_each: int = Field(ge=1)
    total_cycles: int = Field(ge=0)
    evidence: str

    @model_validator(mode="after")
    def validate_arithmetic(self) -> "InstructionCycleEstimate":
        if self.dynamic_count * self.cycles_each != self.total_cycles:
            raise ValueError(
                "instruction cycle total must equal dynamic_count * cycles_each"
            )
        return self


class PredictionResponse(BaseModel):
    analysis_status: Literal["SUPPORTED", "PARTIAL", "UNRESOLVED"]
    function_name: str
    hardware_profile_id: str
    source_analysis: SourceAnalysis
    retrieved_examples_used: list[RetrievedExample] = Field(default_factory=list)
    estimation_basis: Literal["REFERENCE_ANCHORED", "SOURCE_ONLY"]
    reference_anchor_task_id: str | None = None
    reference_anchor_measured_us: float | None = None
    reference_adjustments: list[str] = Field(default_factory=list)
    cycle_components: list[CycleComponent] = Field(default_factory=list)
    predicted_assembly_outline: list[str] = Field(default_factory=list)
    instruction_cycle_ledger: list[InstructionCycleEstimate] = Field(
        default_factory=list
    )
    estimated_source_execution_cycles: int | None = None
    estimated_source_execution_us: float | None = None
    formal_guarantee: bool = False
    confidence_percent: int = Field(ge=0, le=100)
    estimation_reasoning_summary: str
    assumptions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_prediction(self) -> "PredictionResponse":
        if self.formal_guarantee:
            raise ValueError("source-level prediction cannot be a formal guarantee")
        if self.analysis_status in {"SUPPORTED", "PARTIAL"}:
            required = (
                self.estimated_source_execution_cycles,
                self.estimated_source_execution_us,
            )
            if any(value is None for value in required):
                raise ValueError(
                    "SUPPORTED and PARTIAL require source cycle and time predictions"
                )
        if self.estimated_source_execution_cycles is not None and self.estimated_source_execution_cycles <= 0:
            raise ValueError("source execution cycles must be positive")
        if self.estimated_source_execution_us is not None and self.estimated_source_execution_us <= 0:
            raise ValueError("source execution time must be positive")
        priced_components = [
            component.cycles
            for component in self.cycle_components
            if component.cycles is not None
        ]
        if self.estimated_source_execution_cycles is not None and not self.cycle_components:
            raise ValueError("source execution estimate requires cycle components")
        if (
            self.estimated_source_execution_cycles is not None
            and priced_components
            and sum(priced_components) != self.estimated_source_execution_cycles
        ):
            raise ValueError(
                "source execution cycles must equal the sum of priced cycle components"
            )
        if any(component.cycles is None for component in self.cycle_components):
            if self.analysis_status != "PARTIAL":
                raise ValueError("unpriced cycle components require PARTIAL status")
            if not self.unresolved or not self.warnings:
                raise ValueError(
                    "unpriced cycle components require unresolved and warnings"
                )
        if self.analysis_status == "UNRESOLVED" and not self.unresolved:
            raise ValueError("UNRESOLVED requires an explanation")
        if self.estimation_basis == "REFERENCE_ANCHORED":
            if not self.reference_anchor_task_id or self.reference_anchor_measured_us is None:
                raise ValueError(
                    "REFERENCE_ANCHORED requires anchor task ID and measured time"
                )
            if self.reference_anchor_measured_us <= 0:
                raise ValueError("reference anchor measured time must be positive")
            if not self.reference_adjustments:
                raise ValueError(
                    "REFERENCE_ANCHORED requires explicit structural adjustments"
                )
        elif self.reference_anchor_task_id is not None or self.reference_anchor_measured_us is not None:
            raise ValueError("SOURCE_ONLY cannot claim a reference anchor")
        if any(
            component.name == "holistic_build_profile_estimate"
            for component in self.cycle_components
        ):
            ledger = (
                self.source_analysis.dynamic_helper_calls,
                self.source_analysis.dynamic_nested_helper_calls,
                self.source_analysis.dynamic_divisions,
                self.source_analysis.dynamic_branch_evaluations,
                self.source_analysis.estimated_o0_stack_reads,
                self.source_analysis.estimated_o0_stack_writes,
            )
            if any(value is None for value in ledger):
                raise ValueError(
                    "holistic source-only estimate requires a complete dynamic O0 cost ledger"
                )
        instruction_components = [
            component
            for component in self.cycle_components
            if component.name == "predicted_thumb2_cycle_sum"
        ]
        if instruction_components:
            if not self.predicted_assembly_outline or not self.instruction_cycle_ledger:
                raise ValueError(
                    "predicted Thumb-2 estimate requires assembly outline and instruction ledger"
                )
            ledger_total = sum(
                item.total_cycles for item in self.instruction_cycle_ledger
            )
            if ledger_total != instruction_components[0].cycles:
                raise ValueError(
                    "instruction ledger total must equal predicted Thumb-2 component"
                )
        return self
