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
    function_name: str = Field(max_length=128)
    dynamic_calls: int = Field(ge=1)
    call_count_evidence: str = Field(max_length=500)


class StructurePlan(BaseModel):
    target_function: str
    selected_path: list[str] = Field(default_factory=list, max_length=64)
    functions: list[PlannedFunction] = Field(max_length=64)
    loop_bounds: list[str] = Field(default_factory=list, max_length=64)
    unresolved: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def unique_functions(self) -> "StructurePlan":
        names = [item.function_name for item in self.functions]
        if len(names) != len(set(names)):
            raise ValueError("structure plan contains duplicate functions")
        return self


class CalleeCount(BaseModel):
    function_name: str = Field(max_length=128)
    calls_per_invocation: int = Field(ge=1)
    evidence: str = Field(max_length=500)


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
    evidence: str = Field(max_length=500)


class StaticBlockInstructionCount(BaseModel):
    instruction_class: Literal[
        "alu_move_compare_shift", "multiply", "integer_divide_worst_case",
        "sram_or_stack_load", "sram_or_stack_store",
        "push_or_pop_register_transfer", "multi_register_instruction_overhead",
        "pop_pc_pipeline_refill_worst_case", "function_call_bl_with_refill",
        "function_return_with_refill",
    ]
    static_count: int = Field(ge=0)
    evidence: str = Field(max_length=500)


class PredictedBasicBlock(BaseModel):
    block_id: str = Field(max_length=128)
    source_region: str = Field(max_length=500)
    execution_count_per_invocation: int = Field(ge=0)
    execution_count_evidence: str = Field(max_length=500)
    successors: list[str] = Field(default_factory=list, max_length=4)
    instruction_counts: list[StaticBlockInstructionCount] = Field(
        min_length=1, max_length=len(TIMING_PROFILE_CYCLES)
    )

class ControlFlowEdge(BaseModel):
    source_block: str = Field(max_length=128)
    target_block: str = Field(max_length=128)
    kind: Literal[
        "conditional_taken",
        "conditional_not_taken",
        "unconditional",
        "fallthrough",
    ]
    execution_count_per_invocation: int = Field(ge=0)
    evidence: str = Field(max_length=500)


class FunctionBlockPlan(BaseModel):
    function_name: str = Field(max_length=128)
    selected_path: list[str] = Field(min_length=1, max_length=64)
    callees: list[CalleeCount] = Field(default_factory=list, max_length=32)
    blocks: list[PredictedBasicBlock] = Field(min_length=1, max_length=64)
    edges: list[ControlFlowEdge] = Field(default_factory=list, max_length=128)
    unresolved: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def unique_blocks_and_valid_successors(self) -> "FunctionBlockPlan":
        ids = [block.block_id for block in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("basic block IDs must be unique")
        unknown = {
            successor for block in self.blocks for successor in block.successors
        } - set(ids)
        if unknown:
            raise ValueError(f"basic-block successors are undefined: {sorted(unknown)}")
        unknown_path = set(self.selected_path) - set(ids)
        if unknown_path:
            raise ValueError(
                f"selected_path contains undefined blocks: {sorted(unknown_path)}"
            )
        unknown_edge_blocks = {
            endpoint
            for edge in self.edges
            for endpoint in (edge.source_block, edge.target_block)
            if endpoint not in set(ids)
        }
        if unknown_edge_blocks:
            raise ValueError(
                "control-flow edges reference undefined blocks: "
                f"{sorted(unknown_edge_blocks)}"
            )
        edge_keys = [(edge.source_block, edge.target_block, edge.kind)
                     for edge in self.edges]
        if len(edge_keys) != len(set(edge_keys)):
            raise ValueError("control-flow edges must be unique")

        block_executions = {
            block.block_id: block.execution_count_per_invocation
            for block in self.blocks
        }
        outgoing: dict[str, list[ControlFlowEdge]] = {}
        for edge in self.edges:
            outgoing.setdefault(edge.source_block, []).append(edge)
        for block in self.blocks:
            declared = set(block.successors)
            represented = {
                edge.target_block for edge in outgoing.get(block.block_id, [])
            }
            if represented:
                # Edges carry execution counts and branch kinds, so they are
                # authoritative; successors is only a redundant summary.
                block.successors = sorted(represented)
            elif len(declared) == 1:
                # Models commonly omit an explicit edge for straight-line
                # fallthrough. It has no refill cost, so completing it is
                # deterministic and does not invent cycle-bearing behavior.
                target = next(iter(declared))
                edge = ControlFlowEdge(
                    source_block=block.block_id,
                    target_block=target,
                    kind="fallthrough",
                    execution_count_per_invocation=(
                        block.execution_count_per_invocation
                    ),
                    evidence="canonicalized implicit single-successor fallthrough",
                )
                self.edges.append(edge)
                outgoing[block.block_id] = [edge]
            elif declared:
                raise ValueError(
                    f"multiple successors for {block.block_id} require "
                    "explicit control-flow edges"
                )
        for source, source_edges in outgoing.items():
            conditional = [edge for edge in source_edges if edge.kind.startswith(
                "conditional_"
            )]
            if conditional:
                kinds = {edge.kind for edge in conditional}
                if kinds != {"conditional_taken", "conditional_not_taken"}:
                    raise ValueError(
                        f"conditional block {source} requires taken and "
                        "not-taken edges"
                    )
                evaluations = sum(
                    edge.execution_count_per_invocation for edge in conditional
                )
                if evaluations != block_executions[source]:
                    raise ValueError(
                        f"conditional edge counts for {source} must sum to "
                        "the source block execution count"
                    )
        return self


class FunctionLedger(BaseModel):
    function_name: str = Field(max_length=128)
    selected_path: list[str] = Field(default_factory=list, max_length=64)
    callees: list[CalleeCount] = Field(default_factory=list, max_length=32)
    conditional_branch_evaluations_per_invocation: int = Field(ge=0)
    instruction_counts: list[PerCallInstructionCount] = Field(
        min_length=1, max_length=len(TIMING_PROFILE_CYCLES)
    )
    unresolved: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_internal_consistency(self) -> "FunctionLedger":
        # Cross-row arithmetic is normalized and checked by StagedPredictor.
        # Local models often emit separate PUSH and POP rows for one class.
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
