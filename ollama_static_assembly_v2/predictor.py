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
    SemanticAssemblyReview,
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

    @staticmethod
    def _signature_contracts(functions: dict[str, str]) -> str:
        """Render compact source-derived AAPCS entry contracts."""
        rows: list[str] = []
        for name, body in functions.items():
            signature = " ".join(body.split("{", 1)[0].split())
            match = re.search(rf"\b{re.escape(name)}\s*\((.*)\)\s*$", signature)
            params = [] if not match else [
                item.strip() for item in match.group(1).split(",")
                if item.strip() and item.strip() != "void"
            ]
            incoming = ", ".join(
                f"r{index} <- {param}" for index, param in enumerate(params[:4])
            ) or "no incoming argument registers"
            if len(params) > 4:
                incoming += ", remaining arguments follow AAPCS stack rules"
            return_type = signature.split(name, 1)[0].strip()
            returned = "void" if re.search(r"\bvoid\s*$", return_type) else "r0"
            rows.append(
                f"{name}: `{signature}`; entry {incoming}; scalar/pointer return: {returned}"
            )
        return "\n".join(rows) or "(none)"

    @staticmethod
    def _split_call_arguments(arguments: str) -> list[str]:
        parts: list[str] = []
        start = 0
        depth = 0
        for index, char in enumerate(arguments):
            if char in "([{" :
                depth += 1
            elif char in ")]}" :
                depth = max(0, depth - 1)
            elif char == "," and depth == 0:
                parts.append(arguments[start:index].strip())
                start = index + 1
        tail = arguments[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    @classmethod
    def _call_site_contracts(
        cls, function_name: str, body: str, functions: dict[str, str]
    ) -> str:
        """Render exact source call expressions and their AAPCS argument registers."""
        sites: list[tuple[int, str]] = []
        for callee in sorted(cls._direct_callees(function_name, body, functions)):
            for match in re.finditer(rf"\b{re.escape(callee)}\s*\(", body):
                open_index = body.find("(", match.start())
                depth = 0
                close_index = None
                for index in range(open_index, len(body)):
                    if body[index] == "(":
                        depth += 1
                    elif body[index] == ")":
                        depth -= 1
                        if depth == 0:
                            close_index = index
                            break
                if close_index is None:
                    continue
                arguments = cls._split_call_arguments(body[open_index + 1:close_index])
                bindings = ", ".join(
                    f"r{index} <- `{argument}`"
                    for index, argument in enumerate(arguments[:4])
                ) or "no argument registers"
                if len(arguments) > 4:
                    bindings += ", remaining arguments follow AAPCS stack rules"
                sites.append((match.start(), f"before `bl {callee}`: {bindings}"))
        return "\n".join(row for _, row in sorted(sites)) or "(no direct helper calls)"

    def _prompt(
        self,
        function_name: str,
        function_source: str,
        declarations: str,
        source_facts: str,
        callable_symbols: set[str],
        data_symbols: set[str],
        signature_contracts: str,
        call_site_contracts: str,
        data_type_contracts: str,
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
12. Respect symbol kinds exactly. Symbols listed as DATA are addressable objects and must never be direct
    `bl`/`blx` targets. Only symbols listed as CALLABLE may be named direct-call targets.
13. All branch instructions (b, beq, bne, bls, etc.) MUST target declared symbolic labels (e.g. `b loop_start`),
    NEVER numeric addresses or offset strings like `bls 10 <func+0x10>`.
14. Global or static arrays/tables (e.g. lookup tables) are DATA, never functions. NEVER invoke data arrays with `bl`.
    A subscripted DATA expression such as `table[index]` is a memory access, not a function call. Form the
    table address, calculate the indexed element address, and load or store the element using its C width.
    Never emit `bl` or `blx` to implement a DATA lookup.
15. Follow the C function signature and the Arm procedure-call convention. Do not invent incoming argument
    values for a no-argument function. A `void name(void)` function must obtain source globals/statics through
    their DATA symbols. Before a real helper call, place its source arguments in `r0`-`r3` as required; consume
    its scalar return value from `r0`.
16. Preserve the declared C access width and signedness. Use byte loads/stores for 8-bit objects, halfword
    loads/stores for 16-bit objects, and word loads/stores for 32-bit objects. Use signed loads or explicit
    extension when the C object is signed. Pointer/address loads do not change the pointee's access width.
17. Make the stack frame self-consistent. Every local stack access must lie within the byte count reserved by
    the prologue, with enough aligned space for all locals and spills. Do not emit an `[r7, #offset]` local
    access beyond the allocated frame, and restore exactly that frame in the epilogue.
18. Preserve loop initialization, comparison operator, bound and update exactly. In particular, `< N` must
    not become `<= N`, and `<= N` must not become `< N`. Emit the initial condition check when required by
    the C loop form, one body, one update and the correct symbolic back-edge.
19. Keep register and memory dataflow valid across the whole function. Every consumed value must come from
    a preceding definition, load or legitimate incoming argument. Treat `r0`-`r3` and `r12` as call-clobbered;
    save a live value before `bl` when the source still needs it afterward. Store results through the intended
    destination address, never through a register that currently contains an ordinary scalar value.
20. Preserve source DATA dependencies explicitly. Every global or static DATA symbol referenced by this C
    function must still be named in the symbolic assembly. Never satisfy another rule by silently omitting a
    DATA read or write; form or load the symbol's address and perform the source access.

Before returning JSON, silently audit that all source constructs are represented, every loop has a
symbolic back-edge, every direct call is a BL to a real function, no data symbols are called with BL,
every source DATA symbol remains referenced, all memory widths match their C objects, and every stack
offset is inside the allocated frame.

TRANSLATION-UNIT DECLARATIONS AND GLOBAL CONTEXT
{declarations}

OBJECT-LIKE MACROS
{source_facts}

SYMBOL KIND CONTRACT
CALLABLE: {", ".join(sorted(callable_symbols)) or "(none)"}
DATA: {", ".join(sorted(data_symbols)) or "(none)"}

FUNCTION SIGNATURE AND ABI CONTRACT
These bindings come directly from the C signatures and call expressions; preserve them exactly.
{signature_contracts}

CALL-SITE ARGUMENT CONTRACT FOR {function_name}
{call_site_contracts}

DATA TYPE AND ACCESS-WIDTH CONTRACT
{data_type_contracts}

FUNCTION TO TRANSLATE
{function_source}

REAL GCC 11.4 -O0 TRANSFORMATION EXAMPLES
These are shape examples, not code to concatenate or copy wholesale:
{evidence}
{repair}
        Return JSON only with exactly these fields:
        {{"function_name":"{function_name}","assembly":["label:","opcode operands"],"unresolved":[]}}
        """

    def _review_prompt(
        self,
        function_name: str,
        function_source: str,
        assembly: list[str],
        source_facts: str,
        signature_contracts: str,
        call_site_contracts: str,
        data_type_contracts: str,
    ) -> str:
        return f"""Perform an independent SEMANTIC REVIEW of one proposed Thumb-2 function.

Do not generate replacement assembly, do not calculate cycles, and do not demand an
exact GCC instruction layout. Compare only the C semantics with the proposed assembly.

Check concrete correctness defects only:
- macro constants versus addressable globals, locals and parameters;
- address values versus loaded scalar values and the destination of every source assignment;
- AAPCS argument placement at every call, including fifth and later stack arguments;
- live values across call-clobbered r0-r3/r12;
- load/store width and signedness;
- local stack lifetime, extent and non-overlapping object layout;
- pointer/scalar register dataflow;
- exact loop initialization, bounds, updates and absence of unrolling;
- preservation of each source read, write, call and return value.

Do not report stylistic differences, register-allocation choices, harmless redundant
instructions, or uncertain compiler preferences. A FAIL error must name a specific C
operation and the conflicting assembly behavior. Report at most 12 errors.

OBJECT-LIKE MACROS
{source_facts}

FUNCTION SIGNATURE AND ABI CONTRACT
{signature_contracts}

CALL-SITE ARGUMENT CONTRACT FOR {function_name}
{call_site_contracts}

DATA TYPE AND ACCESS-WIDTH CONTRACT
{data_type_contracts}

C FUNCTION
{function_source}

PROPOSED ASSEMBLY
{chr(10).join(assembly)}

Return JSON only with exactly these fields:
{{"function_name":"{function_name}","verdict":"PASS","errors":[]}}
or
{{"function_name":"{function_name}","verdict":"FAIL","errors":["concrete semantic defect"]}}
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
    def _has_variable_multiplication(body: str) -> bool:
        """Detect value multiplication without confusing pointer declarators/dereferences."""
        stripped = re.sub(r"/\*.*?\*/|//[^\n]*", " ", body, flags=re.S)
        if "{" in stripped:
            stripped = stripped.split("{", 1)[1]
        operand = r"[A-Za-z_]\w*(?:\s*\[[^\]]+\])*"
        type_words = {
            "char", "short", "int", "long", "float", "double", "signed",
            "unsigned", "const", "volatile", "void", "struct", "union", "enum",
        }
        for match in re.finditer(rf"(?P<left>{operand})\s*\*\s*(?P<right>{operand}|\d+[uUlL]*)", stripped):
            left = re.match(r"[A-Za-z_]\w*", match.group("left"))
            if left is None:
                continue
            token = left.group(0)
            if token in type_words or token.endswith("_t"):
                continue
            return True
        return False

    @staticmethod
    def _clean_data_declarations(declarations: str) -> str:
        clean = re.sub(r"/\*.*?\*/|//[^\n]*", " ", declarations, flags=re.S)
        # Declaration context also contains function prototypes. Remove them before
        # scanning objects so parameter names are never classified as DATA.
        clean = re.sub(
            r"\b(?:(?:static|extern|inline|const|volatile|signed|unsigned|long|short)\s+)*"
            r"(?:u?int(?:8|16|32|64)_t|void|char|short|int|long|float|double|"
            r"[A-Za-z_]\w*)\s+\**\s*[A-Za-z_]\w*\s*\([^;{}]*\)\s*;",
            " ", clean,
        )
        # If malformed/overlapping prototype extraction left a bare parameter
        # list behind, remove its contents so parameter declarations cannot be
        # mistaken for translation-unit objects.
        clean = re.sub(r"\([^(){};]*\)", " ", clean)
        return clean

    @classmethod
    def _data_symbols(cls, declarations: str) -> set[str]:
        """Extract translation-unit data objects, including initialized arrays."""
        clean = cls._clean_data_declarations(declarations)
        pattern = re.compile(
            r"\b(?:(?:static|const|volatile|extern|register)\s+)*"
            r"(?:u?int(?:8|16|32|64)_t|char|short|int|long|float|double|"
            r"[A-Za-z_]\w*_t)\s+"
            r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)*"
            r"(?=\s*(?:=|;|,))"
        )
        return {match.group(1).lower() for match in pattern.finditer(clean)}

    @classmethod
    def _data_type_contracts(cls, declarations: str) -> str:
        """Render source-derived types and array shapes for global/static objects."""
        clean = cls._clean_data_declarations(declarations)
        pattern = re.compile(
            r"\b((?:(?:static|const|volatile|extern|register)\s+)*"
            r"(?:u?int(?:8|16|32|64)_t|char|short|int|long|float|double|"
            r"[A-Za-z_]\w*_t))\s+"
            r"([A-Za-z_]\w*)\s*((?:\[[^\]]*\]\s*)*)"
            r"(?=\s*(?:=|;|,))"
        )
        contracts = {
            match.group(2).lower(): (
                f"{match.group(2)}: {' '.join(match.group(1).split())}"
                f"{''.join(match.group(3).split())}"
            )
            for match in pattern.finditer(clean)
        }
        return "\n".join(contracts[name] for name in sorted(contracts)) or "(none)"

    @staticmethod
    def _allocated_stack_frame_size(instructions: list[str]) -> int | None:
        """Parse prologue stack allocation size (e.g. sub sp, #16)."""
        for inst in instructions[:10]:
            match = re.match(r"^\s*sub(?:s)?(?:\.w)?\s+sp,\s*(?:sp,\s*)?#?(\d+)\b", inst, flags=re.I)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _max_stack_extent(instructions: list[str]) -> tuple[int, int, str] | None:
        """Return the stack access requiring the largest allocated byte extent."""
        widest: tuple[int, int, str] | None = None
        for inst in instructions:
            opcode_match = re.match(r"^\s*(ldrb|strb|ldrh|strh|ldrd|strd|ldr|str)(?:\.[nw])?\b", inst, flags=re.I)
            if not opcode_match:
                continue
            opcode = opcode_match.group(1).lower()
            width = 1 if opcode.endswith("b") else 2 if opcode.endswith("h") else 8 if opcode.endswith("d") else 4
            for m in re.finditer(r"\[(?:r7|sp),\s*#?(\d+)\]", inst, flags=re.I):
                offset = int(m.group(1))
                extent = offset + width
                if widest is None or extent > widest[0] + widest[1]:
                    widest = (offset, width, inst)
        return widest

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

        # 4. A source-level global/static data dependency must not disappear.
        source_identifiers = {
            match.group(0).lower()
            for match in re.finditer(r"\b[A-Za-z_]\w*\b", body)
        }
        required_data_symbols = source_identifiers & data_symbols
        assembly_identifiers = {
            match.group(0).lower()
            for line in instructions
            for match in re.finditer(r"\b[A-Za-z_]\w*\b", line)
        }
        for symbol in sorted(required_data_symbols - assembly_identifiers):
            errors.append(
                f"source references DATA symbol {symbol!r}, but assembly never names it; "
                "do not omit the access: form or load that symbol's address and preserve "
                "the source read/write"
            )

        # 5. Callee call sites audit
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

        # 6. Loops must have a backward branch
        if re.search(r"\b(?:for|while)\s*\(|\bdo\b", body):
            if not self._has_backward_branch(draft.assembly):
                errors.append("source contains a loop but assembly has no backward branch")

        # 7. Loop relational operator consistency (< vs <=)
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

        # 8. Stack frame allocation bounds check
        frame_size = self._allocated_stack_frame_size(instructions)
        if frame_size is not None:
            stack_extent = self._max_stack_extent(instructions)
            if stack_extent is not None:
                offset, width, instruction = stack_extent
                required_size = offset + width
            else:
                required_size = 0
            if stack_extent is not None and required_size > frame_size:
                errors.append(
                    f"stack access {instruction!r} at offset #{offset} with width {width} "
                    f"requires {required_size} bytes and exceeds allocated frame size #{frame_size}; "
                    "increase the aligned frame or correct the local layout"
                )

        # 9. Control flow & operator audits
        if re.search(r"\b(?:if|switch)\s*\(|\?", body):
            if not self._has_conditional_branch(instructions):
                errors.append("source contains conditional control flow but assembly has no conditional branch")
        if self._variable_operator_present(body, "/") and not any(
            re.match(r"^(?:sdiv|udiv)\b", line) for line in lowered
        ):
            errors.append("source contains variable division but assembly has no SDIV/UDIV")
        if self._has_variable_multiplication(body) and not any(
            re.match(r"^(?:muls?|mla|mls|smull|umull|smlal|umlal)(?:\.[nw])?\b", line)
            for line in lowered
        ):
            errors.append("source contains variable multiplication but assembly has no multiply instruction")
        if not any(
            re.match(r"^(?:bx\s+lr|pop\s+.*\bpc\b)", line) for line in lowered
        ):
            errors.append("assembly has no recognizable function return")
        return list(dict.fromkeys(errors))

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
        callable_symbols = set(function_names(source))
        data_symbols = self._data_symbols(declarations)
        signature_contracts = self._signature_contracts(functions)
        data_type_contracts = self._data_type_contracts(declarations)
        semantic_attempts = max(1, int(os.getenv("OLLAMA_V2_SEMANTIC_ATTEMPTS", "2")))
        analyses: list[StaticFunctionAnalysis] = []
        raw_outputs: list[tuple[str, str]] = []

        for name, body in functions.items():
            call_site_contracts = self._call_site_contracts(name, body, functions)
            evidence = self._format_evidence(retrieve_assembly_evidence(
                source, self.pattern_path, function_name=name, limit=5,
            ))
            errors: list[str] = []
            previous: StaticAssemblyFunction | None = None
            draft: StaticAssemblyFunction | None = None
            for attempt in range(semantic_attempts):
                prompt = self._prompt(
                    name, body, declarations, source_facts,
                    callable_symbols, data_symbols,
                    signature_contracts, call_site_contracts, data_type_contracts,
                    evidence,
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
                    review, review_raw = self.client.predict(
                        self._review_prompt(
                            name, body, draft.assembly, source_facts,
                            signature_contracts, call_site_contracts,
                            data_type_contracts,
                        ),
                        response_schema=SemanticAssemblyReview,
                    )
                    raw_outputs.append((f"{name}.review-{attempt + 1}", review_raw))
                    if review.function_name != name:
                        errors = [
                            f"semantic reviewer returned function_name {review.function_name!r}, "
                            f"expected {name!r}"
                        ]
                    elif review.verdict == "FAIL":
                        errors = [f"semantic reviewer: {error}" for error in review.errors]
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
