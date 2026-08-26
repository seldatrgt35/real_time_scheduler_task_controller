from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class StructuralSummary(BaseModel):
    loop_count: int = 0
    nested_loop_depth: int = 0
    known_total_iterations: int | None = None
    has_branches: bool = False
    has_helper_calls: bool = False
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
    dominant_operations: list[str] = Field(default_factory=list)
    nominal_input_scenario: str | None = None
    upper_input_scenario: str | None = None


class CycleComponent(BaseModel):
    name: str
    cycles: int = Field(ge=0)
    basis: str


class HelperInvocationLedger(BaseModel):
    function: str
    dynamic_calls: int = Field(ge=0)
    nominal_cycles_per_call: int | None = Field(default=None, ge=0)
    upper_cycles_per_call: int | None = Field(default=None, ge=0)
    nominal_total_cycles: int | None = Field(default=None, ge=0)
    upper_total_cycles: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_totals(self) -> "HelperInvocationLedger":
        pairs = (
            (self.nominal_cycles_per_call, self.nominal_total_cycles, "nominal"),
            (self.upper_cycles_per_call, self.upper_total_cycles, "upper"),
        )
        for per_call, total, label in pairs:
            if per_call is not None and total is not None:
                expected = self.dynamic_calls * per_call
                if total != expected:
                    raise ValueError(
                        f"{label} helper total mismatch for {self.function}: "
                        f"expected {expected}, received {total}"
                    )
        return self


class DynamicWorkLedger(BaseModel):
    fixed_overhead_cycles: int | None = Field(default=None, ge=0)
    loop_initializations: int = Field(default=0, ge=0)
    loop_condition_checks: int = Field(default=0, ge=0)
    loop_increments: int = Field(default=0, ge=0)
    helper_invocations: list[HelperInvocationLedger] = Field(default_factory=list)
    source_memory_reads: int | None = Field(default=None, ge=0)
    source_memory_writes: int | None = Field(default=None, ge=0)
    estimated_compiler_memory_overhead_cycles: int | None = Field(default=None, ge=0)
    branches: int | None = Field(default=None, ge=0)
    operator_counts: dict[str, int] = Field(default_factory=dict)
    nominal_cycle_components: list[CycleComponent] = Field(default_factory=list)
    upper_cycle_components: list[CycleComponent] = Field(default_factory=list)


class CycleBreakdown(BaseModel):
    source_visible_nominal: int | None = Field(default=None, ge=0)
    compiler_sensitive_allowance: int | None = Field(default=None, ge=0)
    hardware_sensitive_allowance: int | None = Field(default=None, ge=0)
    total_nominal: int | None = Field(default=None, ge=0)


class PredictionResponse(BaseModel):
    analysis_status: Literal["SUPPORTED", "PARTIAL", "UNRESOLVED"]
    function_name: str
    hardware_profile_id: str
    source_analysis: SourceAnalysis
    dynamic_work_ledger: DynamicWorkLedger = Field(default_factory=DynamicWorkLedger)
    cycle_breakdown: CycleBreakdown = Field(default_factory=CycleBreakdown)
    retrieved_examples_used: list[RetrievedExample] = Field(default_factory=list)
    estimated_nominal_cycles: int | None = None
    estimated_upper_cycles: int | None = None
    estimated_nominal_us: float | None = None
    estimated_upper_us: float | None = None
    upper_basis: Literal[
        "SOURCE_ONLY_ENGINEERING_ESTIMATE",
        "MEASUREMENT_SUPPORTED_ESTIMATE",
        "NOT_AVAILABLE",
    ] = "SOURCE_ONLY_ENGINEERING_ESTIMATE"
    formal_guarantee: bool = False
    confidence_percent: int = Field(ge=0, le=100)
    estimation_reasoning_summary: str
    assumptions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_prediction(self) -> "PredictionResponse":
        if self.formal_guarantee:
            raise ValueError("source-level prediction cannot claim a formal guarantee")
        if self.analysis_status == "SUPPORTED":
            required = (
                self.estimated_nominal_cycles,
                self.estimated_upper_cycles,
                self.estimated_nominal_us,
                self.estimated_upper_us,
            )
            if any(value is None for value in required):
                raise ValueError("SUPPORTED requires cycle and time predictions")
        if self.estimated_nominal_cycles is not None and self.estimated_nominal_cycles <= 0:
            raise ValueError("nominal cycles must be positive")
        if self.estimated_upper_cycles is not None and self.estimated_upper_cycles <= 0:
            raise ValueError("upper cycles must be positive")
        if (
            self.estimated_nominal_cycles is not None
            and self.estimated_upper_cycles is not None
            and self.estimated_upper_cycles < self.estimated_nominal_cycles
        ):
            raise ValueError("upper cycles cannot be smaller than nominal cycles")
        if self.analysis_status == "UNRESOLVED" and not self.unresolved:
            raise ValueError("UNRESOLVED requires an explanation")
        if self.analysis_status == "PARTIAL" and not self.unresolved:
            raise ValueError("PARTIAL requires an explanation")
        if self.estimated_upper_cycles is None and self.upper_basis != "NOT_AVAILABLE":
            raise ValueError("missing upper estimate requires upper_basis=NOT_AVAILABLE")
        if self.estimated_upper_cycles is not None and self.upper_basis == "NOT_AVAILABLE":
            raise ValueError("available upper estimate cannot use upper_basis=NOT_AVAILABLE")
        if (
            self.cycle_breakdown.total_nominal is not None
            and self.estimated_nominal_cycles is not None
            and self.cycle_breakdown.total_nominal != self.estimated_nominal_cycles
        ):
            raise ValueError("cycle breakdown total does not match nominal cycles")
        component_sets = (
            (self.dynamic_work_ledger.nominal_cycle_components, self.estimated_nominal_cycles, "nominal"),
            (self.dynamic_work_ledger.upper_cycle_components, self.estimated_upper_cycles, "upper"),
        )
        for components, final_value, label in component_sets:
            if components and final_value is not None:
                component_total = sum(component.cycles for component in components)
                if component_total != final_value:
                    raise ValueError(
                        f"{label} component total mismatch: expected {final_value}, "
                        f"received {component_total}"
                    )
        return self
