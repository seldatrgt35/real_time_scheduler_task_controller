from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


TIMING_PROFILE_CYCLES = {
    "alu_move_compare_shift": 1,
    "multiply": 1,
    "integer_divide_worst_case": 12,
    "sram_or_stack_load": 2,
    "sram_or_stack_store": 2,
    "push_or_pop_register_transfer": 1,
    "multi_register_instruction_overhead": 1,
    "pop_pc_pipeline_refill_worst_case": 3,
    "function_call_bl_with_refill": 4,
    "function_return_with_refill": 4,
    "conditional_branch_taken": 4,
    "conditional_branch_not_taken": 1,
    "unconditional_branch_with_refill": 4,
}


class PlannedFunction(BaseModel):
    function_name: str
    dynamic_calls: int = Field(ge=1)
    call_count_evidence: str


class StructurePlan(BaseModel):
    target_function: str
    selected_path: list[str] = Field(default_factory=list)
    functions: list[PlannedFunction]
    loop_bounds: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_functions(self) -> "StructurePlan":
        names = [item.function_name for item in self.functions]
        if len(names) != len(set(names)):
            raise ValueError("structure plan contains duplicate functions")
        return self


class CalleeCount(BaseModel):
    function_name: str
    calls_per_invocation: int = Field(ge=1)
    evidence: str


class PerCallInstructionCount(BaseModel):
    instruction_class: Literal[
        "alu_move_compare_shift",
        "multiply",
        "integer_divide_worst_case",
        "sram_or_stack_load",
        "sram_or_stack_store",
        "push_or_pop_register_transfer",
        "multi_register_instruction_overhead",
        "pop_pc_pipeline_refill_worst_case",
        "function_call_bl_with_refill",
        "function_return_with_refill",
        "conditional_branch_taken",
        "conditional_branch_not_taken",
        "unconditional_branch_with_refill",
    ]
    dynamic_count_per_invocation: int = Field(ge=0)
    evidence: str


class FunctionLedger(BaseModel):
    function_name: str
    selected_path: list[str] = Field(default_factory=list)
    callees: list[CalleeCount] = Field(default_factory=list)
    conditional_branch_evaluations_per_invocation: int = Field(ge=0)
    instruction_counts: list[PerCallInstructionCount]
    unresolved: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_internal_consistency(self) -> "FunctionLedger":
        classes = [item.instruction_class for item in self.instruction_counts]
        if len(classes) != len(set(classes)):
            raise ValueError("instruction classes must be aggregated and unique")
        counts = {
            item.instruction_class: item.dynamic_count_per_invocation
            for item in self.instruction_counts
        }
        expected_bl = sum(item.calls_per_invocation for item in self.callees)
        if counts.get("function_call_bl_with_refill", 0) != expected_bl:
            raise ValueError(
                "per-call BL count must equal declared callee-call count"
            )
        conditional = (
            counts.get("conditional_branch_taken", 0)
            + counts.get("conditional_branch_not_taken", 0)
        )
        if conditional != self.conditional_branch_evaluations_per_invocation:
            raise ValueError(
                "conditional branch ledger count must equal declared evaluations"
            )
        if counts.get("function_return_with_refill", 0) < 1:
            raise ValueError("each invoked function requires a return")
        return self


class AggregateInstructionCycles(BaseModel):
    instruction_class: str
    dynamic_count: int
    cycles_each: int
    total_cycles: int


class FunctionContribution(BaseModel):
    function_name: str
    dynamic_calls: int
    cycles_per_invocation: int
    total_cycles: int


class StagedPrediction(BaseModel):
    analysis_status: Literal["SUPPORTED", "VALIDATION_REQUIRED"]
    provider: str
    model: str
    target_function: str
    hardware_profile_id: str
    structure_plan: StructurePlan
    function_ledgers: list[FunctionLedger]
    function_contributions: list[FunctionContribution]
    aggregate_instruction_ledger: list[AggregateInstructionCycles]
    estimated_source_execution_cycles: int | None
    estimated_source_execution_us: float | None
    formal_guarantee: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
