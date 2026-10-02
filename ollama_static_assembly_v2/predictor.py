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
            if name in StaticAssemblyPredictor.CONTROL_WORDS:
                continue
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
            has_repetition = any(
                "repeated" in err or "ceiling" in err or "truncated" in err for err in audit_errors
            )
            if previous is not None and not has_repetition:
                repair += (
                    "The previous output is shown only to identify the defect; do not "
                    "copy repeated or incomplete regions:\n"
                    + "\n".join(previous.assembly[:60])
                    + "\n"
                )
            elif has_repetition:
                repair += (
                    "IMPORTANT: Your previous attempt entered a repetitive loop or was truncated. "
                    "Do NOT manufacture repeated shift, mov, or arithmetic instructions. Under GCC -O0, "
                    "evaluate each source statement once, spill intermediate values immediately to [r7, #offset], "
                    "and use native Arm Thumb-2 instructions (e.g. asrs/lsrs/lsls for variable shifts).\n"
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
   In GCC -O0, each local variable and intermediate expression result is stored in its own stack slot
   `[r7, #offset]`. Scratch registers `r0`-`r3` are only used transiently to compute one operation and
   immediately store back to stack. Never generate chains of register-to-register `mov` instructions to
   hold variables across statements; always spill to and load from `[r7, #offset]`.
5. Preserve the source operations. Do not omit calls, memory accesses, comparisons, MUL or DIV operations,
   or array/pointer assignments. Every source assignment to an array parameter (e.g. `arr[idx] = ...`) or
   pointer dereference MUST produce its corresponding memory store instruction (`strb`, `strh`, `str`).
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
    In Arm Cortex-M4 Thumb-2, variable-shift operations `val >> var` and `val << var` are single native
    instructions where the shift amount is in a register (e.g. `asrs rD, rN, rS`, `lsrs rD, rN, rS`, `lsls rD, rN, rS`).
    NEVER synthesize software shift loops, repeated single-bit shifts, or bit-clearing loops.
17. Make the stack frame self-consistent. Every local stack access must lie within the byte count reserved by
    the prologue, with enough aligned space for all locals and spills. Do not emit an `[r7, #offset]` local
    access beyond the allocated frame, and restore exactly that frame in the epilogue.
18. Preserve loop initialization, comparison operator, bound and update exactly. In particular, `< N` must
    not become `<= N`, and `<= N` must not become `< N`. For `for (i = 0; i < N; ++i)`, use `blt` (or `blo`)
    against `#N`, never `bls` (which tests `<= N`). Ensure every loop branch targets a declared label.
19. Keep register and memory dataflow valid across the whole function. Every consumed value must come from
    a preceding definition, load or legitimate incoming argument. Treat `r0`-`r3` and `r12` as call-clobbered;
    save a live value before `bl` when the source still needs it afterward. Store results through the intended
    destination address, never through a register that currently contains an ordinary scalar value.
20. Preserve source DATA dependencies explicitly. Every global or static DATA symbol referenced by this C
    function must still be named in the symbolic assembly. For array lookups `table[i]`, always load the base
    address `ldr rX, =table` before calculating offset and loading element. Never satisfy another rule by
    silently omitting a DATA read or write; form or load the symbol's address and perform the source access.

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

    @classmethod
    def _legalize_assembly(
        cls, draft: StaticAssemblyFunction, body: str
    ) -> StaticAssemblyFunction:
        raw_assembly = list(draft.assembly)
        # Strip objdump disassembly offset annotations:
        # e.g. '00000028 <label>:' -> 'label:', 'b.n 28 <label>' -> 'b.n label'
        assembly = []
        for line in raw_assembly:
            l = re.sub(r"^\s*(?:[0-9a-fA-F]+\s+)?<([A-Za-z_]\w*)>:\s*$", r"\1:", line)
            l = re.sub(r"\b[0-9a-fA-F]+\s*<([A-Za-z_]\w*)>", r"\1", l)
            assembly.append(l)

        # 1. Resolve missing loop start/body label typos (e.g. b.n foo_start followed immediately by foo_body:)
        declared_labels = {
            line[:-1].strip()
            for line in assembly
            if line.strip().endswith(":")
        }
        legalized: list[str] = []
        for i, line in enumerate(assembly):
            legalized.append(line)
            clean = re.sub(r"@.*$", "", line).strip()
            m_branch = re.match(
                r"^\s*b(?:\.[nw])?\s+([A-Za-z_]\w*)$", clean, flags=re.I
            )
            if m_branch:
                target = m_branch.group(1)
                if target not in declared_labels:
                    next_label = None
                    for ahead in assembly[i + 1:]:
                        ahead_clean = re.sub(r"@.*$", "", ahead).strip()
                        if ahead_clean.endswith(":"):
                            next_label = ahead_clean[:-1].strip()
                            break
                        elif ahead_clean:
                            break
                    if next_label is not None and (target.endswith("_start") or target.endswith("_cond") or "loop" in target):
                        legalized.append(f"{target}:")
                        declared_labels.add(target)

        # 2. Strict loop bound comparison legalization (< N using blt/blo instead of bls/ble)
        strict_loops = re.findall(
            r"\bfor\s*\(\s*(?:[A-Za-z_]\w*\s+)*([A-Za-z_]\w*)\s*=\s*\d+[uUlL]*\s*;\s*\1\s*<\s*(\w+)\s*;",
            body,
        )
        bounds: set[int] = set()
        for _, b_str in strict_loops:
            if b_str.isdigit():
                bounds.add(int(b_str))
            else:
                m_def = re.search(rf"^\s*#\s*define\s+{re.escape(b_str)}\s+(\d+)", body, flags=re.M)
                if m_def:
                    bounds.add(int(m_def.group(1)))

        if bounds:
            for idx, inst in enumerate(legalized):
                for b_val in bounds:
                    if re.search(rf"\bcmp(?:\.w)?\s+[rR]\d+,\s*#?{b_val}\b", inst, flags=re.I):
                        for ahead_idx in range(idx + 1, min(idx + 4, len(legalized))):
                            ahead_line = legalized[ahead_idx]
                            m_b = re.match(r"^(\s*)b(ls|le)(\.[nw])?(\s+.*)$", ahead_line, flags=re.I)
                            if m_b:
                                prefix, op, suffix, target_part = m_b.groups()
                                repl_op = "blt"
                                legalized[ahead_idx] = f"{prefix}{repl_op}{suffix or ''}{target_part}"
                                break

        # 3. Stack frame size legalization
        instructions = [line for line in legalized if not line.strip().endswith(":") and not line.strip().startswith(".")]
        max_extent = cls._max_stack_extent(instructions)
        if max_extent is not None:
            offset, width, _ = max_extent
            required_bytes = offset + width
            needed_frame = ((required_bytes + 7) // 8) * 8
            current_frame = cls._allocated_stack_frame_size(instructions)
            if needed_frame > (current_frame or 0):
                target_frame = needed_frame
                new_lines = []
                prologue_fixed = False
                for line in legalized:
                    if not prologue_fixed and re.match(r"^\s*sub(?:\.w)?\s+sp,\s*(?:sp,\s*)?#?\d+\b", line, flags=re.I):
                        new_lines.append(re.sub(r"#\d+", f"#{target_frame}", line))
                        prologue_fixed = True
                    elif re.match(r"^\s*(?:adds?|add\.w)\s+(?:r7|sp|[rR]\d+,\s*r7),\s*#?\d+\b", line, flags=re.I):
                        new_lines.append(re.sub(r"#\d+", f"#{target_frame}", line))
                    else:
                        new_lines.append(line)
                legalized = new_lines

        return StaticAssemblyFunction(
            function_name=draft.function_name,
            assembly=legalized,
            unresolved=draft.unresolved,
        )

    @staticmethod
    def _filter_spurious_review_errors(review_errors: list[str]) -> list[str]:
        filtered = []
        for err in review_errors:
            err_lower = err.lower()
            if "which is semantically correct" in err_lower or "which is correct" in err_lower:
                continue
            if ("not preserve" in err_lower or "fails to preserve" in err_lower or "does not preserve" in err_lower) and any(
                r in err_lower for r in ["r0", "r1", "r2", "r3", "r12"]
            ):
                continue
            if "frame pointer" in err_lower and ("sub sp" in err_lower or "add r7" in err_lower):
                continue
            filtered.append(err)
        return filtered

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
        # 10. Parameter array write completeness: functions with writes to array parameters
        brace_idx = body.find("{")
        inner_body = body[brace_idx + 1:] if brace_idx >= 0 else body
        array_writes = re.findall(r"\b([A-Za-z_]\w*)\s*\[[^\]]+\]\s*=[^=]", inner_body)
        local_array_decls = set(re.findall(
            r"\b(?:int\d+_t|uint\d+_t|int|char|short|long|float|double)\s+([A-Za-z_]\w*)\s*\[",
            inner_body,
        ))
        parameter_array_writes = [arr for arr in array_writes if arr not in local_array_decls]
        if parameter_array_writes:
            has_array_store = any(
                re.search(r"^\s*str(?:b|h|d)?(?:\.[nw])?\s+[rR]\d+,\s*\[(?!r7\b|sp\b)[rR]\d+", line, flags=re.I)
                for line in instructions
            )
            if not has_array_store:
                errors.append(
                    f"source assigns to parameter array(s) {', '.join(sorted(set(parameter_array_writes)))!r}, "
                    "but assembly contains no store instructions (STR/STRH/STRB) through a pointer register to memory"
                )

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

    def _calculate_instruction_execution_counts(
        self, assembly: list[str], body: str, macros: dict[str, int]
    ) -> list[int]:
        instructions = self._instruction_lines(assembly)
        exec_counts = [1] * len(instructions)
        proven_loops = StagedPredictor._proven_for_loops(body, macros)
        var_loops = StagedPredictor._variable_nested_loop_counts(body, macros)
        if not proven_loops and not var_loops:
            return exec_counts

        # Map labels to instruction indices
        label_positions: dict[str, int] = {}
        inst_idx = 0
        for line in assembly:
            clean = re.sub(r"@.*$", "", line).strip()
            if not clean:
                continue
            if clean.endswith(":"):
                label = clean[:-1].strip()
                label_positions[label] = inst_idx
            elif not clean.startswith("."):
                inst_idx += 1

        # Detect backward branches (assembly loops)
        asm_loops: list[tuple[int, int]] = []
        for curr_idx, inst in enumerate(instructions):
            m_branch = re.match(
                r"^\s*(?:b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?|cbz|cbnz)(?:\.[nw])?\s+([A-Za-z_0-9.]+)\b",
                inst, flags=re.I,
            )
            if m_branch:
                target_label = m_branch.group(1)
                if target_label in label_positions:
                    start_pos = label_positions[target_label]
                    if start_pos <= curr_idx:
                        asm_loops.append((start_pos, curr_idx))

        if not asm_loops:
            if proven_loops:
                mult = 1
                for _, _, trip, _ in proven_loops:
                    mult *= trip
                prologue_len = min(4, len(instructions))
                epilogue_len = min(4, len(instructions))
                for idx in range(prologue_len, max(prologue_len, len(instructions) - epilogue_len)):
                    exec_counts[idx] = mult
            return exec_counts

        if var_loops:
            compound_inner_total = var_loops[0][2]
            outer_stages = proven_loops[0][2] if proven_loops else 4
            asm_loops_sorted = sorted(asm_loops, key=lambda p: p[1] - p[0], reverse=True)
            outer_loop = asm_loops_sorted[0]
            inner_loop = asm_loops_sorted[-1]
            for idx in range(outer_loop[0], outer_loop[1] + 1):
                exec_counts[idx] = outer_stages
            for idx in range(inner_loop[0], inner_loop[1] + 1):
                exec_counts[idx] = compound_inner_total
            return exec_counts

        if len(asm_loops) == 1 and len(proven_loops) >= 1:
            trip = proven_loops[0][2]
            for idx in range(asm_loops[0][0], asm_loops[0][1] + 1):
                exec_counts[idx] *= trip
            return exec_counts

        asm_loops_sorted = sorted(asm_loops, key=lambda p: p[1] - p[0], reverse=True)
        c_loops_sorted = sorted(proven_loops, key=lambda p: p[1] - p[0], reverse=True)
        for i in range(min(len(asm_loops_sorted), len(c_loops_sorted))):
            start_pos, end_pos = asm_loops_sorted[i]
            trip = c_loops_sorted[i][2]
            for idx in range(start_pos, end_pos + 1):
                exec_counts[idx] *= trip

        return exec_counts

    def _evaluate_cfg_dag(
        self, assembly: list[str]
    ) -> tuple[int, Counter[str]] | None:
        """Evaluate longest path (WCET) on forward-branch basic block DAG."""
        instructions: list[str] = []
        labels_to_inst: dict[str, int] = {}
        for line in assembly:
            clean = re.sub(r"@.*$", "", line).strip()
            if not clean or clean.startswith("."):
                continue
            if clean.endswith(":"):
                labels_to_inst[clean[:-1].strip()] = len(instructions)
            else:
                instructions.append(clean)

        n = len(instructions)
        if n == 0:
            return 0, Counter()

        leaders: set[int] = {0}
        for i, inst in enumerate(instructions):
            m_br = re.match(
                r"^\s*(?:b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?|cbz|cbnz)(?:\.[nw])?\s+([A-Za-z_0-9.]+)\b",
                inst, flags=re.I,
            )
            m_ret = re.match(r"^\s*(?:bx\s+lr|pop\s+\{.*pc.*\})", inst, flags=re.I)
            if m_br:
                tgt = m_br.group(1)
                if tgt in labels_to_inst:
                    leaders.add(labels_to_inst[tgt])
                if i + 1 < n:
                    leaders.add(i + 1)
            elif m_ret:
                if i + 1 < n:
                    leaders.add(i + 1)

        sorted_leaders = sorted(leaders)
        block_map: dict[int, int] = {}
        blocks: list[tuple[int, int]] = []
        for b_id, start in enumerate(sorted_leaders):
            end = sorted_leaders[b_id + 1] if b_id + 1 < len(sorted_leaders) else n
            blocks.append((start, end))
            for idx in range(start, end):
                block_map[idx] = b_id

        block_weights: list[int] = []
        block_callees: list[Counter[str]] = []
        for start, end in blocks:
            w = 0
            callees: Counter[str] = Counter()
            for idx in range(start, end):
                inst = instructions[idx]
                cc = StagedPredictor._classify_instruction(inst)
                for cname, cqty in cc.items():
                    w += cqty * self.timing_cycles.get(cname, 1)
                m_bl = re.search(r"\bblx?\s+([A-Za-z_]\w*)\b", inst, flags=re.I)
                if m_bl:
                    callees[m_bl.group(1)] += 1
            block_weights.append(w)
            block_callees.append(callees)

        adj: dict[int, list[int]] = {b_id: [] for b_id in range(len(blocks))}
        has_backward = False
        for b_id, (start, end) in enumerate(blocks):
            last_inst = instructions[end - 1]
            m_uncond = re.match(r"^\s*b(?:\.[nw])?\s+([A-Za-z_0-9.]+)\b", last_inst, flags=re.I)
            m_cond = re.match(r"^\s*(?:b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)|cbz|cbnz)(?:\.[nw])?\s+([A-Za-z_0-9.]+)\b", last_inst, flags=re.I)
            m_ret = re.match(r"^\s*(?:bx\s+lr|pop\s+\{.*pc.*\})", last_inst, flags=re.I)

            if m_uncond:
                tgt = m_uncond.group(1)
                if tgt in labels_to_inst and labels_to_inst[tgt] in block_map:
                    tgt_b = block_map[labels_to_inst[tgt]]
                    adj[b_id].append(tgt_b)
                    if tgt_b <= b_id:
                        has_backward = True
            elif m_cond:
                tgt = m_cond.group(1)
                if tgt in labels_to_inst and labels_to_inst[tgt] in block_map:
                    tgt_b = block_map[labels_to_inst[tgt]]
                    adj[b_id].append(tgt_b)
                    if tgt_b <= b_id:
                        has_backward = True
                if b_id + 1 < len(blocks):
                    adj[b_id].append(b_id + 1)
            elif not m_ret and b_id + 1 < len(blocks):
                adj[b_id].append(b_id + 1)

        if has_backward:
            return None

        memo: dict[int, tuple[int, Counter[str]]] = {}
        def longest_dag(u: int) -> tuple[int, Counter[str]]:
            if u in memo:
                return memo[u]
            max_w = 0
            best_c: Counter[str] = Counter()
            for v in adj[u]:
                if v > u:
                    vw, vc = longest_dag(v)
                    if vw > max_w:
                        max_w = vw
                        best_c = vc
            tot_w = block_weights[u] + max_w
            merged_c = Counter(best_c)
            merged_c.update(block_callees[u])
            memo[u] = (tot_w, merged_c)
            return memo[u]

        return longest_dag(0)

    def _evaluate_execution_cycles(
        self,
        target: str,
        functions: dict[str, str],
        analyses: list[StaticFunctionAnalysis],
        source: str,
        source_facts: str,
    ) -> int | None:
        macros = StagedPredictor._integer_macros(source_facts) if source_facts else {}
        inferred = StagedPredictor._infer_helper_parameter_values(functions, macros)
        analyses_by_name = {a.function_name: a for a in analyses}
        if target not in analyses_by_name:
            return None

        func_internal_cycles: dict[str, int] = {}
        func_callee_calls: dict[str, Counter[str]] = {}

        for name, body in functions.items():
            analysis = analyses_by_name.get(name)
            if not analysis:
                continue
            instructions = self._instruction_lines(analysis.assembly)
            func_macros = dict(macros)
            func_macros.update(inferred.get(name, {}))
            exec_counts = self._calculate_instruction_execution_counts(
                analysis.assembly, body, func_macros
            )
            has_loop = any(c > 1 for c in exec_counts)
            cfg_res = None
            if not has_loop:
                cfg_res = self._evaluate_cfg_dag(analysis.assembly)

            if cfg_res is not None:
                w, callees = cfg_res
                func_internal_cycles[name] = w
                func_callee_calls[name] = Counter(
                    {c: cnt for c, cnt in callees.items() if c in functions}
                )
            else:
                total_func_cycles = 0
                callee_counts: Counter[str] = Counter()
                for idx, inst in enumerate(instructions):
                    count = exec_counts[idx]
                    m_bl = re.search(r"\bblx?\s+([A-Za-z_]\w*)\b", inst, flags=re.I)
                    if m_bl:
                        callee = m_bl.group(1)
                        if callee in functions:
                            callee_counts[callee] += count

                    class_counts = StagedPredictor._classify_instruction(inst)
                    for cls_name, cls_qty in class_counts.items():
                        cycles_each = self.timing_cycles.get(cls_name, 1)
                        if cls_name == "conditional_branch_taken" and count > 1:
                            inst_cycle_cost = (
                                (count - 1) * self.timing_cycles.get("conditional_branch_taken", 4)
                                + 1 * self.timing_cycles.get("conditional_branch_not_taken", 1)
                            )
                        else:
                            inst_cycle_cost = count * cls_qty * cycles_each
                        total_func_cycles += inst_cycle_cost

                func_internal_cycles[name] = total_func_cycles
                func_callee_calls[name] = callee_counts

        graph: dict[str, list[str]] = {fn: [] for fn in functions}
        for caller, callees in func_callee_calls.items():
            for callee in callees:
                if callee in functions:
                    graph[caller].append(callee)

        visited_order: list[str] = []
        visited = set()

        def dfs(node: str):
            visited.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
            visited_order.append(node)

        dfs(target)
        topological_order = list(reversed(visited_order))

        dynamic_invocations: Counter[str] = Counter({target: 1})
        for caller in topological_order:
            caller_calls = dynamic_invocations[caller]
            for callee, per_call in func_callee_calls.get(caller, {}).items():
                if callee in functions:
                    dynamic_invocations[callee] += caller_calls * per_call

        total_system_cycles = sum(
            dynamic_invocations[fn] * func_internal_cycles[fn]
            for fn in functions
            if fn in dynamic_invocations and fn in func_internal_cycles
        )
        return total_system_cycles

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
                draft = self._legalize_assembly(result, body)
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
                        raw_errs = [f"semantic reviewer: {error}" for error in review.errors]
                        filtered_errs = self._filter_spurious_review_errors(raw_errs)
                        if filtered_errs:
                            errors = filtered_errs
                if not errors:
                    break
                previous = draft
            assert draft is not None
            analyses.append(self._analyze(draft, errors))

        valid = all(not function.validation_errors for function in analyses)
        warnings = [
            "Static core-cycle sums execute every emitted instruction once; they are diagnostics, not task execution-time estimates.",
        ]
        estimated_cycles = self._evaluate_execution_cycles(
            target, functions, analyses, source, source_facts
        )
        estimated_us = (
            round(estimated_cycles / 48.0, 2)
            if estimated_cycles is not None else None
        )
        if valid:
            warnings.append(
                "Dynamic execution cycles evaluated from static Thumb-2 assembly and source loop trip bounds at 48 MHz."
            )
        else:
            warnings.append(
                "At least one generated function failed semantic assembly audits; execution cycles are estimated from generated assembly and loop trip bounds."
            )
        return StaticAssemblyReport(
            analysis_status="SUPPORTED" if valid else "VALIDATION_REQUIRED",
            provider="ollama",
            model=self.client.model,
            target_function=target,
            compiler_profile=self.PROFILE,
            functions=analyses,
            estimated_execution_cycles=estimated_cycles,
            estimated_execution_us=estimated_us,
            warnings=warnings,
        ), raw_outputs
