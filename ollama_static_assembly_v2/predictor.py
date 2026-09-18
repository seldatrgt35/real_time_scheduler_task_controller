from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re

from gemini_rag_cycle_prototype.rag.measurement_loader import (
    extract_function,
    extract_reachable_helpers,
    function_names,
)
from ollama_staged_cycle_prototype.assembly_evidence import (
    retrieve_assembly_evidence,
)
from ollama_staged_cycle_prototype.predictor import StagedPredictor

from .schemas import (
    StaticAssemblyFunction,
    StaticAssemblyReport,
    StaticFunctionAnalysis,
    StaticInstructionClassCount,
)


class StaticAssemblyPredictor:
    """Ask the LLM for static assembly only, then audit it in Python."""

    CONTROL_WORDS = {"if", "else", "for", "while", "switch", "do", "sizeof"}
    PROFILE = (
        "arm-none-eabi-gcc 11.4; -mcpu=cortex-m4 -mthumb -O0 "
        "-fno-inline -ffunction-sections -fdata-sections"
    )

    def __init__(self, repository_root: Path, client):
        self.root = repository_root.resolve()
        self.client = client
        config = self.root / "gemini_rag_cycle_prototype" / "config"
        timing = json.loads(
            (config / "cortex_m4_timing_profile.json").read_text(encoding="utf-8")
        )
        self.timing_cycles = {
            item["name"]: int(item["cycles_each"])
            for item in timing["instruction_classes"]
        }
        self.pattern_path = (
            self.root / "ollama_staged_cycle_prototype" / "knowledge"
            / "gcc_o0_assembly_patterns.json"
        )

    @staticmethod
    def _relevant_functions(source: str, target: str) -> dict[str, str]:
        target_body = extract_function(source, target)
        if target_body is None:
            raise ValueError(f"target function not found: {target}")
        helpers = extract_reachable_helpers(source, target)
        result = {target: target_body}
        for name in function_names(helpers):
            body = extract_function(helpers, name)
            if body:
                result[name] = body
        return result

    @staticmethod
    def _source_facts(source: str) -> str:
        lines = source.splitlines()
        facts: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if re.match(r"^\s*#\s*define\b", line):
                facts.append(line)
                while facts[-1].rstrip().endswith("\\") and index + 1 < len(lines):
                    index += 1
                    facts.append(lines[index])
            index += 1
        return "\n".join(facts) or "/* no object macros */"

    @staticmethod
    def _declaration_context(source: str) -> str:
        """Keep types/globals/prototypes, but remove every function body."""
        spans: list[tuple[int, int, str]] = []
        for name in function_names(source):
            body = extract_function(source, name)
            if not body:
                continue
            start = source.find(body)
            if start < 0:
                continue
            brace = body.find("{")
            signature = body[:brace].strip() + ";"
            spans.append((start, start + len(body), signature))
        context = source
        for start, end, replacement in sorted(spans, reverse=True):
            context = context[:start] + replacement + context[end:]
        context = re.sub(r"\n{3,}", "\n\n", context)
        return context.strip()

    @staticmethod
    def _format_evidence(records: list[dict]) -> str:
        chunks: list[str] = []
        for record in records:
            lines = [
                f"EXAMPLE {record['pattern']} tags={','.join(record.get('tags', []))}"
            ]
            for block in record.get("basic_blocks", []):
                lines.append(f"{block['id']}:")
                lines.extend(f"  {instruction}" for instruction in block["assembly"])
            chunks.append("\n".join(lines))
        return "\n\n".join(chunks) or "No matching example was selected."

    def _prompt(
        self,
        function_name: str,
        function_source: str,
        declarations: str,
        source_facts: str,
        evidence: str,
        audit_errors: list[str] | None = None,
        previous: StaticAssemblyFunction | None = None,
    ) -> str:
        repair = ""
        if audit_errors:
            repair = (
                "\nPREVIOUS ASSEMBLY FAILED THESE GENERAL AUDITS:\n- "
                + "\n- ".join(audit_errors)
                + "\nRegenerate the complete function; do not patch individual lines.\n"
            )
            if previous is not None:
                repair += (
                    "The previous output is shown only to identify the defect; do not "
                    "copy repeated or incomplete regions:\n"
                    + "\n".join(previous.assembly[:220])
                    + "\n"
                )
        return f"""You are performing exactly one compiler-emulation task.

TARGET PROFILE
{self.PROFILE}

OUTPUT SCOPE
Translate exactly the C function {function_name} into a plausible complete STATIC
Thumb-2 function body for the target profile. This is ordinary compiler output,
not an executed trace and not a timing estimate.

STRICT RULES
1. Emit every source branch arm, switch case and early-return route. Do not choose a runtime path.
2. Emit each loop body exactly once with labels, its condition and a backward branch. NEVER unroll a loop.
3. Keep function boundaries. Emit one `bl CalleeName` for every static direct-call site in this
   function, including call sites in mutually exclusive branch arms; never inline a callee body.
4. Include a plausible GCC -O0 prologue, stack/local accesses, address formation, body and epilogue.
5. Preserve the source operations. Do not omit calls, memory accesses, comparisons, MUL or DIV operations.
6. Produce assembly only for {function_name}. Do not repeat an instruction sequence to represent iterations.
7. Do not calculate cycles, paths, execution counts, statement IDs, CFG objects or instruction ledgers.
8. Use symbolic labels and symbols. Each assembly array item is exactly one label or instruction.
9. If exact code generation is genuinely unresolved, state the narrow uncertainty in `unresolved`; do not
   hide missing source behavior or manufacture hundreds of repeated instructions.
10. The `assembly` array has a HARD LIMIT of 320 items and normally should be much shorter. Never approach
    that limit by expanding iterations, branch executions, lookup-table contents or source array data.
11. Emit function-body instructions only. Refer to constants and global tables by symbol; do not emit their
    `.word`, `.byte`, initializer, literal-pool data or other translation-unit data in this response.
12. All branch instructions (b, beq, bne, bls, etc.) MUST target declared symbolic labels (e.g. `b loop_start`),
    NEVER numeric addresses or offset strings like `bls 10 <func+0x10>`.
13. Global or static arrays/tables (e.g. lookup tables) are DATA, never functions. NEVER invoke data arrays with `bl`.
    Form their address and load/store data.

Before returning JSON, silently audit that all source constructs are represented, every loop has a
symbolic back-edge, every direct call is a BL to a real function, and no data symbols are called with BL.

TRANSLATION-UNIT DECLARATIONS AND GLOBAL CONTEXT
{declarations}

OBJECT-LIKE MACROS
{source_facts}

FUNCTION TO TRANSLATE
{function_source}

REAL GCC 11.4 -O0 TRANSFORMATION EXAMPLES
These are shape examples, not code to concatenate or copy wholesale:
{evidence}
{repair}
Return JSON only with exactly these fields:
{{"function_name":"{function_name}","assembly":["label:","opcode operands"],"unresolved":[]}}
"""

    @staticmethod
    def _instruction_lines(assembly: list[str]) -> list[str]:
        result = []
        for line in assembly:
            clean = re.sub(r"@.*$", "", line).strip()
            if not clean or clean.endswith(":") or clean.startswith("."):
                continue
            result.append(clean)
        return result

    @staticmethod
    def _direct_callees(
        name: str, body: str, functions: dict[str, str]
    ) -> set[str]:
        return {
            candidate for candidate in functions
            if candidate != name and re.search(rf"\b{re.escape(candidate)}\s*\(", body)
        }

    @staticmethod
    def _has_backward_branch(assembly: list[str]) -> bool:
        labels = {
            line[:-1].strip(): index
            for index, line in enumerate(assembly)
            if line.strip().endswith(":")
        }
        for index, line in enumerate(assembly):
            clean = re.sub(r"@.*$", "", line).strip()
            match = re.match(
                r"^(b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?|cbz|cbnz)(?:\.[nw])?\s+(.+)$",
                clean, flags=re.I,
            )
            if not match:
                continue
            operands = [item.strip() for item in match.group(2).split(",")]
            target = operands[-1]
            if labels.get(target, index) < index:
                return True
        return False

    @staticmethod
    def _has_conditional_branch(instructions: list[str]) -> bool:
        return any(StagedPredictor._is_conditional_branch_instruction(line) for line in instructions)

    @staticmethod
    def _variable_operator_present(body: str, operator: str) -> bool:
        stripped = re.sub(r"/\*.*?\*/|//[^\n]*", " ", body, flags=re.S)
        escaped = re.escape(operator)
        pattern = rf"\b[A-Za-z_]\w*(?:\s*\[[^]]+\])?\s*{escaped}\s*[A-Za-z_]\w*"
        return bool(re.search(pattern, stripped))

    @staticmethod
    def _data_symbols(declarations: str) -> set[str]:
        """Extract global/static array and variable symbol names from declarations context."""
        symbols: set[str] = set()
        for line in declarations.splitlines():
            clean = re.sub(r"/\*.*?\*/|//.*$", "", line).strip()
            if not clean or clean.startswith("#"):
                continue
            # Match declarations like: static const uint8_t s_aes_sbox[256]; or uint8_t g_bench_sink8;
            matches = re.finditer(
                r"\b(?:const\s+|static\s+|volatile\s+|extern\s+|unsigned\s+|signed\s+|"
                r"[A-Za-z_]\w*_t|[A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*;",
                clean,
            )
            for m in matches:
                sym = m.group(1).strip()
                if sym and not sym.startswith(("int", "uint", "void", "char")):
                    symbols.add(sym.lower())
        return symbols

    @staticmethod
    def _allocated_stack_frame_size(instructions: list[str]) -> int | None:
        """Parse prologue stack allocation size (e.g. sub sp, #16)."""
        for inst in instructions[:10]:
            match = re.match(r"^\s*sub(?:s)?(?:\.w)?\s+sp,\s*(?:sp,\s*)?#?(\d+)\b", inst, flags=re.I)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _max_stack_offset(instructions: list[str]) -> int | None:
        """Find the maximum immediate offset used in stack accesses ([r7, #N] or [sp, #N])."""
        max_val = None
        for inst in instructions:
            for m in re.finditer(r"\[(?:r7|sp),\s*#?(\d+)\]", inst, flags=re.I):
                val = int(m.group(1))
                if max_val is None or val > max_val:
                    max_val = val
        return max_val

    def _audit(
        self,
        draft: StaticAssemblyFunction,
        expected_name: str,
        body: str,
        functions: dict[str, str],
        declarations: str = "",
    ) -> list[str]:
        errors: list[str] = []
        if draft.function_name != expected_name:
            errors.append(
                f"function_name is {draft.function_name!r}, expected {expected_name!r}"
            )
        instructions = self._instruction_lines(draft.assembly)
        if len(instructions) < 2:
            errors.append("assembly contains fewer than two instructions")
        if len(draft.assembly) >= 310:
            errors.append("assembly reached the output ceiling and is probably truncated")
        if StagedPredictor._has_repeated_instruction_ngram(instructions):
            errors.append("assembly contains a repeated 8-instruction sequence three times")

        # 1. Directives rejection (.word, .byte, etc. within assembly array)
        for line in draft.assembly:
            clean = re.sub(r"@.*$", "", line).strip()
            if re.match(r"^\.(?:word|byte|short|ascii|asciz|space|fill|zero)\b", clean, flags=re.I):
                errors.append(
                    f"assembly contains data directive {clean!r}; refer to global data by symbol, "
                    "do not emit literal-pool or data declarations in assembly"
                )
                break

        # 2. Branch targets must be defined symbolic labels (no numeric offsets or undefined targets)
        labels = {
            line[:-1].strip()
            for line in draft.assembly
            if line.strip().endswith(":")
        }
        for line in instructions:
            match = re.match(
                r"^(?:b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?|cbz|cbnz)(?:\.[nw])?\s+(.+)$",
                line, flags=re.I,
            )
            if match:
                operands = [item.strip() for item in match.group(1).split(",")]
                target = operands[-1]
                # Reject hex/numeric offset branch targets like "10 <func+0x10>" or bare numbers
                if re.match(r"^(?:0x[0-9a-f]+|\d+)\b", target, flags=re.I) or "<" in target:
                    errors.append(
                        f"branch target {target!r} is numeric or an offset; "
                        "all branch targets must be symbolic labels"
                    )
                    break
                elif target not in labels:
                    errors.append(
                        f"branch target {target!r} does not match any declared label in this function"
                    )
                    break

        # 3. Reject BL to data/array symbols
        data_symbols = self._data_symbols(declarations)
        lowered = [line.lower() for line in instructions]
        for line in lowered:
            bl_match = re.search(r"\bblx?\s+([A-Za-z_]\w*)\b", line)
            if bl_match:
                called = bl_match.group(1)
                if called in data_symbols:
                    errors.append(
                        f"instruction {line.strip()!r} attempts to call data symbol {called!r} with BL; "
                        "load its address instead of invoking it as a function"
                    )

        # 4. Callee call sites audit
        for callee in sorted(self._direct_callees(expected_name, body, functions)):
            expected_sites = len(re.findall(
                rf"\b{re.escape(callee)}\s*\(", body
            ))
            actual_sites = sum(
                bool(re.search(rf"\bblx?\s+{re.escape(callee.lower())}\b", line))
                for line in lowered
            )
            if actual_sites < expected_sites:
                errors.append(
                    f"source has {expected_sites} static call site(s) for {callee}, "
                    f"assembly has {actual_sites} BL instruction(s)"
                )

        # 5. Loops must have a backward branch
        if re.search(r"\b(?:for|while)\s*\(|\bdo\b", body):
            if not self._has_backward_branch(draft.assembly):
                errors.append("source contains a loop but assembly has no backward branch")

        # 6. Loop relational operator consistency (< vs <=)
        # In GCC -O0, for loops like for(i=0; i < N; ++i) compare i with N and use blt/blo or bne,
        # never bls/ble against N (which would execute N+1 iterations).
        strict_loop_matches = re.findall(
            r"\bfor\s*\(\s*(?:[A-Za-z_]\w*\s+)*([A-Za-z_]\w*)\s*=\s*\d+[uUlL]*\s*;\s*\1\s*<\s*(\d+)[uUlL]*\s*;",
            body,
        )
        for var_name, bound_str in strict_loop_matches:
            bound_val = int(bound_str)
            # Check if assembly compares with bound_val and branches with bls/ble
            for idx, inst in enumerate(instructions):
                cmp_match = re.search(rf"\bcmp(?:\.w)?\s+[rR]\d+,\s*#?{bound_val}\b", inst, flags=re.I)
                if cmp_match:
                    # Look ahead for immediate branch
                    for next_inst in instructions[idx + 1:idx + 3]:
                        if re.match(r"^\s*b(?:ls|le)(?:\.[nw])?\b", next_inst, flags=re.I):
                            errors.append(
                                f"loop condition is strictly '< {bound_val}', but assembly tests "
                                f"with <= ({next_inst.strip()}); use < comparison or test != bound"
                            )
                            break

        # 7. Stack frame allocation bounds check
        frame_size = self._allocated_stack_frame_size(instructions)
        if frame_size is not None:
            max_offset = self._max_stack_offset(instructions)
            if max_offset is not None and max_offset >= frame_size:
                errors.append(
                    f"stack access offset #{max_offset} exceeds allocated frame size #{frame_size}"
                )

        # 8. Control flow & operator audits
        if re.search(r"\b(?:if|switch)\s*\(|\?", body):
            if not self._has_conditional_branch(instructions):
                errors.append("source contains conditional control flow but assembly has no conditional branch")
        if self._variable_operator_present(body, "/") and not any(
            re.match(r"^(?:sdiv|udiv)\b", line) for line in lowered
        ):
            errors.append("source contains variable division but assembly has no SDIV/UDIV")
        if self._variable_operator_present(body, "*") and not any(
            re.match(r"^(?:mul|mla|mls|smull|umull|smlal|umlal)\b", line)
            for line in lowered
        ):
            errors.append("source contains variable multiplication but assembly has no multiply instruction")
        if not any(
            re.match(r"^(?:bx\s+lr|pop\s+.*\bpc\b)", line) for line in lowered
        ):
            errors.append("assembly has no recognizable function return")
        return errors

    def _analyze(
        self, draft: StaticAssemblyFunction, errors: list[str]
    ) -> StaticFunctionAnalysis:
        instructions = self._instruction_lines(draft.assembly)
        counts: Counter[str] = Counter()
        for instruction in instructions:
            counts.update(StagedPredictor._classify_instruction(instruction))
        class_rows = []
        for name in sorted(counts):
            cycles = self.timing_cycles[name]
            class_rows.append(StaticInstructionClassCount(
                instruction_class=name,
                static_count=counts[name],
                cycles_each=cycles,
                static_cycle_sum=counts[name] * cycles,
            ))
        return StaticFunctionAnalysis(
            function_name=draft.function_name,
            assembly=draft.assembly,
            instruction_count=len(instructions),
            instruction_classes=class_rows,
            static_core_cycle_sum=sum(row.static_cycle_sum for row in class_rows),
            unresolved=draft.unresolved,
            validation_errors=errors,
        )

    def predict(
        self, source: str, target: str
    ) -> tuple[StaticAssemblyReport, list[tuple[str, str]]]:
        functions = self._relevant_functions(source, target)
        declarations = self._declaration_context(source)
        source_facts = self._source_facts(source)
        semantic_attempts = max(1, int(os.getenv("OLLAMA_V2_SEMANTIC_ATTEMPTS", "2")))
        analyses: list[StaticFunctionAnalysis] = []
        raw_outputs: list[tuple[str, str]] = []

        for name, body in functions.items():
            evidence = self._format_evidence(retrieve_assembly_evidence(
                source, self.pattern_path, function_name=name, limit=5,
            ))
            errors: list[str] = []
            previous: StaticAssemblyFunction | None = None
            draft: StaticAssemblyFunction | None = None
            for attempt in range(semantic_attempts):
                prompt = self._prompt(
                    name, body, declarations, source_facts, evidence,
                    audit_errors=errors or None,
                    previous=previous,
                )
                result, raw = self.client.predict(
                    prompt, response_schema=StaticAssemblyFunction
                )
                draft = result
                raw_outputs.append((f"{name}.attempt-{attempt + 1}", raw))
                errors = self._audit(draft, name, body, functions, declarations=declarations)
                if not errors:
                    break
                previous = draft
            assert draft is not None
            analyses.append(self._analyze(draft, errors))

        valid = all(not function.validation_errors for function in analyses)
        warnings = [
            "Static core-cycle sums execute every emitted instruction once; they are diagnostics, not task execution-time estimates.",
            "Dynamic loop counts, branch paths, call multiplicities and PFlash effects are intentionally not evaluated in V2 phase 1.",
        ]
        if not valid:
            warnings.append(
                "At least one generated function failed semantic assembly audits; no execution-cycle estimate is published."
            )
        return StaticAssemblyReport(
            analysis_status="SUPPORTED" if valid else "VALIDATION_REQUIRED",
            model=self.client.model,
            target_function=target,
            compiler_profile=self.PROFILE,
            functions=analyses,
            warnings=warnings,
        ), raw_outputs
