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

Before returning JSON, silently audit that all source constructs are represented, every loop has a
back-edge, every direct call is a BL, and no long instruction sequence is repeated verbatim.

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

    def _audit(
        self,
        draft: StaticAssemblyFunction,
        expected_name: str,
        body: str,
        functions: dict[str, str],
    ) -> list[str]:
        errors: list[str] = []
        if draft.function_name != expected_name:
            errors.append(
                f"function_name is {draft.function_name!r}, expected {expected_name!r}"
            )
        instructions = self._instruction_lines(draft.assembly)
        if len(instructions) < 2:
            errors.append("assembly contains fewer than two instructions")
        if len(draft.assembly) >= 590:
            errors.append("assembly reached the output ceiling and is probably truncated")
        if StagedPredictor._has_repeated_instruction_ngram(instructions):
            errors.append("assembly contains a repeated 8-instruction sequence three times")

        lowered = [line.lower() for line in instructions]
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

        if re.search(r"\b(?:for|while)\s*\(|\bdo\b", body):
            if not self._has_backward_branch(draft.assembly):
                errors.append("source contains a loop but assembly has no backward branch")
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
                errors = self._audit(draft, name, body, functions)
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
