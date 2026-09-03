from __future__ import annotations

import re
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

KNOWN_THUMB2_OPCODES = {
    "adc", "add", "adds", "adr", "and", "ands", "asr", "b", "bcc",
    "bcs", "beq", "bge", "bgt", "bhi", "bhs", "bl", "ble", "blo",
    "bls", "blt", "blx", "bmi", "bne", "bpl", "bx", "cbnz", "cbz",
    "clz", "cmn", "cmp", "eor", "eors", "it", "ldm", "ldmia", "ldr",
    "ldrb", "ldrh", "ldrsb", "ldrsh", "lsl", "lsls", "lsr", "lsrs",
    "mla", "mls", "mov", "movs", "movt", "movw", "mul", "muls", "mvn",
    "neg", "negs", "nop", "orr", "orrs", "pop", "push", "rev", "ror",
    "asrs", "rsb", "rsbs", "sbc", "sdiv", "stm", "stmia", "str", "strb", "strh", "sub",
    "subs", "tst", "udiv", "umull", "uxtb", "uxth", "sxth",
}
CONDITIONAL_BRANCH_OPCODES = {
    "bcc", "bcs", "beq", "bge", "bgt", "bhi", "bhs", "ble", "blo",
    "bls", "blt", "bmi", "bne", "bpl", "cbnz", "cbz",
}


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


class PredictedInstruction(BaseModel):
    opcode: str
    operands: str = ""
    instruction_class: str
    count_per_block: int = Field(default=1, ge=1)
    timing_profile_record: str
    not_taken_timing_profile_record: str | None = None
    register_transfer_count: int | None = Field(default=None, ge=1)
    taken_count: int | None = Field(default=None, ge=0)
    not_taken_count: int | None = Field(default=None, ge=0)
    callee: str | None = None
    stack_effect_bytes: int = 0
    executed_on_path: bool = True
    role: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_derivable_fields(cls, value):
        if not isinstance(value, dict):
            return value
        raw_opcode = str(value.get("opcode", "")).strip()
        opcode_parts = raw_opcode.split(maxsplit=1)
        if len(opcode_parts) == 2:
            value["opcode"] = opcode_parts[0]
            if not str(value.get("operands", "")).strip():
                value["operands"] = opcode_parts[1]
        opcode = str(value.get("opcode", "")).lower().split(".")[0]
        if opcode in CONDITIONAL_BRANCH_OPCODES:
            value["instruction_class"] = "conditional_branch"
            value["timing_profile_record"] = "conditional_branch_taken"
            value["not_taken_timing_profile_record"] = (
                "conditional_branch_not_taken"
            )
        if opcode in {"push", "pop", "ldm", "ldmia", "stm", "stmia"}:
            operands = str(value.get("operands", ""))
            register_list = re.search(r"\{([^}]+)\}", operands)
            if register_list:
                registers = [
                    register.strip()
                    for register in register_list.group(1).split(",")
                    if register.strip()
                ]
                value["register_transfer_count"] = len(registers)
            value["instruction_class"] = "push_or_pop_register_transfer"
            value["timing_profile_record"] = "push_or_pop_register_transfer"
        return value

    @model_validator(mode="after")
    def validate_instruction_shape(self) -> "PredictedInstruction":
        op = self.opcode.lower().split(".")[0]
        if op not in KNOWN_THUMB2_OPCODES:
            raise ValueError(f"unrecognized Thumb-2 opcode: {self.opcode}")
        is_conditional_branch = op in CONDITIONAL_BRANCH_OPCODES
        if is_conditional_branch:
            if self.taken_count is None or self.not_taken_count is None:
                raise ValueError("conditional branch requires taken_count and not_taken_count")
            if self.timing_profile_record not in {
                "conditional_branch_taken", "conditional_branch_not_taken"
            }:
                raise ValueError("conditional branch requires a branch timing record")
            if self.not_taken_timing_profile_record not in {
                None, "conditional_branch_not_taken"
            }:
                raise ValueError("conditional branch has an invalid not-taken timing record")
        elif self.taken_count is not None or self.not_taken_count is not None:
            raise ValueError("branch counts are valid only for conditional branches")
        if op in {"bl", "blx"} and not self.callee:
            raise ValueError("BL/BLX requires a defined callee")
        if op in {"push", "pop", "ldm", "stm"} and self.register_transfer_count is None:
            raise ValueError("multi-register instruction requires register_transfer_count")
        if self.executed_on_path and self.timing_profile_record not in TIMING_PROFILE_CYCLES:
            raise ValueError("instruction has no recognized timing-profile record")
        return self


