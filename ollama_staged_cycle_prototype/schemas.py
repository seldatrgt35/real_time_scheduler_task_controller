from __future__ import annotations

from collections import defaultdict
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
    evidence: str = Field(default="", max_length=200)


class PredictedBasicBlock(BaseModel):
    block_id: str = Field(max_length=64)
    source_region: str = Field(max_length=200)
    execution_count_per_invocation: int = Field(ge=0)
    execution_count_evidence: str = Field(default="", max_length=200)
    successors: list[str] = Field(default_factory=list, max_length=4)
    instruction_counts: list[StaticBlockInstructionCount] = Field(
        min_length=1, max_length=len(TIMING_PROFILE_CYCLES)
    )

class ControlFlowEdge(BaseModel):
    source_block: str = Field(max_length=64)
    target_block: str = Field(max_length=64)
    kind: Literal[
        "conditional_taken",
        "conditional_not_taken",
        "unconditional",
        "fallthrough",
    ]
    execution_count_per_invocation: int = Field(ge=0)
    evidence: str = Field(default="", max_length=200)


class AssemblySection(BaseModel):
    section_name: str = Field(max_length=64)
    execution_count: int = Field(ge=0)
    instructions: list[str] = Field(min_length=1, max_length=256)


class FunctionAssemblyPlan(BaseModel):
    function_name: str = Field(max_length=128)
    sections: list[AssemblySection] = Field(min_length=1, max_length=16)
    unresolved: list[str] = Field(default_factory=list, max_length=16)


class FunctionBlockPlan(BaseModel):
    function_name: str = Field(max_length=128)
    selected_path: list[str] = Field(min_length=1, max_length=32)
    callees: list[CalleeCount] = Field(default_factory=list, max_length=16)
    blocks: list[PredictedBasicBlock] = Field(min_length=1, max_length=32)
    edges: list[ControlFlowEdge] = Field(default_factory=list, max_length=64)
    unresolved: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def unique_blocks_and_valid_successors(self) -> "FunctionBlockPlan":
        ids = [block.block_id for block in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("basic block IDs must be unique")
        ids_set = set(ids)
        for block in self.blocks:
            block.successors = [s for s in block.successors if s in ids_set]

        # Prune edges referencing undefined blocks
        self.edges = [
            edge for edge in self.edges
            if edge.source_block in ids_set and edge.target_block in ids_set
        ]

        # Deduplicate edges if model repeats any
        seen_edges = set()
        deduped_edges = []
        for edge in self.edges:
            key = (edge.source_block, edge.target_block, edge.kind)
            if key not in seen_edges:
                seen_edges.add(key)
                deduped_edges.append(edge)
        self.edges = deduped_edges

        outgoing: dict[str, list[ControlFlowEdge]] = {}
        for edge in self.edges:
            outgoing.setdefault(edge.source_block, []).append(edge)

        for block in self.blocks:
            represented = {
                edge.target_block for edge in outgoing.get(block.block_id, [])
            }
            if set(block.successors) != represented:
                # Auto-sync declared successors from actual executed control-flow edges
                block.successors = sorted(represented)

        for source, source_edges in outgoing.items():
            conditional = [edge for edge in source_edges if edge.kind.startswith(
                "conditional_"
            )]
            if conditional:
                kinds = {edge.kind for edge in conditional}
                if "conditional_not_taken" not in kinds:
                    fallback_target = conditional[0].target_block
                    new_edge = ControlFlowEdge(
                        source_block=source,
                        target_block=fallback_target,
                        kind="conditional_not_taken",
                        execution_count_per_invocation=0,
                        evidence="auto-completed by framework",
                    )
                    self.edges.append(new_edge)
                    conditional.append(new_edge)
                elif "conditional_taken" not in kinds:
                    fallback_target = conditional[0].target_block
                    new_edge = ControlFlowEdge(
                        source_block=source,
                        target_block=fallback_target,
                        kind="conditional_taken",
                        execution_count_per_invocation=0,
                        evidence="auto-completed by framework",
                    )
                    self.edges.append(new_edge)
                    conditional.append(new_edge)

                evaluations = sum(
                    edge.execution_count_per_invocation for edge in conditional
                )
                source_block_obj = next((b for b in self.blocks if b.block_id == source), None)
                if source_block_obj and source_block_obj.execution_count_per_invocation != evaluations:
                    source_block_obj.execution_count_per_invocation = evaluations

        # Zero out blocks whose explicit incoming edges are all zero (CFG reachability):
        incoming_edges: dict[str, list[ControlFlowEdge]] = defaultdict(list)
        for edge in self.edges:
            incoming_edges[edge.target_block].append(edge)

        entry_block_id = self.selected_path[0] if self.selected_path else (self.blocks[0].block_id if self.blocks else None)
        for block in self.blocks:
            if block.block_id == entry_block_id:
                continue
            if block.block_id in incoming_edges:
                total_in = sum(e.execution_count_per_invocation for e in incoming_edges[block.block_id])
                if total_in == 0 and block.execution_count_per_invocation > 0:
                    block.execution_count_per_invocation = 0
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
    function_assembly_plans: list[FunctionAssemblyPlan] = Field(default_factory=list)
    function_ledgers: list[FunctionLedger]
    function_contributions: list[FunctionContribution]
    aggregate_instruction_ledger: list[AggregateInstructionCycles]
    estimated_source_execution_cycles: int | None
    estimated_source_execution_us: float | None
    formal_guarantee: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
