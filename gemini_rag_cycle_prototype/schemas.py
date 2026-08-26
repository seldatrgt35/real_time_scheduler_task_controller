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


class PredictionResponse(BaseModel):
    analysis_status: Literal["SUPPORTED", "PARTIAL", "UNRESOLVED"]
    function_name: str
    hardware_profile_id: str
    source_analysis: SourceAnalysis
    retrieved_examples_used: list[RetrievedExample] = Field(default_factory=list)
    estimated_nominal_cycles: int | None = None
    estimated_upper_cycles: int | None = None
    estimated_nominal_us: float | None = None
    estimated_upper_us: float | None = None
    confidence_percent: int = Field(ge=0, le=100)
    estimation_reasoning_summary: str
    assumptions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_prediction(self) -> "PredictionResponse":
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
        return self