class PredictedBasicBlock(BaseModel):
    block_id: str
    execution_count: int = Field(ge=0)
    layout_index: int | None = Field(default=None, ge=0)
    successors: list[str] = Field(default_factory=list)
    fallthrough_successor: str | None = None
    branch_successors: list[str] = Field(default_factory=list)
    loop_iteration_evidence: str | None = None
    instructions: list[PredictedInstruction]

    @model_validator(mode="before")
    @classmethod
    def normalize_per_block_branch_counts(cls, value):
        if not isinstance(value, dict):
            return value
        block_count = int(value.get("execution_count", 0))
        for instruction in value.get("instructions", []):
            if not isinstance(instruction, dict):
                continue
            opcode = str(instruction.get("opcode", "")).lower().split(".")[0]
            if opcode not in CONDITIONAL_BRANCH_OPCODES:
                continue
            taken = int(instruction.get("taken_count") or 0)
            not_taken = int(instruction.get("not_taken_count") or 0)
            count_per_block = int(instruction.get("count_per_block", 1))
            expected = block_count * count_per_block
            if taken + not_taken == count_per_block and expected != count_per_block:
                instruction["taken_count"] = taken * block_count
                instruction["not_taken_count"] = not_taken * block_count
        return value

    @model_validator(mode="after")
    def validate_branch_arithmetic(self) -> "PredictedBasicBlock":
        for instruction in self.instructions:
            opcode = instruction.opcode.lower().split(".")[0]
            if opcode in CONDITIONAL_BRANCH_OPCODES:
                executions = (instruction.taken_count or 0) + (
                    instruction.not_taken_count or 0
                )
                expected = self.execution_count * instruction.count_per_block
                if executions != expected:
                    raise ValueError(
                        "taken_count + not_taken_count must equal branch execution count"
                    )
        return self


