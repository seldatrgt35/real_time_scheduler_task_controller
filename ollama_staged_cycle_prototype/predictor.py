from __future__ import annotations

from collections import defaultdict
import json
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
from gemini_rag_cycle_prototype.predictor import (
    indexed_access_obligations,
    source_analysis_bundle,
)

from ollama_staged_cycle_prototype.schemas import (
    AggregateInstructionCycles,
    CalleeCount,
    FunctionContribution,
    FunctionBlockPlan,
    FunctionLedger,
    PerCallInstructionCount,
    StagedPrediction,
    StructurePlan,
    TIMING_PROFILE_CYCLES,
)


class StagedPredictor:
    C_CONTROL_KEYWORDS = {
        "if", "else", "for", "while", "switch", "do", "return", "sizeof",
    }
    def __init__(self, repository_root: Path, client):
        self.root = repository_root.resolve()
        self.client = client
        config = self.root / "gemini_rag_cycle_prototype" / "config"
        self.hardware = json.loads(
            (config / "hardware_profile.json").read_text(encoding="utf-8")
        )
        self.timing = json.loads(
            (config / "cortex_m4_timing_profile.json").read_text(encoding="utf-8")
        )
        self.timing_cycles = {
            item["name"]: item["cycles_each"]
            for item in self.timing["instruction_classes"]
        }
        if set(self.timing_cycles) != set(TIMING_PROFILE_CYCLES):
            raise ValueError(
                "timing profile instruction classes disagree with the "
                "structured-output schema"
            )
        self.gcc_pattern_path = (
            self.root / "ollama_staged_cycle_prototype" / "knowledge"
            / "gcc_o0_assembly_patterns.json"
        )

    @staticmethod
    def _relevant_functions(source: str, target: str) -> dict[str, str]:
        target_body = extract_function(source, target)
        if target_body is None:
            raise ValueError(f"target function not found: {target}")
        helper_region = extract_reachable_helpers(source, target)
        relevant = {target: target_body}
        for name in function_names(helper_region):
            if name in StagedPredictor.C_CONTROL_KEYWORDS:
                continue
            body = extract_function(helper_region, name)
            if body:
                relevant[name] = body
        return relevant

    def _structure_prompt(
        self, target: str, functions: dict[str, str], source_facts: str,
        analysis_source: str, analysis_context: str,
        access_obligations: list[str],
    ) -> str:
        all_loop_obligations = []
        for f_name, f_body in functions.items():
            for o in self._loop_execution_obligations(f_name, f_body, functions, source_facts):
                all_loop_obligations.append(f"[{f_name}] {o}")

        return f"""You are pass 1 of a staged GCC -O0 source timing analysis.
Analyze only control flow and dynamic function-call multiplicities on the most
expensive feasible source path. Do not calculate cycles or write assembly.

Target: {target}
Compiler: ARM GCC 11.4 -O0, Cortex-M4 Thumb-2

Source-derived indexed-access obligations:
{json.dumps(access_obligations, indent=2)}

Source-derived proven loop execution obligations:
{json.dumps(all_loop_obligations, indent=2)}

Required rules:
- The target function has dynamic_calls=1.
- Include every supplied reachable function exactly once.
- A helper's dynamic_calls is its total invocation count during one target call.
- Expand loop call sites using their proven source bounds.
- For nested loops (a loop inside another loop), explicitly state both the individual
  bounds and compound body iterations (e.g. outer 8 * inner 4 = 32 iterations) in loop_bounds.
- Never invent a helper or omit a supplied reachable helper.
- Put genuinely unprovable source bounds in unresolved.

Functions supplied:
{json.dumps(list(functions), indent=2)}

Source constants/macros (authoritative for loop bounds):
```c
{source_facts}
```

Source:
```c
{analysis_source}
```

Additional source/initialization context (outside the timed interval):
{analysis_context or "No additional context files supplied."}
"""

    def _ledger_prompt(
        self, name: str, body: str, all_functions: dict[str, str],
        plan: StructurePlan, source_facts: str,
        analysis_context: str, gcc_evidence: list[dict],
        access_obligations: list[str],
    ) -> str:
        direct_callees = sorted(
            candidate
            for candidate in all_functions
            if candidate != name
            and re.search(rf"\b{re.escape(candidate)}\s*\(", body)
        )
        loop_obligations = self._loop_execution_obligations(
            name, body, all_functions, source_facts
        )
        control_obligations = self._control_flow_obligations(
            body, name=name, all_functions=all_functions, source_facts=source_facts
        )
        return f"""You are pass 2 of a staged GCC 11.4 -O0 assembly-shape analysis.
Predict static Thumb-2 instruction-class counts separately for every basic
block of EXACTLY ONE invocation of function {name}. Do not emit a whole-function
aggregate and do not calculate cycles.

Hardware profile:
{json.dumps(self.hardware, indent=2)}

Authoritative timing profile:
{json.dumps(self.timing, indent=2)}

GCC 11.4 -O0 transformation evidence (identical evidence source used by the
Gemini no-RAG path; these are compiler examples, not board measurements):
{json.dumps(gcc_evidence, indent=2)}

Source-derived indexed-access obligations:
{json.dumps(access_obligations, indent=2)}

Source-derived proven loop execution obligations:
{json.dumps(loop_obligations, indent=2)}

Source-derived control-flow regions that must all be represented:
{json.dumps(control_obligations, indent=2)}

Allowed instruction classes and cycles:
{json.dumps(self.timing_cycles, indent=2)}

Pass-1 structure plan:
{plan.model_dump_json(indent=2)}

Source constants/macros (authoritative):
```c
{source_facts}
```

Additional source/initialization context (outside the timed interval):
{analysis_context or "No additional context files supplied."}

Direct callees found syntactically in this function:
{json.dumps(direct_callees)}

Rules:
- Split entry/prologue, loop body, loop condition, branch arms, joins and
  epilogue into distinct basic blocks. Give every block a stable unique ID.
- Each block has its dynamic execution_count_per_invocation on the selected
  path. instruction_counts inside a block are STATIC counts for one execution
  of that block; never pre-multiply them by the block execution count.
- CRITICAL FOR LOOPS AND NESTED LOOPS:
  * Audit execution counts against 'Source-derived proven loop execution obligations'.
  * For a single loop with N iterations: loop body blocks execute N times.
  * For nested loops: The dynamic execution count of the inner loop's sequential body
    is the compound product of enclosing loop iterations (prod(trip_counts)).
- MUTUAL EXCLUSION OF CONDITIONAL BRANCHES (if-else):
  * Alternative branch arms of an if-else statement are mutually exclusive.
  * For any conditional construct evaluated K times, the execution counts of its alternative
    branches must partition K: execution_count(taken_arm) + execution_count(not_taken_arm) == K.
  * NEVER assign K executions to BOTH the taken arm and the not-taken arm.
  * On a worst-case path, the path selects the more expensive feasible arm (e.g. taken_arm = K,
    not_taken_arm = 0), never both arms simultaneously.
- Do not put conditional or unconditional branch classes in a block's
  instruction_counts. Represent every executed control-flow transfer in edges.
- For a conditional block, emit exactly one conditional_taken edge and one
  conditional_not_taken edge. Their execution counts must sum exactly to the
  source block execution count. This permits mixed loop outcomes such as two
  taken and two not-taken evaluations.
- Use a fallthrough edge for sequential flow (zero branch-refill charge) and an
  unconditional edge only where GCC emits an actual B instruction.
- Prefer one instruction_counts row per instruction class per block. If separate
  rows are needed, keep every row static; Python safely aggregates duplicates.
- Basic block definition and Control Flow Graph (CFG) rules:
  * A basic block CANNOT contain control flow. Every loop (`for`, `while`) and conditional
    (`if`, `else if`, `switch`) inherently introduces control-flow boundaries and CANNOT be
    merged into a flat straight-line block.
  * Every loop (outer OR nested) MUST have:
    (a) A loop condition / test block evaluated N+1 times, with its conditional branch edges.
    (b) The loop body.
    (c) A loop latch / counter increment block executed N times (updating the loop variable
        in GCC -O0 via load, add, store).
  * Every if statement has a condition test block with taken and not-taken branch edges.
  * Prologue, parameter homing, and initial outer loop index initialization form ONE contiguous
    entry basic block; do NOT separate them into artificial micro-blocks.
  * Straight-line statements between branch boundaries form ONE maximal basic block.
  * Static instruction density: Ground static instruction counts strictly in the C statements
    contained in that block. In Thumb-2 GCC -O0, a typical scalar C assignment or arithmetic
    update takes 2 to 4 static instructions (load operand, ALU op, store result). Never hallucinate
    duplicate loads or stores for the same variable within a single basic block.
- Consistency requirement: Every block referenced in selected_path, edges, or
  successors MUST be explicitly defined in blocks. Never leave blocks undefined.
- Omit instruction classes with static_count 0: only emit classes with static_count >= 1.
- The complete response must remain compact: keep each evidence and source_region string
  to a short phrase (under 10 words). Never copy source code or C statements into evidence.
- Count GCC -O0 stack parameter homing, local loads/stores, loop control,
  comparisons, address calculations, prologue and epilogue.
- Audit every relevant indexed-access obligation at its full dynamic
  multiplicity. Do not merge memory operations into the ALU class.
- Apply the supplied GCC transformation examples structurally. In particular,
  retain -O0 parameter homing, repeated stack reloads/stores, array address
  formation and balanced prologue/epilogue register transfers.
- callees lists direct calls made during one invocation of {name}; expand
  loop-contained call sites into calls_per_invocation.
- The callee names must exactly match the syntactic direct-callee list above.
  Do not include transitive callees; Python composes those separately.
- BL ledger count must equal the sum of direct callee calls.
- Do not include callee body instructions here. Each callee is analyzed in a
  separate request and Python composes it later.
- Represent the executed return exactly once with
  function_return_with_refill. Never also emit
  pop_pc_pipeline_refill_worst_case for the same return.
- For PUSH/POP, push_or_pop_register_transfer is the number of transferred
  registers and multi_register_instruction_overhead is the number of executed
  PUSH/POP instructions. Do not treat a whole register list as one transfer.
- Do not calculate final cycles and do not apply a margin.

Function under analysis:
```c
{body}
```

Names of other supplied functions:
{json.dumps([item for item in all_functions if item != name])}
"""

    def _review_prompt(
        self, name: str, body: str, initial: FunctionBlockPlan,
        source_facts: str, analysis_context: str, gcc_evidence: list[dict],
        access_obligations: list[str],
        all_functions: dict[str, str] | None = None,
    ) -> str:
        loop_obligations = self._loop_execution_obligations(
            name, body, all_functions or {}, source_facts
        )
        control_obligations = self._control_flow_obligations(
            body, name=name, all_functions=all_functions or {}, source_facts=source_facts
        )
        return f"""You are pass 3, an independent critical reviewer of a predicted
GCC 11.4 -O0 Thumb-2 assembly shape for exactly one invocation of function
{name}. Return a COMPLETE corrected FunctionBlockPlan, not comments or a patch.

The first prediction is only a draft. Reconstruct and correct it by comparing
every C statement and control-flow region against the GCC micro-patterns.

Mandatory review:
- selected_path must list the executed block IDs in order and may not be empty.
- Audit basic block cohesion and CFG completeness:
  * Ensure that every loop (`for`, `while`) and conditional (`if`) from 'Source-derived control-flow regions'
    has its distinct condition test block, executed branch edges, and (for loops) latch/increment block.
  * An inner loop or if statement must NEVER be absorbed into an unbranched flat block.
  * Straight-line statements between branch boundaries must be consolidated into maximal basic blocks.
- Audit loop and branch dynamic execution counts:
  * Cross-check execution counts against 'Source-derived proven loop execution obligations'.
  * For nested loops, ensure the loop condition, body, and latch all reflect the compound product of enclosing trip counts.
  * Enforce mutual exclusion on if-else branches: alternative branch arm execution counts must
    sum to the condition's evaluation count (taken + not_taken == K). Never execute both alternative
    arms for the same iteration.
- Audit static instruction density:
  Ensure static instruction counts reflect real GCC -O0 instructions for the C statements
  in that block (typically 2-4 instructions per simple scalar C assignment or update).
  Consolidate any redundant or duplicated instructions.
- A loop condition executed N+1 times has N taken and one not-taken outcome;
  represent those outcomes without calling all N+1 evaluations taken.
- instruction_counts are STATIC per one block execution. Block execution count
  performs the only dynamic multiplication.
- Conditional outcomes belong exclusively in edges. For every conditional
  source block, taken-edge executions plus not-taken-edge executions must equal
  that block's execution count. Never place a pre-multiplied branch count in a
  block instruction row.
- A fallthrough edge has no refill cost. Use unconditional only for an actual
  emitted B instruction.
- Evidence for a class may mention only operations belonging to that class:
  LDR/LDRB/LDRH/LDRSH are loads; STR/STRB/STRH are stores; MOV/UXT/SXT,
  ADD/SUB/CMP/shifts/logical operations are ALU; B is unconditional; B<cond>
  is conditional; BL is a call. Never place STR or B under ALU, MOV/UXT under
  load, or B under store.
- Audit GCC -O0 stack parameter homing, repeated local reload/store, indexed
  address formation, extensions, PUSH/POP register transfers and multi-register
  instruction overhead. Do not optimize them away.
- Include all post-loop if/else and final sink/output expressions. A valid JSON
  shape is not evidence that the draft assembly is complete.
- Do not use board measurements, correction factors, margins or desired cycles.

Hardware profile:
{json.dumps(self.hardware, indent=2)}

GCC 11.4 -O0 transformation evidence:
{json.dumps(gcc_evidence, indent=2)}

Indexed-access obligations:
{json.dumps(access_obligations, indent=2)}

Source-derived proven loop execution obligations:
{json.dumps(loop_obligations, indent=2)}

Source-derived control-flow regions that must all be represented by blocks and
executed edge counts:
{json.dumps(control_obligations, indent=2)}

Source constants/macros:
```c
{source_facts}
```

Initialization/path context (outside timed interval):
{analysis_context or "No additional context supplied."}

Function source:
```c
{body}
```

Draft block plan to audit and replace:
{initial.model_dump_json(indent=2)}
"""

    @staticmethod
    def _infer_helper_parameter_values(
        all_functions: dict[str, str], macro_values: dict[str, int]
    ) -> dict[str, dict[str, int]]:
        param_values: dict[str, dict[str, int]] = {}
        for name, body in all_functions.items():
            m = re.search(rf"\b{re.escape(name)}\s*\(([^)]*)\)", body)
            if not m:
                continue
            param_list = [p.strip() for p in m.group(1).split(",") if p.strip()]
            param_names = []
            for p in param_list:
                parts = re.findall(r"[A-Za-z_]\w*", p)
                if parts:
                    param_names.append(parts[-1])
            if not param_names:
                continue
            for caller_name, caller_body in all_functions.items():
                if caller_name == name:
                    continue
                for call in re.finditer(rf"\b{re.escape(name)}\s*\(([^)]*)\)", caller_body):
                    args = [a.strip() for a in call.group(1).split(",")]
                    for i, arg in enumerate(args):
                        if i < len(param_names):
                            clean_arg = re.sub(r"[uUlL]+$", "", arg)
                            val = int(clean_arg) if clean_arg.isdigit() else macro_values.get(clean_arg)
                            if val is not None:
                                if name not in param_values:
                                    param_values[name] = {}
                                param_values[name][param_names[i]] = val
        return param_values

    @staticmethod
    def _loop_execution_obligations(
        name: str, body: str, all_functions: dict[str, str], source_facts: str
    ) -> list[str]:
        macros = StagedPredictor._integer_macros(source_facts) if source_facts else {}
        if all_functions:
            inferred = StagedPredictor._infer_helper_parameter_values(all_functions, macros)
            macros.update(inferred.get(name, {}))
        loops = StagedPredictor._proven_for_loops(body, macros)
        obligations: list[str] = []
        for start, end, trip, desc in loops:
            enclosing = [p for p in loops if p[0] < start and p[1] > end]
            mult = 1
            enclosing_descs = []
            for p in enclosing:
                mult *= p[2]
                enclosing_descs.append(f"{p[3]} ({p[2]}x)")
            total = mult * trip
            if enclosing:
                parents_str = ", ".join(enclosing_descs)
                obligations.append(
                    f"NESTED LOOP: {desc} (trip={trip}) inside [{parents_str}] "
                    f"-> COMPOUND INNER BODY EXECUTION COUNT = {total} times"
                )
            else:
                obligations.append(
                    f"LOOP: {desc} -> BODY EXECUTION COUNT = {trip} times"
                )
        return obligations

    @staticmethod
    def _control_flow_obligations(
        body: str,
        name: str = "",
        all_functions: dict[str, str] | None = None,
        source_facts: str = "",
    ) -> list[str]:
        """Expose source control regions without synthesizing their CFG."""
        obligations: list[str] = []
        macros = StagedPredictor._integer_macros(source_facts) if source_facts else {}
        if all_functions and name:
            inferred = StagedPredictor._infer_helper_parameter_values(all_functions, macros)
            macros.update(inferred.get(name, {}))
        loops = StagedPredictor._proven_for_loops(body, macros)

        for line_number, raw_line in enumerate(body.splitlines(), start=1):
            line = re.sub(r"/\*.*?\*/", "", raw_line).strip()
            if not line:
                continue
            if re.search(
                r"\b(?:for|while|if|else\s+if|else|switch|case|return)\b",
                line,
            ):
                matched_tag = ""
                for start, end, trip, desc in loops:
                    var = desc.split(":")[0].strip()
                    if re.search(rf"\bfor\s*\([^;]*\b{re.escape(var)}\b", line):
                        parents = [p for p in loops if p[0] < start and p[1] > end]
                        mult = 1
                        for p in parents:
                            mult *= p[2]
                        total = mult * trip
                        if parents:
                            matched_tag = f" -> [NESTED LOOP BODY EXECUTIONS = {total} ({mult} * {trip})]"
                        else:
                            matched_tag = f" -> [LOOP BODY EXECUTIONS = {total}]"
                        break
                obligations.append(f"line {line_number}: {line[:240]}{matched_tag}")
        return obligations

    @staticmethod
    def _block_plan_to_ledger(plan: FunctionBlockPlan) -> FunctionLedger:
        """Deterministically expand static block rows into a per-call ledger."""
        counts: dict[str, int] = defaultdict(int)
        evidence: dict[str, list[str]] = defaultdict(list)
        for block in plan.blocks:
            for item in block.instruction_counts:
                counts[item.instruction_class] += (
                    item.static_count * block.execution_count_per_invocation
                )
                evidence[item.instruction_class].append(
                    f"{block.block_id} x{block.execution_count_per_invocation}: "
                    f"{item.static_count} ({item.evidence})"
                )
        edge_class = {
            "conditional_taken": "conditional_branch_taken",
            "conditional_not_taken": "conditional_branch_not_taken",
            "unconditional": "unconditional_branch_with_refill",
        }
        for edge in plan.edges:
            instruction_class = edge_class.get(edge.kind)
            if instruction_class is None:
                continue
            counts[instruction_class] += edge.execution_count_per_invocation
            evidence[instruction_class].append(
                f"{edge.source_block}->{edge.target_block}: "
                f"{edge.execution_count_per_invocation} ({edge.evidence})"
            )
        conditional = counts.get("conditional_branch_taken", 0) + counts.get(
            "conditional_branch_not_taken", 0
        )
        return FunctionLedger(
            function_name=plan.function_name,
            selected_path=plan.selected_path,
            callees=plan.callees,
            conditional_branch_evaluations_per_invocation=conditional,
            instruction_counts=[
                PerCallInstructionCount(
                    instruction_class=name,
                    dynamic_count_per_invocation=count,
                    evidence="; ".join(evidence[name])[:500],
                )
                for name, count in counts.items()
            ],
            unresolved=plan.unresolved,
        )

    @staticmethod
    def _source_facts(source: str) -> str:
        """Keep source constants visible when function extraction removes them."""
        facts = []
        lines = source.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index]
            if re.match(r"^\s*#\s*define\b", line):
                definition = [line]
                while definition[-1].rstrip().endswith("\\"):
                    index += 1
                    if index >= len(lines):
                        break
                    definition.append(lines[index])
                facts.extend(definition)
            index += 1
        return "\n".join(facts) or "/* no source macros supplied */"

    @staticmethod
    def _direct_callee_names(
        name: str, body: str, functions: dict[str, str]
    ) -> set[str]:
        return {
            candidate
            for candidate in functions
            if candidate != name
            and re.search(rf"\b{re.escape(candidate)}\s*\(", body)
        }

    @staticmethod
    def _direct_callee_occurrences(
        body: str, callee_name: str
    ) -> int:
        """Count syntactic call sites; this is a lower bound on dynamic calls."""
        return len(re.findall(rf"\b{re.escape(callee_name)}\s*\(", body))

    @staticmethod
    def _integer_macros(source_facts: str) -> dict[str, int]:
        """Extract simple integer object macros used as source loop bounds."""
        values: dict[str, int] = {}
        pending = list(re.finditer(
            r"^\s*#\s*define\s+([A-Za-z_]\w*)\s+(.+?)\s*$",
            source_facts, re.MULTILINE,
        ))
        # Resolve literal macros first, then aliases/simple arithmetic.  Eval is
        # deliberately restricted to digits and integer operators.
        for _ in range(len(pending) + 1):
            changed = False
            for match in pending:
                name, expression = match.groups()
                expression = re.sub(r"/\*.*?\*/|//.*", "", expression).strip()
                expression = re.sub(r"(?<=\d)[uUlL]+\b", "", expression)
                for key, value in values.items():
                    expression = re.sub(rf"\b{re.escape(key)}\b", str(value), expression)
                if not re.fullmatch(r"[\d\s()+\-*/%<>&|]+", expression):
                    continue
                try:
                    value = int(eval(expression, {"__builtins__": {}}, {}))
                except (SyntaxError, TypeError, ValueError, ZeroDivisionError):
                    continue
                if value >= 0 and values.get(name) != value:
                    values[name] = value
                    changed = True
            if not changed:
                break
        return values

    @staticmethod
    def _matching_brace(text: str, opening: int) -> int | None:
        depth = 0
        for index in range(opening, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    return index
        return None

    @staticmethod
    def _proven_for_loops(
        body: str, macro_values: dict[str, int]
    ) -> list[tuple[int, int, int, str]]:
        """Return braced, canonical for-loop body ranges and trip counts."""
        loops: list[tuple[int, int, int, str]] = []
        pattern = re.compile(
            r"\bfor\s*\(\s*(?:[A-Za-z_]\w*\s+)*([A-Za-z_]\w*)\s*=\s*"
            r"(\d+)[uUlL]*\s*;\s*\1\s*(<|<=)\s*([A-Za-z_]\w*|\d+[uUlL]*)"
            r"\s*;\s*(?:\+\+\s*\1|\1\s*\+\+)\s*\)\s*\{"
        )
        for match in pattern.finditer(body):
            variable, start_text, comparator, bound_text = match.groups()
            start = int(start_text)
            clean_bound = re.sub(r"[uUlL]+$", "", bound_text)
            bound = (int(clean_bound) if clean_bound.isdigit()
                     else macro_values.get(clean_bound))
            if bound is None:
                continue
            trip_count = max(0, bound - start + (1 if comparator == "<=" else 0))
            opening = match.end() - 1
            closing = StagedPredictor._matching_brace(body, opening)
            if closing is not None:
                loops.append((opening + 1, closing, trip_count,
                              f"{variable}: {start} {comparator} {bound_text}"))
        return loops

    @staticmethod
    def _proven_direct_callee_calls(
        body: str, callee_name: str, source_facts: str
    ) -> tuple[int | None, str]:
        """Compute call multiplicity from each call site's lexical loop scope."""
        sites = list(re.finditer(rf"\b{re.escape(callee_name)}\s*\(", body))
        if not sites:
            return 0, "no syntactic call site"
        macros = StagedPredictor._integer_macros(source_facts)
        loops = StagedPredictor._proven_for_loops(body, macros)
        total = 0
        evidence: list[str] = []
        for site in sites:
            enclosing = [loop for loop in loops if loop[0] <= site.start() < loop[1]]
            multiplier = 1
            for _, _, trip_count, _ in enclosing:
                multiplier *= trip_count
            total += multiplier
            evidence.append("outside loops" if not enclosing else " * ".join(
                str(loop[2]) for loop in enclosing
            ))
        # If a call is lexically inside an unrecognized for/while loop, its
        # dynamic multiplicity is not proven and must not be guessed.
        for token in re.finditer(r"\b(?:for|while)\s*\(", body):
            opening = body.find("{", token.end())
            if opening < 0:
                continue
            closing = StagedPredictor._matching_brace(body, opening)
            if closing is None:
                continue
            recognized = any(loop[0] == opening + 1 for loop in loops)
            if not recognized and any(opening < site.start() < closing for site in sites):
                return None, "call is inside a loop whose bound was not proven"
        return total, "Python lexical loop-scope proof per call site: " + " + ".join(evidence)

    @staticmethod
    def _compose_call_counts(
        target: str, ledgers: dict[str, FunctionLedger]
    ) -> dict[str, int]:
        totals: dict[str, int] = defaultdict(int)
        visiting: set[str] = set()

        def visit(name: str, multiplier: int) -> None:
            if name in visiting:
                raise ValueError("recursive call graph is unsupported")
            ledger = ledgers.get(name)
            if ledger is None:
                raise ValueError(f"missing ledger for called function: {name}")
            totals[name] += multiplier
            visiting.add(name)
            for callee in ledger.callees:
                visit(callee.function_name, multiplier * callee.calls_per_invocation)
            visiting.remove(name)

        visit(target, 1)
        return dict(totals)

    @staticmethod
    def _normalize_ledger_relations(
        name: str,
        ledger: FunctionLedger,
        functions: dict[str, str],
        planned: dict[str, int],
        parent_map: dict[str, set[str]],
        source_facts: str = "",
    ) -> tuple[FunctionLedger, list[str]]:
        """Move redundant call/branch arithmetic out of the language model."""
        errors: list[str] = []
        expected_names = StagedPredictor._direct_callee_names(
            name, functions[name], functions
        )
        callees: list[CalleeCount] = []
        parent_calls = planned.get(name, 0)
        for callee_name in sorted(expected_names):
            child_calls = planned.get(callee_name, 0)
            call_sites = StagedPredictor._direct_callee_occurrences(
                functions[name], callee_name
            )
            proven_calls, proof = StagedPredictor._proven_direct_callee_calls(
                functions[name], callee_name, source_facts
            )
            if proven_calls is not None:
                calls_per_invocation = proven_calls
                evidence = proof
            elif parent_map.get(callee_name) == {name}:
                planned_ratio = 0
                if parent_calls >= 1 and child_calls % parent_calls == 0:
                    planned_ratio = child_calls // parent_calls
                calls_per_invocation = max(call_sites, planned_ratio)
                evidence = (
                    "fallback from pass-1 dynamic calls and "
                    f"{call_sites} syntactic direct call-site(s): {proof}"
                )
            else:
                calls_per_invocation = max(1, call_sites)
                evidence = (
                    f"syntactic direct call-site(s) for shared callee: {call_sites} ({proof})"
                )
            if calls_per_invocation < 1:
                errors.append(f"no call multiplicity for {name}->{callee_name}")
                continue
            callees.append(CalleeCount(
                function_name=callee_name,
                calls_per_invocation=calls_per_invocation,
                evidence=evidence,
            ))

        aggregated_counts: dict[str, int] = defaultdict(int)
        aggregated_evidence: dict[str, list[str]] = defaultdict(list)
        for item in ledger.instruction_counts:
            aggregated_counts[item.instruction_class] += (
                item.dynamic_count_per_invocation
            )
            if item.evidence not in aggregated_evidence[item.instruction_class]:
                aggregated_evidence[item.instruction_class].append(item.evidence)
        counts = {
            instruction_class: PerCallInstructionCount(
                instruction_class=instruction_class,
                dynamic_count_per_invocation=count,
                evidence="; ".join(aggregated_evidence[instruction_class]),
            )
            for instruction_class, count in aggregated_counts.items()
        }

        # Canonicalize both possible representations of POP {..., PC} to the
        # single abstract return class used by the compact ledger.
        pop_pc = counts.pop("pop_pc_pipeline_refill_worst_case", None)
        return_evidence = (
            "canonicalized by Python from POP {..., PC}"
            if pop_pc is not None
            else "one return required for each completed invocation of a "
                 "supplied non-noreturn C function"
        )
        # Every supplied function in this experiment completes normally. A
        # selected per-invocation path therefore has exactly one return control
        # transfer, whether Qwen spells it BX LR, POP {..., PC}, or only records
        # the POP register transfers in its evidence text.
        counts["function_return_with_refill"] = PerCallInstructionCount(
            instruction_class="function_return_with_refill",
            dynamic_count_per_invocation=1,
            evidence=return_evidence,
        )
        bl_count = sum(item.calls_per_invocation for item in callees)
        if bl_count:
            counts["function_call_bl_with_refill"] = PerCallInstructionCount(
                instruction_class="function_call_bl_with_refill",
                dynamic_count_per_invocation=bl_count,
                evidence="derived by Python from direct callee multiplicities",
            )
        else:
            counts.pop("function_call_bl_with_refill", None)
        conditional = sum(
            counts.get(branch, PerCallInstructionCount(
                instruction_class=branch,
                dynamic_count_per_invocation=0,
                evidence="absent",
            )).dynamic_count_per_invocation
            for branch in (
                "conditional_branch_taken",
                "conditional_branch_not_taken",
            )
        )
        normalized = ledger.model_copy(update={
            "callees": callees,
            "instruction_counts": list(counts.values()),
            "conditional_branch_evaluations_per_invocation": conditional,
        })
        return normalized, errors

    def predict(self, source: str, target: str) -> tuple[StagedPrediction, list[str]]:
        functions = self._relevant_functions(source, target)
        source_facts = self._source_facts(source)
        analysis_source, analysis_context = source_analysis_bundle(source, target)
        access_obligations = indexed_access_obligations(source, target)
        raw_outputs: list[str] = []
        plan, raw = self.client.predict(
            self._structure_prompt(
                target, functions, source_facts, analysis_source,
                analysis_context, access_obligations,
            ),
            response_schema=StructurePlan,
        )
        raw_outputs.append(raw)
        errors: list[str] = []
        if plan.target_function != target:
            errors.append("structure plan target does not match requested target")
        planned = {item.function_name: item.dynamic_calls for item in plan.functions}
        unknown_planned = set(planned) - set(functions)
        if unknown_planned:
            errors.append(
                f"structure plan contains unknown functions: {sorted(unknown_planned)}"
            )
        for missing_fn in set(functions) - set(planned):
            planned[missing_fn] = 0
        # One CLI prediction always represents exactly one target invocation.
        planned[target] = 1
        for item in plan.functions:
            if item.function_name == target:
                item.dynamic_calls = 1
                item.call_count_evidence = (
                    "canonicalized by Python: one CLI analysis equals one "
                    "target invocation"
                )

        parent_map: dict[str, set[str]] = defaultdict(set)
        for caller, body in functions.items():
            for callee in self._direct_callee_names(caller, body, functions):
                parent_map[callee].add(caller)

        ledgers: dict[str, FunctionLedger] = {}
        for name, body in functions.items():
            # Retrieve transformation examples for the function currently
            # being synthesized, rather than reusing only the target's tags.
            function_evidence = retrieve_assembly_evidence(
                source, self.gcc_pattern_path, function_name=name, limit=8
            )
            function_access_obligations = indexed_access_obligations(
                source, name
            )
            block_plan, raw = self.client.predict(
                self._ledger_prompt(
                    name, body, functions, plan, source_facts,
                    analysis_context, function_evidence,
                    function_access_obligations,
                ),
                response_schema=FunctionBlockPlan,
            )
            raw_outputs.append(raw)
            reviewed_plan, raw = self.client.predict(
                self._review_prompt(
                    name, body, block_plan, source_facts, analysis_context,
                    function_evidence, function_access_obligations,
                    all_functions=functions,
                ),
                response_schema=FunctionBlockPlan,
            )
            raw_outputs.append(raw)
            block_plan = reviewed_plan
            has_source_condition = bool(re.search(r"\b(?:if|for|while)\s*\(", body))
            has_conditional_edges = any(
                edge.kind.startswith("conditional_") for edge in block_plan.edges
            )
            if has_source_condition and not has_conditional_edges:
                errors.append(
                    f"{name} contains source conditions but its CFG has no "
                    "conditional edges"
                )
            ledger = self._block_plan_to_ledger(block_plan)
            if ledger.function_name != name:
                errors.append(
                    f"ledger function mismatch: expected {name}, "
                    f"received {ledger.function_name}"
                )
            ledger, relation_errors = self._normalize_ledger_relations(
                name, ledger, functions, planned, parent_map, source_facts
            )
            errors.extend(relation_errors)
            unknown_callees = {
                item.function_name for item in ledger.callees
            } - set(functions)
            if unknown_callees:
                errors.append(
                    f"{name} ledger calls unknown functions: "
                    f"{sorted(unknown_callees)}"
                )
            expected_callees = self._direct_callee_names(name, body, functions)
            returned_callees = {item.function_name for item in ledger.callees}
            if returned_callees != expected_callees:
                errors.append(
                    f"{name} direct callee mismatch: expected "
                    f"{sorted(expected_callees)}, received "
                    f"{sorted(returned_callees)}"
                )
            ledgers[name] = ledger

        try:
            composed_calls = self._compose_call_counts(target, ledgers)
        except ValueError as exc:
            errors.append(str(exc))
            composed_calls = {}
        if composed_calls and composed_calls != planned:
            # The syntactic call graph/call-site lower bound is authoritative
            # when the model confuses number of callees with target calls.
            planned = composed_calls
            for item in plan.functions:
                if item.function_name in composed_calls:
                    item.dynamic_calls = composed_calls[item.function_name]
                    item.call_count_evidence += (
                        "; normalized by Python call-graph composition"
                    )

        aggregate_counts: dict[str, int] = defaultdict(int)
        contributions: list[FunctionContribution] = []
        for name, ledger in ledgers.items():
            calls = composed_calls.get(name, planned.get(name, 0))
            per_call_cycles = sum(
                item.dynamic_count_per_invocation
                * self.timing_cycles[item.instruction_class]
                for item in ledger.instruction_counts
            )
            contributions.append(FunctionContribution(
                function_name=name,
                dynamic_calls=calls,
                cycles_per_invocation=per_call_cycles,
                total_cycles=per_call_cycles * calls,
            ))
            for item in ledger.instruction_counts:
                aggregate_counts[item.instruction_class] += (
                    item.dynamic_count_per_invocation * calls
                )

        aggregate = [
            AggregateInstructionCycles(
                instruction_class=name,
                dynamic_count=count,
                cycles_each=self.timing_cycles[name],
                total_cycles=count * self.timing_cycles[name],
            )
            for name, count in sorted(aggregate_counts.items())
        ]
        total = sum(item.total_cycles for item in aggregate)
        contribution_total = sum(item.total_cycles for item in contributions)
        if contribution_total != total:
            errors.append(
                "function contributions disagree with aggregate ledger: "
                f"contributions={contribution_total}, aggregate={total}"
            )
        known_functions = set(functions)
        unresolved = [
            item for item in plan.unresolved
            if item.strip() not in known_functions
        ]
        unresolved.extend(
            f"{name}: {item}"
            for name, ledger in ledgers.items()
            for item in ledger.unresolved
            if item.strip() not in known_functions
        )
        status = "VALIDATION_REQUIRED" if errors or unresolved else "SUPPORTED"
        prediction = StagedPrediction(
            analysis_status=status,
            provider=self.client.provider,
            model=self.client.model,
            target_function=target,
            hardware_profile_id=self.hardware["hardware_profile_id"],
            structure_plan=plan,
            function_ledgers=list(ledgers.values()),
            function_contributions=contributions,
            aggregate_instruction_ledger=aggregate,
            estimated_source_execution_cycles=(
                total if status == "SUPPORTED" else None
            ),
            estimated_source_execution_us=(
                total / 48.0 if status == "SUPPORTED" else None
            ),
            validation_errors=errors,
            warnings=[
                "Experimental source-only estimate; not a formal WCET bound.",
                "Compiler-sensitive and PFlash effects not priced by supplied "
                "evidence remain outside this source-level estimate.",
                *(["Unresolved source/ledger items: " + "; ".join(unresolved)]
                  if unresolved else []),
            ],
        )
        return prediction, raw_outputs
