from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


_CONDITIONAL_BRANCH_RE = re.compile(
    r"\bB(?:EQ|NE|CS|HS|CC|LO|MI|PL|VS|VC|HI|LS|GE|LT|GT|LE)(?:\.[NW])?\b",
    re.IGNORECASE,
)
_UNCONDITIONAL_BRANCH_RE = re.compile(r"\bB(?:\.[NW])?\b", re.IGNORECASE)
_CALL_RE = re.compile(r"\bBLX?(?:\.[NW])?\b", re.IGNORECASE)
_LOAD_RE = re.compile(r"\bLDR(?:B|H|SB|SH|D)?(?:\.[NW])?\b", re.IGNORECASE)
_STORE_RE = re.compile(r"\bSTR(?:B|H|D)?(?:\.[NW])?\b", re.IGNORECASE)
_PUSH_POP_RE = re.compile(r"\b(?:PUSH|POP)(?:\.[NW])?\b", re.IGNORECASE)
_ALU_RE = re.compile(
    r"\b(?:MOVS?|MVN|ADD|ADDS|ADC|ADCS|SUB|SUBS|SBC|SBCS|RSB|RSBS|CMP|CMN|"
    r"TST|TEQ|AND|ANDS|ORR|ORRS|EOR|EORS|BIC|BICS|LSL|LSLS|LSR|LSRS|"
    r"ASR|ASRS|ROR|RORS|UXTB|UXTH|SXTB|SXTH)(?:\.[NW])?\b",
    re.IGNORECASE,
)
_MULTIPLY_RE = re.compile(r"\b(?:MUL|MULS|MLA|MLS)\b", re.IGNORECASE)
_DIVIDE_RE = re.compile(r"\b(?:SDIV|UDIV)\b", re.IGNORECASE)
_ASSEMBLY_EVIDENCE_RE = re.compile(
    r"(?:\b(?:r1?[0-9]|sp|lr|pc)\b|[#\[\]{}]|\.[nw]\b)", re.IGNORECASE
)
_MULTIPLICITY_RE = re.compile(r"(?:\s|\*)x?(\d+)\s*$", re.IGNORECASE)


def _mnemonic_class(text: str) -> str | None:
    """Map one assembly evidence fragment to its timing-ledger class."""
    if _CALL_RE.search(text):
        return "function_call_bl_with_refill"
    if _CONDITIONAL_BRANCH_RE.search(text):
        return "conditional_branch_taken"
    if _UNCONDITIONAL_BRANCH_RE.search(text):
        return "unconditional_branch_with_refill"
    if _LOAD_RE.search(text):
        return "sram_or_stack_load"
    if _STORE_RE.search(text):
        return "sram_or_stack_store"
    if _PUSH_POP_RE.search(text):
        return "push_or_pop_register_transfer"
    if _DIVIDE_RE.search(text):
        return "integer_divide_worst_case"
    if _MULTIPLY_RE.search(text):
        return "multiply"
    if _ALU_RE.search(text):
        return "alu_move_compare_shift"
    return None


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
    model_config = ConfigDict(populate_by_name=True)

    function_name: str = Field(max_length=128, alias="fn")
    calls_per_invocation: int = Field(ge=1, alias="n")
    evidence: str = Field(max_length=240, alias="why")


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
    model_config = ConfigDict(populate_by_name=True)

    instruction_class: Literal[
        "alu_move_compare_shift", "multiply", "integer_divide_worst_case",
        "sram_or_stack_load", "sram_or_stack_store",
        "push_or_pop_register_transfer", "multi_register_instruction_overhead",
        "pop_pc_pipeline_refill_worst_case", "function_call_bl_with_refill",
        "function_return_with_refill", "conditional_branch_taken",
        "conditional_branch_not_taken", "unconditional_branch_with_refill",
    ] = Field(alias="c")
    static_count: int = Field(ge=0, alias="n")
    evidence: str = Field(max_length=160, alias="op")

    @model_validator(mode="after")
    def evidence_mnemonics_match_class(self) -> "StaticBlockInstructionCount":
        """Reject opcode examples placed under an incompatible timing class."""
        text = self.evidence
        if not _ASSEMBLY_EVIDENCE_RE.search(text):
            return self
        found = {
            "conditional": bool(_CONDITIONAL_BRANCH_RE.search(text)),
            "unconditional": bool(_UNCONDITIONAL_BRANCH_RE.search(text)),
            "call": bool(_CALL_RE.search(text)),
            "load": bool(_LOAD_RE.search(text)),
            "store": bool(_STORE_RE.search(text)),
            "push_pop": bool(_PUSH_POP_RE.search(text)),
            "alu": bool(_ALU_RE.search(text)),
        }
        # BL contains the token B; do not also interpret it as an unconditional
        # branch. Conditional Bxx mnemonics likewise take precedence over B.
        if found["call"] or found["conditional"]:
            found["unconditional"] = False

        allowed = {
            "alu_move_compare_shift": {"alu"},
            "sram_or_stack_load": {"load"},
            "sram_or_stack_store": {"store"},
            "push_or_pop_register_transfer": {"push_pop"},
            "multi_register_instruction_overhead": {"push_pop"},
            "pop_pc_pipeline_refill_worst_case": {"push_pop"},
            "function_call_bl_with_refill": {"call"},
            "function_return_with_refill": {"push_pop"},
            "conditional_branch_taken": {"conditional"},
            "conditional_branch_not_taken": {"conditional"},
            "unconditional_branch_with_refill": {"unconditional"},
        }.get(self.instruction_class)
        if allowed is None:
            return self

        incompatible = sorted(
            kind for kind, present in found.items()
            if present and kind not in allowed
        )
        if incompatible:
            raise ValueError(
                f"opcode evidence for {self.instruction_class} contains "
                f"incompatible mnemonic classes: {incompatible}"
            )
        return self