class PredictedFunctionAssembly(BaseModel):
    function_name: str
    execution_count: int = Field(ge=1)
    entry_block_id: str
    blocks: list[PredictedBasicBlock]
    stack_allocation_bytes: int = Field(ge=0)
    stack_deallocation_bytes: int = Field(ge=0)
    lr_saved: bool
    valid_return_via: Literal["BX_LR", "POP_PC"]
    loop_bounds_proven: bool
    successors_inferred: bool = False

    @model_validator(mode="before")
    @classmethod
    def infer_missing_successors(cls, value):
        if not isinstance(value, dict):
            return value
        blocks = value.get("blocks", [])
        for index, block in enumerate(blocks):
            if block.get("layout_index") is None:
                block["layout_index"] = index
        block_ids = [block.get("block_id") for block in blocks]
        known_ids = set(block_ids)
        inferred_any = False
        for index, block in enumerate(blocks):
            if block.get("successors"):
                continue
            instructions = block.get("instructions", [])
            executed = [
                instruction for instruction in instructions
                if instruction.get("executed_on_path", True)
            ]
            successor_ids: list[str] = []
            terminal_return = False
            unconditional = False
            conditional = False
            for instruction in executed:
                opcode = str(instruction.get("opcode", "")).lower().split()[0]
                opcode = opcode.split(".")[0]
                operands = str(instruction.get("operands", ""))
                if opcode in CONDITIONAL_BRANCH_OPCODES:
                    conditional = True
                    successor_ids.extend(
                        block_id for block_id in block_ids
                        if block_id and block_id in operands
                    )
                elif opcode == "b":
                    unconditional = True
                    successor_ids.extend(
                        block_id for block_id in block_ids
                        if block_id and block_id in operands
                    )
                elif opcode == "bx" and operands.strip().lower() == "lr":
                    terminal_return = True
                elif opcode == "pop" and "pc" in operands.lower():
                    terminal_return = True
            next_block = block_ids[index + 1] if index + 1 < len(block_ids) else None
            if next_block and not terminal_return and (conditional or not unconditional):
                successor_ids.append(next_block)
            inferred_successors = list(dict.fromkeys(
                successor for successor in successor_ids if successor in known_ids
            ))
            block["successors"] = inferred_successors
            if inferred_successors:
                inferred_any = True
        if inferred_any:
            value["successors_inferred"] = True
        return value

    @model_validator(mode="after")
    def validate_cfg_and_call_frame(self) -> "PredictedFunctionAssembly":
        by_id = {block.block_id: block for block in self.blocks}
        if len(by_id) != len(self.blocks):
            raise ValueError("basic block IDs must be unique within a function")
        if self.entry_block_id not in by_id:
            raise ValueError("function entry block does not exist")
        layout_indices = [block.layout_index for block in self.blocks]
        if any(index is None for index in layout_indices):
            raise ValueError("every basic block requires a layout index")
        if sorted(layout_indices) != list(range(len(self.blocks))):
            raise ValueError(
                "basic block layout indices must be unique and contiguous"
            )
        layout = sorted(self.blocks, key=lambda block: block.layout_index or 0)
        next_by_id = {
            block.block_id: (
                layout[index + 1].block_id
                if index + 1 < len(layout) else None
            )
            for index, block in enumerate(layout)
        }
        for block in self.blocks:
            missing = set(block.successors) - set(by_id)
            if missing:
                raise ValueError(f"basic block has unknown successor: {sorted(missing)}")
            physical_next = next_by_id[block.block_id]
            if (
                block.fallthrough_successor is not None
                and block.fallthrough_successor != physical_next
            ):
                raise ValueError(
                    "fallthrough successor must be the physically next basic block"
                )
            if set(block.branch_successors) - set(block.successors):
                raise ValueError("branch successor must also be a CFG successor")
            if (
                block.fallthrough_successor is not None
                and block.fallthrough_successor not in block.successors
            ):
                raise ValueError("fallthrough must also be a CFG successor")
            branch_targets: list[str] = []
            conditional_count = 0
            unconditional_count = 0
            for instruction in block.instructions:
                if not instruction.executed_on_path:
                    continue
                opcode = instruction.opcode.lower().split(".")[0]
                operands = instruction.operands
                targets = [
                    target for target in by_id
                    if re.search(
                        rf"(?<![A-Za-z0-9_]){re.escape(target)}(?![A-Za-z0-9_])",
                        operands,
                    )
                ]
                if opcode in CONDITIONAL_BRANCH_OPCODES:
                    conditional_count += instruction.count_per_block
                    branch_targets.extend(targets)
                elif opcode == "b":
                    unconditional_count += instruction.count_per_block
                    branch_targets.extend(targets)
                    if physical_next is not None and physical_next in targets:
                        raise ValueError(
                            "unconditional branch to the physically next block "
                            "must be represented as fallthrough"
                        )
            if conditional_count > 0:
                if block.fallthrough_successor is None:
                    raise ValueError(
                        "conditional branch requires an explicit fallthrough successor"
                    )
                if len(block.successors) != 2:
                    raise ValueError(
                        "conditional branch block requires exactly two successors"
                    )
            if unconditional_count > 0 and block.fallthrough_successor is not None:
                raise ValueError(
                    "unconditional branch block cannot also declare fallthrough"
                )
            declared_branch_targets = set(block.branch_successors)
            discovered_branch_targets = set(branch_targets)
            if declared_branch_targets and (
                declared_branch_targets != discovered_branch_targets
            ):
                raise ValueError(
                    "declared branch successors do not match instruction targets"
                )
            represented = declared_branch_targets or discovered_branch_targets
            if block.fallthrough_successor is not None:
                represented = represented | {block.fallthrough_successor}
            if represented and represented != set(block.successors):
                raise ValueError(
                    "CFG successors must be partitioned into branch and fallthrough successors"
                )
        reachable: set[str] = set()
        pending = [self.entry_block_id]
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)
            pending.extend(by_id[current].successors)
        unreachable_executed = {
            block_id
            for block_id, block in by_id.items()
            if block_id not in reachable and block.execution_count > 0
        }
        if unreachable_executed and not self.successors_inferred:
            raise ValueError(
                "function contains an unreachable executed basic block: "
                f"{sorted(unreachable_executed)}"
            )
        if self.stack_allocation_bytes != self.stack_deallocation_bytes:
            raise ValueError("stack allocation/deallocation is not balanced")
        calls = [
            instruction
            for block in self.blocks
            for instruction in block.instructions
            if instruction.opcode.lower().split(".")[0] in {"bl", "blx"}
            and instruction.executed_on_path
        ]
        if calls and not self.lr_saved:
            raise ValueError("function containing BL/BLX must preserve LR")
        explicit_lr_restore = any(
            instruction.opcode.lower().split(".")[0] in {"pop", "ldm", "ldmia"}
            and "lr" in instruction.operands.lower()
            and instruction.executed_on_path
            for block in self.blocks
            for instruction in block.instructions
        )
        if self.valid_return_via == "BX_LR" and calls and not explicit_lr_restore:
            raise ValueError("non-leaf BX LR return requires explicit LR restore")
        return_opcodes = {
            instruction.opcode.lower().split(".")[0]
            for block in self.blocks
            for instruction in block.instructions
            if instruction.executed_on_path
        }
        has_bx_lr = any(
            instruction.opcode.lower().split(".")[0] == "bx"
            and instruction.operands.strip().lower() == "lr"
            and instruction.executed_on_path
            for block in self.blocks
            for instruction in block.instructions
        )
        has_pop_pc = any(
            instruction.opcode.lower().split(".")[0] == "pop"
            and "pc" in instruction.operands.lower()
            and instruction.executed_on_path
            for block in self.blocks
            for instruction in block.instructions
        )
        if has_bx_lr and has_pop_pc:
            raise ValueError("BX LR and POP {...,PC} cannot both be counted as the return path")
        if self.valid_return_via == "BX_LR" and not has_bx_lr:
            raise ValueError("declared BX LR return is absent")
        if self.valid_return_via == "POP_PC" and not has_pop_pc:
            raise ValueError("declared POP PC return is absent")
        if not self.loop_bounds_proven and any(
            block.execution_count > self.execution_count for block in self.blocks
        ):
            raise ValueError("loop execution counts require proven loop bounds")
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
    predicted_functions: list[PredictedFunctionAssembly] = Field(default_factory=list)
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

    @model_validator(mode="before")
    @classmethod
    def rebuild_ledger_from_structured_blocks(cls, value):
        if not isinstance(value, dict) or not value.get("predicted_functions"):
            return value
        counts: dict[str, int] = {}
        for function in value["predicted_functions"]:
            for block in function.get("blocks", []):
                block_count = int(block.get("execution_count", 0))
                for instruction in block.get("instructions", []):
                    if not instruction.get("executed_on_path", True):
                        continue
                    opcode = str(instruction.get("opcode", "")).lower().split(".")[0]
                    if opcode in CONDITIONAL_BRANCH_OPCODES:
                        counts["conditional_branch_taken"] = (
                            counts.get("conditional_branch_taken", 0)
                            + int(instruction.get("taken_count") or 0)
                        )
                        counts["conditional_branch_not_taken"] = (
                            counts.get("conditional_branch_not_taken", 0)
                            + int(instruction.get("not_taken_count") or 0)
                        )
                        continue
                    record = instruction.get("timing_profile_record")
                    if record not in TIMING_PROFILE_CYCLES:
                        continue
                    dynamic_count = block_count * int(
                        instruction.get("count_per_block", 1)
                    )
                    transfer_count = instruction.get("register_transfer_count")
                    if transfer_count is not None:
                        dynamic_count *= int(transfer_count)
                    counts[record] = counts.get(record, 0) + dynamic_count
                    if opcode in {"push", "pop", "ldm", "ldmia", "stm", "stmia"}:
                        instruction_executions = block_count * int(
                            instruction.get("count_per_block", 1)
                        )
                        overhead = "multi_register_instruction_overhead"
                        counts[overhead] = counts.get(overhead, 0) + instruction_executions
                        if opcode == "pop" and "pc" in str(
                            instruction.get("operands", "")
                        ).lower():
                            refill = "pop_pc_pipeline_refill_worst_case"
                            counts[refill] = counts.get(refill, 0) + instruction_executions
        if not counts:
            return value
        supplied = {
            item.get("instruction_class"): (
                item.get("dynamic_count"), item.get("cycles_each"), item.get("total_cycles")
            )
            for item in value.get("instruction_cycle_ledger", [])
            if isinstance(item, dict)
        }
        rebuilt = []
        for record, dynamic_count in counts.items():
            cycles_each = TIMING_PROFILE_CYCLES[record]
            rebuilt.append({
                "instruction_class": record,
                "dynamic_count": dynamic_count,
                "cycles_each": cycles_each,
                "total_cycles": dynamic_count * cycles_each,
                "evidence": "deterministically rebuilt from structured basic blocks",
            })
        total_cycles = sum(item["total_cycles"] for item in rebuilt)
        value["instruction_cycle_ledger"] = rebuilt
        for component in value.get("cycle_components", []):
            if component.get("name") == "predicted_thumb2_cycle_sum":
                component["cycles"] = total_cycles
                component["evidence"] = (
                    "deterministically rebuilt from structured basic blocks "
                    "and the configured timing profile"
                )
        value["estimated_source_execution_cycles"] = total_cycles
        value["estimated_source_execution_us"] = total_cycles / 48.0
        rebuilt_signature = {
            item["instruction_class"]: (
                item["dynamic_count"], item["cycles_each"], item["total_cycles"]
            )
            for item in rebuilt
        }
        if supplied != rebuilt_signature:
            warnings = value.setdefault("warnings", [])
            warning = (
                "Gemini instruction-ledger counts disagreed with structured "
                "basic blocks; the ledger and total were replaced deterministically."
            )
            if warning not in warnings:
                warnings.append(warning)
        return value

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
            if not self.predicted_functions or not self.instruction_cycle_ledger:
                raise ValueError(
                    "predicted Thumb-2 estimate requires structured functions and instruction ledger"
                )
            functions = {function.function_name: function for function in self.predicted_functions}
            if self.function_name not in functions:
                raise ValueError("structured assembly does not contain the query function")
            call_counts: dict[str, int] = {}
            for function in self.predicted_functions:
                for block in function.blocks:
                    for instruction in block.instructions:
                        if instruction.callee and instruction.executed_on_path:
                            count = block.execution_count * instruction.count_per_block
                            call_counts[instruction.callee] = call_counts.get(instruction.callee, 0) + count
            for callee, count in call_counts.items():
                if callee not in functions:
                    raise ValueError(f"BL callee has no structured helper body: {callee}")
                if functions[callee].execution_count != count:
                    raise ValueError("helper execution count must equal dynamic BL count")
            computed_counts: dict[str, int] = {}
            for function in self.predicted_functions:
                for block in function.blocks:
                    for instruction in block.instructions:
                        if not instruction.executed_on_path:
                            continue
                        opcode = instruction.opcode.lower().split(".")[0]
                        if opcode in CONDITIONAL_BRANCH_OPCODES:
                            computed_counts["conditional_branch_taken"] = (
                                computed_counts.get("conditional_branch_taken", 0)
                                + (instruction.taken_count or 0)
                            )
                            computed_counts["conditional_branch_not_taken"] = (
                                computed_counts.get("conditional_branch_not_taken", 0)
                                + (instruction.not_taken_count or 0)
                            )
                            continue
                        count = block.execution_count * instruction.count_per_block
                        if instruction.register_transfer_count is not None:
                            count *= instruction.register_transfer_count
                        record = instruction.timing_profile_record
                        computed_counts[record] = computed_counts.get(record, 0) + count
                        if opcode in {"push", "pop", "ldm", "ldmia", "stm", "stmia"}:
                            instruction_executions = (
                                block.execution_count * instruction.count_per_block
                            )
                            overhead = "multi_register_instruction_overhead"
                            computed_counts[overhead] = (
                                computed_counts.get(overhead, 0)
                                + instruction_executions
                            )
                            if opcode == "pop" and "pc" in instruction.operands.lower():
                                refill = "pop_pc_pipeline_refill_worst_case"
                                computed_counts[refill] = (
                                    computed_counts.get(refill, 0)
                                    + instruction_executions
                                )
            ledger_counts = {
                item.instruction_class: item.dynamic_count
                for item in self.instruction_cycle_ledger
            }
            if computed_counts != ledger_counts:
                warning = (
                    "Normalized structured basic-block counts changed the "
                    "instruction ledger; the ledger and total were rebuilt "
                    "deterministically."
                )
                if warning not in self.warnings:
                    self.warnings.append(warning)
            self.instruction_cycle_ledger = [
                InstructionCycleEstimate(
                    instruction_class=record,
                    dynamic_count=count,
                    cycles_each=TIMING_PROFILE_CYCLES[record],
                    total_cycles=count * TIMING_PROFILE_CYCLES[record],
                    evidence=(
                        "deterministically rebuilt from validated structured "
                        "basic blocks"
                    ),
                )
                for record, count in computed_counts.items()
            ]
            deterministic_total = sum(
                item.total_cycles for item in self.instruction_cycle_ledger
            )
            instruction_components[0].cycles = deterministic_total
            instruction_components[0].evidence = (
                "deterministically rebuilt from validated structured basic "
                "blocks and the configured timing profile"
            )
            self.estimated_source_execution_cycles = deterministic_total
            self.estimated_source_execution_us = deterministic_total / 48.0
            ledger_total = sum(
                item.total_cycles for item in self.instruction_cycle_ledger
            )
            if ledger_total != instruction_components[0].cycles:
                raise ValueError(
                    "instruction ledger total must equal predicted Thumb-2 component"
                )
        return self