class PredictedBasicBlock(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    block_id: str = Field(max_length=128, alias="id")
    source_region: str = Field(max_length=200, alias="src")
    execution_count_per_invocation: int = Field(ge=0, alias="x")
    execution_count_evidence: str = Field(max_length=200, alias="why")
    successors: list[str] = Field(default_factory=list, max_length=4, alias="next")
    instruction_counts: list[StaticBlockInstructionCount] = Field(
        min_length=1, max_length=len(TIMING_PROFILE_CYCLES), alias="ins"
    )

    @model_validator(mode="before")
    @classmethod
    def split_mixed_opcode_evidence(cls, value):
        """Canonicalize explicit mnemonic lists before row validation.

        Local models commonly put ``CMP ...; BNE ...`` in one aggregate row.
        When the evidence contains exactly one semicolon-separated fragment per
        declared instruction, the opcode text is authoritative and can be
        deterministically regrouped without inventing instructions.
        """
        if not isinstance(value, dict):
            return value
        output_key = "ins" if "ins" in value else "instruction_counts"
        rows = value.get(output_key)
        if not isinstance(rows, list):
            return value

        normalized: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                normalized.append(row)
                continue
            row_class = row.get("instruction_class", row.get("c"))
            count = row.get("static_count", row.get("n"))
            evidence = row.get("evidence", row.get("op"))
            if not isinstance(count, int) or count <= 0 or not isinstance(evidence, str):
                normalized.append(row)
                continue
            fragments = [part.strip() for part in evidence.split(";") if part.strip()]
            classes = [_mnemonic_class(part) for part in fragments]
            if any(item is None for item in classes):
                normalized.append(row)
                continue
            weights = []
            for fragment in fragments:
                match = _MULTIPLICITY_RE.search(fragment)
                weights.append(int(match.group(1)) if match else 1)
            original_class = row_class
            if original_class in {
                "conditional_branch_taken", "conditional_branch_not_taken",
            }:
                classes = [
                    original_class if item == "conditional_branch_taken" else item
                    for item in classes
                ]
            if sum(weights) != count:
                normalized.append(row)
                continue

            grouped: dict[str, list[tuple[str, int]]] = {}
            for fragment, instruction_class, weight in zip(fragments, classes, weights):
                grouped.setdefault(instruction_class, []).append((fragment, weight))
            for instruction_class, items in grouped.items():
                normalized.append({
                    "instruction_class": instruction_class,
                    "static_count": sum(weight for _, weight in items),
                    "evidence": "; ".join(fragment for fragment, _ in items),
                })

        # Regroup duplicate classes produced by separate draft rows.
        combined: dict[str, dict] = {}
        for row in normalized:
            if not isinstance(row, dict):
                continue
            instruction_class = row.get("instruction_class", row.get("c"))
            if instruction_class is None:
                continue
            row_count = row.get("static_count", row.get("n", 0))
            row_evidence = row.get("evidence", row.get("op", ""))
            if instruction_class not in combined:
                combined[instruction_class] = {
                    "instruction_class": instruction_class,
                    "static_count": row_count,
                    "evidence": row_evidence,
                }
            else:
                combined[instruction_class]["static_count"] += row_count
                prior = combined[instruction_class].get("evidence", "")
                current = row_evidence
                combined[instruction_class]["evidence"] = "; ".join(
                    part for part in (prior, current) if part
                )[:500]
        value = dict(value)
        value[output_key] = list(combined.values())
        return value


class FunctionBlockPlan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    function_name: str = Field(max_length=128, alias="fn")
    selected_path: list[str] = Field(default_factory=list, max_length=64, alias="path")
    callees: list[CalleeCount] = Field(default_factory=list, max_length=32, alias="calls")
    blocks: list[PredictedBasicBlock] = Field(min_length=1, max_length=64, alias="blocks")
    unresolved: list[str] = Field(default_factory=list, max_length=32, alias="open")

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
