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
    AssemblySection,
    CalleeCount,
    FunctionContribution,
    FunctionAssemblyPlan,
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
Analyze only control flow and dynamic function-call multiplicities on one
feasible source path. Initialization/path context is authoritative when it
determines a condition; among genuinely unknown alternatives, select the most
expensive feasible path. Do not calculate cycles or write assembly.

Target: {target}
Compiler: ARM GCC 11.4 -O0, Cortex-M4 Thumb-2

Source-derived indexed-access obligations:
{json.dumps(access_obligations, indent=2)}

Source-derived proven loop execution obligations:
{json.dumps(all_loop_obligations, indent=2)}

Required rules:
- The target function has dynamic_calls=1.
- `selected_path` is mandatory and lists the target's executed source decisions
  in order. It must agree with known initialization values.
- Include every supplied reachable function exactly once.
- A helper's dynamic_calls is its total invocation count during one target call on the selected worst-case path.
- A helper reachable only through an unselected branch has dynamic_calls=0; keep it in the functions list instead of inventing a call.
- In conditional branching (if/else if/else, switch-case), alternative branches are mutually exclusive! If a helper is called in branch A and also in branch B, its dynamic_calls on any single path is at most 1, NEVER the sum of mutually exclusive branches.
- Expand loop call sites using their proven source bounds.
- For nested loops (a loop inside another loop), explicitly compute and state the compound body iterations across all enclosing loop levels in loop_bounds.
- For loops with non-unit strides (e.g. `for (i = 0; i < N; i += step)`):
  * The number of loop iterations is `ceil((bound - start) / step)`, NOT `N`.
  * Never assume the loop increments by 1 when the loop update uses `+= step`.
  * If `step` or inner bounds change across outer loop iterations, compute the true sum of inner iterations across all outer iterations.
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

    def _assembly_prompt(
        self, name: str, body: str, all_functions: dict[str, str],
        plan: StructurePlan, source_facts: str,
        analysis_context: str, gcc_evidence: list[dict],
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
        statement_checklist = self._source_statement_checklist(body)
        access_obligations = self._indexed_access_checklist(statement_checklist)
        arithmetic_obligations = {
            "minimum_static_operations": self._source_arithmetic_obligations(
                body, source_facts, apply_loop_counts=False
            ),
            "minimum_dynamic_operations": self._source_arithmetic_obligations(
                body, source_facts
            ),
        }
        return f"""You are pass 2 of a staged GCC 11.4 -O0 compiler analysis for ARM Cortex-M4 (Thumb-2).
Emit the actual Thumb-2 assembly sections for EXACTLY ONE invocation of function {name}.

Function under analysis:
```c
{body}
```

Relevant call-chain source (use only to propagate caller arguments and state
into this function's path; synthesize assembly only for {name}):
```c
{chr(10).join(all_functions.values())}
```

Structure plan (authoritative call and loop bounds):
{plan.model_dump_json(indent=2)}

Source-derived proven loop execution obligations:
{json.dumps(loop_obligations, indent=2)}

Source-derived control-flow regions:
{json.dumps(control_obligations, indent=2)}

Mandatory source-statement coverage checklist (preserve this order and
translate every entry; do not summarize or merge entries away):
{json.dumps(statement_checklist, indent=2)}

Mandatory indexed memory-access expressions (each occurrence in the source
statement checklist needs its own GCC -O0 address formation and load/store):
{json.dumps(access_obligations, indent=2)}

Source-derived minimum arithmetic instruction obligations for the selected
worst-case path (both static operations and proven dynamic counts):
{json.dumps(arithmetic_obligations, indent=2)}

Direct callees in this function:
{json.dumps(direct_callees)}

Hardware profile:
{json.dumps(self.hardware, indent=2)}

GCC 11.4 -O0 transformation examples:
{json.dumps(gcc_evidence, indent=2)}

Initialization/path context (outside the timed interval):
{analysis_context or "No additional context supplied. Treat unknown values as unknown and choose one most expensive feasible path."}

Rules for generating FunctionAssemblyPlan:
- `selected_source_path` is mandatory. List, in execution order, the source
  conditions and the one arm selected at each decision. Use initialization/path
  context whenever it fixes a value; otherwise choose one most expensive
  feasible arm. Never describe two mutually exclusive arms as selected.
- Structure {name} into its natural sequential assembly sections:
  1. For a function without loops (straight-line or branching with if/else or switch-case):
     - There must be EXACTLY ONE section named "straight_line" with execution_count = 1.
     - Do NOT emit multiple sections!
     - A single invocation executes exactly ONE path. Synthesize ONLY the single selected feasible path (worst-case path) in this single section: entry PUSH, stack allocation, condition tests, ONLY the single chosen branch arm (e.g., only one case of a switch, or only the chosen arm of an if-else), stack teardown, and return (bx lr or pop {{..., pc}}).
     - Completely omit all unselected alternative branch arms! Do not emit multiple alternative sections!
  2. For a function with a single loop:
     - Section "prologue_and_init" with execution_count = 1: entry PUSH, stack allocation, initial variable and index setup.
     - Section "loop_body" with execution_count = N, where N is the loop body trip count from 'Source-derived proven loop execution obligations'. Contains the loop body arithmetic, memory loads/stores, callee calls, and increment/test.
     - Section "epilogue_and_return" with execution_count = 1: stack teardown, POP, and return (bx lr or pop {{..., pc}}).
   3. For functions with nested loops:
      - Section "prologue_and_init" with execution_count = 1: entry PUSH, stack allocation, outermost loop variable and index setup.
      - For each outer/enclosing loop level: Section "outer_loop_overhead" (or "middle_loop_overhead") with execution_count matching that loop's compound execution count (e.g. trip count from 'Source-derived proven loop execution obligations'): contains outer loop counter reload from stack, increment/addition, comparison, test branch, and inner loop counter init.
      - For the innermost loop: Section "inner_loop_body" with execution_count matching the total compound inner body execution count from 'Source-derived proven loop execution obligations' (prod(trip_counts)). Must fully synthesize all actual arithmetic, math, and memory operations written in the C source for ONE single iteration (never emit an empty stub with only index comparisons or branch tests).
      - Section "epilogue_and_return" with execution_count = 1: stack teardown, POP, and return (bx lr or pop {{..., pc}}).
- CRITICAL ANTI-UNROLLING RULE (MANDATORY FOR ALL LOOPS):
  * Every loop section ("loop_body" or "inner_loop_body") represents EXACTLY ONE single iteration of that loop body!
  * Do NOT unroll or repeat loop iterations sequentially inside the section; synthesize all operations of the loop body for one iteration once.
  * Python will automatically multiply all instructions in the section by its `execution_count`. Unrolling inside the section causes massive double-counting!
- STRICT C-SOURCE SCOPE (NO HALLUCINATED EXPANSION):
  * Only synthesize instructions for operations and variables that actually exist in the supplied C source.
  * Never invent extra array elements, continuous loads/stores beyond declared dimensions, or repetitive memory accesses.
  * A function's straight-line trace must conclude its computation concisely and reach its epilogue return.
- Emit real ARM Cortex-M4 Thumb-2 instructions in 'instructions' list for each section:
  * Memory access: ldr, ldrb, ldrh, ldrsb, ldrsh, str, strb, strh
  * Arithmetic/logic: adds, subs, mov, movs, lsls, lsrs, asrs, eor, eors, and, ands, orr, bic, cmp
  * Type extensions: uxtb, uxth, sxtb, sxth
  * Multiplication/Division: mul, mul.w, mla, mls, sdiv, udiv
  * Calls and branches: bl <CalleeName>, b, beq, bne, bls, bx lr, pop
- The source-derived arithmetic obligations are lower bounds, not suggested
  totals. The emitted dynamic trace must contain at least that many matching
  multiply/divide instructions after section execution counts are applied.
- Translate the mandatory source-statement checklist statement by statement:
  first load every operand, then emit every arithmetic/logical operation, then
  store the C result. Do not replace a compound expression with representative
  instructions. For example, `a*b - c*d` requires both multiplications and the
  subtraction; emitting only address arithmetic or loop control is invalid.
- Before returning JSON, audit that every checklist entry is represented in an
  assembly section and every indexed access has explicit address formation plus
  its data load/store. This audit changes the assembly; do not output prose.
- The instructions across all sections are ONE LINEAR DYNAMIC TRACE, not a
  static disassembly containing every basic block. After a taken branch,
  continue with instructions at its target; omit the skipped arm. After a
  not-taken branch, continue with fallthrough instructions.
- For every conditional branch instruction, add one `conditional_branches`
  entry to that section in order of appearance. `instruction_index` is its
  approximate zero-based index in the section's `instructions` list.
  `taken_count + not_taken_count` must equal the section's `execution_count`.
  Straight-line path decisions therefore have either (1, 0) or (0, 1). A loop
  test may use repeated counts.
- Do not add `conditional_branches` entries for unconditional `b`, calls `bl`,
  returns, comparisons, or non-branch instructions.
- GCC 11.4 -O0 compiler rules (strictly preserve compiler stack & memory patterns):
  * In -O0, all local variables, parameters, and temporary evaluation results are homed on the stack frame ([r7, #offset]) and reloaded on EVERY reference. There is NO register allocation across C statements or across loop iterations!
  * Redundant Stack Reloads on Pointer/Array Updates:
    When assigning to an array or pointer (e.g. arr[i] = expr; or *ptr = expr;):
    - The compiler does NOT keep the base pointer or index in registers across expressions.
    - To write the result back, it emits explicit reloads from the stack for the base pointer (ldr rx, [r7, #base]) and index (ldr ry, [r7, #idx]), adds them, and stores (strb/str).
    - Temporary byte/word variables (e.g. temp = arr[i]; arr[i] = arr[j];) are explicitly stored into a stack slot (str/strb) and reloaded from that stack slot (ldr/ldrb); never transferred directly between registers without stack spill!
  * Const/Table Array & Literal Pool Accesses:
    When accessing global constants or lookup tables (e.g. table[k], sbox[x]), GCC -O0 loads the table base address from the Flash literal pool on EVERY lookup:
    - ldr rX, [pc, #offset] (PC-relative constant pool load, 2 cycles)
    - Followed by indexed load (ldrb/ldr rY, [rX, rZ]).
  * Loop Control & Latch in -O0:
    In for loops (e.g. for (i = 0; i < N; i++)):
    - Increment: reload i from stack ([r7, #offset]), adds #1, store back to stack.
    - Test: reload i from stack, cmp with bound, conditional branch (bne/bls/ble) back to loop start.
  * Operations on uint8_t/int8_t produce explicit uxtb/sxtb zero/sign extensions.
  * Calls to direct callees MUST use 'bl <CalleeName>'. In -O0, GCC NEVER inlines functions. NEVER expand or inline callee bodies! Each callee is compiled and analyzed separately; emit only a single 'bl <CalleeName>' instruction at each call site.
  * Single Epilogue Return: In GCC -O0, functions have exactly ONE common exit epilogue at the very end (stack deallocation, pop/bx lr). Branch arms and conditionals jump to the common epilogue; they do NOT contain multiple separate return instructions.
- Balanced epilogue: The last section must conclude with a return instruction (bx lr or pop {{..., pc}}).
- No degenerate repetition: A straight-line block cannot contain repeated identical instructions without purpose.
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
        for _, _, total, description in StagedPredictor._variable_nested_loop_counts(
            body, macros
        ):
            obligations.append(
                f"STAGE-VARYING NESTED LOOP: {description} -> AUTHORITATIVE "
                f"COMPOUND INNER BODY EXECUTION COUNT = {total} times"
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
    def _classify_instruction(instruction: str, is_loop: bool = False) -> dict[str, int]:
        """Map one predicted mnemonic to timing classes without LLM arithmetic."""
        line = instruction.strip()
        line = re.sub(r"^[0-9a-fA-F]+:\s*", "", line)
        line = re.sub(r"/\*.*?\*/", "", line)
        line = re.sub(r"@.*$", "", line).strip()
        if not line or line.endswith(":"):
            return {}

        opcode, separator, operands = line.partition(" ")
        op = opcode.strip().lower()
        op = re.sub(r"\.(?:n|w)$", "", op)
        args = operands.strip().lower()

        def register_count() -> int:
            match = re.search(r"\{([^}]+)\}", args)
            if not match:
                return 1
            total = 0
            for part in (item.strip() for item in match.group(1).split(",")):
                span = re.fullmatch(r"r(\d+)\s*-\s*r(\d+)", part)
                if span:
                    total += abs(int(span.group(2)) - int(span.group(1))) + 1
                elif re.fullmatch(r"(?:r\d+|sp|lr|pc)", part):
                    total += 1
            return max(1, total)

        if op.startswith(("ldr", "vldr")):
            return {"sram_or_stack_load": 1}
        if op.startswith(("str", "vstr")):
            return {"sram_or_stack_store": 1}
        if op in {"push", "pop", "ldm", "ldmia", "ldmdb", "stm", "stmia", "stmdb"}:
            regs = register_count()
            result = {
                "push_or_pop_register_transfer": regs,
                "multi_register_instruction_overhead": 1,
            }
            if op in {"pop", "ldm", "ldmia", "ldmdb"} and re.search(r"\bpc\b", args):
                result["function_return_with_refill"] = 1
            return result
        if op in {"bl", "blx"}:
            return {"function_call_bl_with_refill": 1}
        if op == "bx" and re.fullmatch(r"lr", args):
            return {"function_return_with_refill": 1}
        if op.startswith((
            "mul", "mla", "mls", "smull", "umull", "smlal", "umlal",
        )):
            return {"multiply": 1}
        if op.startswith(("sdiv", "udiv")):
            return {"integer_divide_worst_case": 1}
        if op == "b":
            return {"unconditional_branch_with_refill": 1}
        if op in {"cbz", "cbnz", "tbb", "tbh"} or re.fullmatch(
            r"b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)", op
        ):
            return (
                {"conditional_branch_taken": 1}
                if is_loop
                else {"conditional_branch_not_taken": 1}
            )
        return {"alu_move_compare_shift": 1}

    @staticmethod
    def _is_conditional_branch_instruction(instruction: str) -> bool:
        line = instruction.strip()
        line = re.sub(r"^[0-9a-fA-F]+:\s*", "", line)
        line = re.sub(r"/\*.*?\*/", "", line)
        line = re.sub(r"@.*$", "", line).strip()
        if not line or line.endswith(":"):
            return False
        opcode = re.sub(r"\.(?:n|w)$", "", line.partition(" ")[0].lower())
        return opcode in {"cbz", "cbnz", "tbb", "tbh"} or bool(re.fullmatch(
            r"b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)",
            opcode,
        ))

    @staticmethod
    def _section_instructions(section: AssemblySection) -> list[str]:
        """Return the flat instruction trace for an assembly section."""
        return section.instructions

    @staticmethod
    def _replace_section_instruction(
        section: AssemblySection, flat_index: int, instruction: str
    ) -> None:
        section.instructions[flat_index] = instruction

    @staticmethod
    def _append_section_instruction(
        section: AssemblySection, instruction: str
    ) -> None:
        section.instructions.append(instruction)

    @staticmethod
    def _has_repeated_instruction_ngram(
        instructions: list[str], *, width: int = 8, repeats: int = 3
    ) -> bool:
        """Detect the consecutive repetition collapse seen in local-model output."""
        normalized = [item.strip().lower() for item in instructions if item.strip()]
        span = width * repeats
        for start in range(0, len(normalized) - span + 1):
            unit = normalized[start:start + width]
            if all(
                normalized[start + n * width:start + (n + 1) * width] == unit
                for n in range(1, repeats)
            ):
                return True
        return False

    @staticmethod
    def _map_conditional_branches(
        section: AssemblySection,
    ) -> dict[int, ConditionalBranchExecution]:
        instructions = StagedPredictor._section_instructions(section)
        actual_branch_indices = [
            index for index, instruction in enumerate(instructions)
            if StagedPredictor._is_conditional_branch_instruction(instruction)
        ]
        branch_map: dict[int, ConditionalBranchExecution] = {}
        unmapped_actual = list(actual_branch_indices)
        remaining_declared = []

        # Phase 1: Exact index match
        for branch in section.conditional_branches:
            if branch.instruction_index in unmapped_actual:
                branch_map[branch.instruction_index] = branch
                unmapped_actual.remove(branch.instruction_index)
            else:
                remaining_declared.append(branch)

        # Phase 2: Positional match for remaining declared branches to unmapped actual branches
        for branch in remaining_declared:
            if unmapped_actual:
                target_index = unmapped_actual.pop(0)
                branch_map[target_index] = branch

        return branch_map

    @staticmethod
    def _validate_assembly_plan(plan: FunctionAssemblyPlan) -> list[str]:
        """Validate that the model returned one countable dynamic trace."""
        errors: list[str] = []
        return_locations: list[tuple[int, int]] = []

        for section_index, section in enumerate(plan.sections):
            instructions = StagedPredictor._section_instructions(section)
            if StagedPredictor._has_repeated_instruction_ngram(instructions):
                errors.append(
                    f"{plan.function_name}/{section.section_name}: repeated instruction "
                    "sequence indicates generation collapse"
                )
            conditional_indices = {
                index for index, instruction in enumerate(instructions)
                if StagedPredictor._is_conditional_branch_instruction(instruction)
            }
            if conditional_indices and not section.conditional_branches:
                errors.append(
                    f"{plan.function_name}/{section.section_name}: conditional "
                    f"branch metadata missing for branch instructions at metadata indices {sorted(conditional_indices)}"
                )
            for branch in section.conditional_branches:
                executions = branch.taken_count + branch.not_taken_count
                if executions != section.execution_count:
                    if section.execution_count == 1 and executions > 1:
                        branch.taken_count = 0
                        branch.not_taken_count = 1
                    else:
                        errors.append(
                            f"{plan.function_name}/{section.section_name}: branch executes "
                            f"{executions} times but section executes {section.execution_count} times"
                        )

            for instruction_index, instruction in enumerate(instructions):
                classified = StagedPredictor._classify_instruction(instruction)
                if "function_return_with_refill" in classified:
                    return_locations.append((section_index, instruction_index))

        last_section_instructions = StagedPredictor._section_instructions(
            plan.sections[-1]
        )
        last_instr = last_section_instructions[-1].strip().lower()
        is_epilogue_jump = (
            last_instr.startswith("b ")
            or last_instr.startswith("b.n ")
            or last_instr.startswith("b.w ")
        )
        if len(return_locations) == 0:
            if is_epilogue_jump:
                pass
            elif plan.sections and last_section_instructions:
                StagedPredictor._append_section_instruction(
                    plan.sections[-1], "pop {r7, pc}"
                )
                return_locations.append((
                    len(plan.sections) - 1,
                    len(StagedPredictor._section_instructions(plan.sections[-1])) - 1,
                ))
            else:
                errors.append(
                    f"{plan.function_name}: selected dynamic trace must contain exactly "
                    f"one return, found {len(return_locations)}"
                )
        elif len(return_locations) > 1:
            last_pos = (
                len(plan.sections) - 1,
                len(StagedPredictor._section_instructions(plan.sections[-1])) - 1,
            )
            if last_pos in return_locations:
                for s_idx, i_idx in return_locations:
                    if (s_idx, i_idx) != last_pos:
                        StagedPredictor._replace_section_instruction(
                            plan.sections[s_idx], i_idx, "nop"
                        )
                return_locations = [last_pos]
            else:
                errors.append(
                    f"{plan.function_name}: selected dynamic trace must contain exactly "
                    f"one return, found {len(return_locations)}"
                )
        elif return_locations[0] != (
            len(plan.sections) - 1,
            len(StagedPredictor._section_instructions(plan.sections[-1])) - 1,
        ):
            errors.append(
                f"{plan.function_name}: selected dynamic trace contains instructions "
                "after its return"
            )
        return errors

    @staticmethod
    def _assembly_plan_to_ledger(
        plan: FunctionAssemblyPlan, all_functions: dict[str, str]
    ) -> FunctionLedger:
        """Deterministically map assembly sections into a dynamic instruction ledger."""
        counts: dict[str, int] = defaultdict(int)
        evidence: dict[str, list[str]] = defaultdict(list)
        callee_counts: dict[str, int] = defaultdict(int)

        sections = plan.sections
        if (
            len(sections) > 1
            and all("straight" in s.section_name.lower() for s in sections)
        ):
            sections = [sections[0]]

        for section in sections:
            exec_count = max(0, section.execution_count)
            is_loop = (
                "loop" in section.section_name.lower()
                or "kernel" in section.section_name.lower()
            )
            original_to_cleaned: dict[int, int] = {}
            cleaned_instructions: list[str] = []
            for original_index, instr in enumerate(
                StagedPredictor._section_instructions(section)
            ):
                clean = instr.strip()
                if not clean or clean.endswith(":"):
                    continue
                if (
                    len(cleaned_instructions) >= 2
                    and clean == cleaned_instructions[-1] == cleaned_instructions[-2]
                ):
                    continue
                original_to_cleaned[original_index] = len(cleaned_instructions)
                cleaned_instructions.append(clean)

            mapped_branches = StagedPredictor._map_conditional_branches(section)
            branch_metadata = {
                original_to_cleaned[orig_idx]: branch
                for orig_idx, branch in mapped_branches.items()
                if orig_idx in original_to_cleaned
            }

            for instruction_index, instr in enumerate(cleaned_instructions):
                if StagedPredictor._is_conditional_branch_instruction(instr):
                    branch = branch_metadata.get(instruction_index)
                    if branch is not None:
                        if branch.taken_count:
                            counts["conditional_branch_taken"] += branch.taken_count
                            evidence["conditional_branch_taken"].append(
                                f"{section.section_name}: {branch.taken_count} ({instr}; "
                                f"{branch.evidence})"
                            )
                        if branch.not_taken_count:
                            counts["conditional_branch_not_taken"] += branch.not_taken_count
                            evidence["conditional_branch_not_taken"].append(
                                f"{section.section_name}: {branch.not_taken_count} ({instr}; "
                                f"{branch.evidence})"
                            )
                        continue
                classified = StagedPredictor._classify_instruction(instr, is_loop=is_loop)
                for cls_name, amount in classified.items():
                    counts[cls_name] += amount * exec_count
                    evidence[cls_name].append(
                        f"{section.section_name} x{exec_count}: {amount} ({instr})"
                    )
                match = re.search(r"\bbl\s+([A-Za-z_]\w*)", instr, re.IGNORECASE)
                if match:
                    callee = match.group(1)
                    if callee in all_functions and callee != plan.function_name:
                        callee_counts[callee] += exec_count
                if "function_return_with_refill" in classified and not is_loop:
                    # In straight-line execution, return concludes the function; instructions after are dead code.
                    break

        callees = [
            CalleeCount(
                function_name=callee,
                calls_per_invocation=cnt,
                evidence="synthesized in assembly section calls",
            )
            for callee, cnt in callee_counts.items()
        ]

        bl_calls = sum(callee_counts.values())
        if bl_calls > 0:
            counts["function_call_bl_with_refill"] = max(
                counts["function_call_bl_with_refill"], bl_calls
            )

        instruction_counts = [
            PerCallInstructionCount(
                instruction_class=name,
                dynamic_count_per_invocation=count,
                evidence="; ".join(evidence[name])[:500],
            )
            for name, count in counts.items()
            if count > 0
        ]
        if not any(item.instruction_class == "function_return_with_refill" for item in instruction_counts):
            instruction_counts.append(
                PerCallInstructionCount(
                    instruction_class="function_return_with_refill",
                    dynamic_count_per_invocation=1,
                    evidence="auto-injected return epilogue for completed function",
                )
            )

        conditional = counts.get("conditional_branch_taken", 0) + counts.get(
            "conditional_branch_not_taken", 0
        )

        return FunctionLedger(
            function_name=plan.function_name,
            selected_path=plan.selected_source_path,
            callees=callees,
            conditional_branch_evaluations_per_invocation=conditional,
            instruction_counts=instruction_counts,
            unresolved=plan.unresolved,
        )

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
        return StagedPredictor._matching_delimiter(text, opening, "{", "}")

    @staticmethod
    def _matching_delimiter(
        text: str, opening: int, open_char: str, close_char: str
    ) -> int | None:
        depth = 0
        for index in range(opening, len(text)):
            if text[index] == open_char:
                depth += 1
            elif text[index] == close_char:
                depth -= 1
                if depth == 0:
                    return index
        return None

    @staticmethod
    def _masked_c_source(text: str) -> str:
        """Mask comments and literals while preserving source offsets."""
        result = list(text)
        index = 0
        while index < len(text):
            if text.startswith("//", index):
                end = text.find("\n", index)
                end = len(text) if end < 0 else end
                for position in range(index, end):
                    result[position] = " "
                index = end
                continue
            if text.startswith("/*", index):
                end = text.find("*/", index + 2)
                end = len(text) - 2 if end < 0 else end
                for position in range(index, min(len(text), end + 2)):
                    if result[position] != "\n":
                        result[position] = " "
                index = end + 2
                continue
            if text[index] in {'"', "'"}:
                quote = text[index]
                result[index] = " "
                index += 1
                while index < len(text):
                    result[index] = " " if text[index] != "\n" else "\n"
                    if text[index] == "\\":
                        if index + 1 < len(text):
                            result[index + 1] = (
                                " " if text[index + 1] != "\n" else "\n"
                            )
                        index += 2
                        continue
                    if text[index] == quote:
                        index += 1
                        break
                    index += 1
                continue
            index += 1
        return "".join(result)

    @staticmethod
    def _source_statement_checklist(body: str) -> list[str]:
        """Return executable C statements without asking Python to compile them."""
        masked = StagedPredictor._masked_c_source(body)
        opening = masked.find("{")
        closing = (
            StagedPredictor._matching_brace(masked, opening)
            if opening >= 0 else None
        )
        if opening >= 0 and closing is not None:
            masked = masked[opening + 1:closing]

        # Remove balanced control headers before splitting on semicolons. This
        # keeps one-line functions and the two semicolons in `for (...)` from
        # becoming bogus source statements.
        compact: list[str] = []
        cursor = 0
        control = re.compile(r"\b(?:for|if|while|switch)\s*\(")
        while cursor < len(masked):
            match = control.search(masked, cursor)
            if not match:
                compact.append(masked[cursor:])
                break
            compact.append(masked[cursor:match.start()])
            paren = masked.find("(", match.start())
            depth = 0
            end = paren
            while end < len(masked):
                if masked[end] == "(":
                    depth += 1
                elif masked[end] == ")":
                    depth -= 1
                    if depth == 0:
                        end += 1
                        break
                end += 1
            cursor = end
        masked = "".join(compact).replace("{", ";").replace("}", ";")
        statements: list[str] = []
        for raw_statement in masked.split(";"):
            statement = raw_statement.strip()
            statement = re.sub(r"^else\b", "", statement).strip()
            if not statement or statement in {"else", "do"}:
                continue
            if re.match(r"^(?:case\b|default\s*:)", statement):
                continue
            if re.fullmatch(
                r"(?:(?:static|const|volatile|signed|unsigned)\s+)*"
                r"(?:void|char|short|int|long|float|double|[A-Za-z_]\w*_t)"
                r"(?:\s+|\s*\*+\s*)[A-Za-z_]\w*(?:\s*\[[^]]*\])*",
                statement,
            ):
                # A declaration without an initializer emits no executable
                # instruction and therefore needs no assembly block.
                continue
            statements.append(re.sub(r"\s+", " ", statement)[:300])
        return statements[:64]

    @staticmethod
    def _indexed_access_checklist(statements: list[str]) -> list[str]:
        """Keep every variable-indexed source occurrence visible to the LLM."""
        pattern = re.compile(
            r"\b[A-Za-z_]\w*(?:\s*\[[^\]]+\])+"
            r"(?:\s*(?:\.|->)\s*[A-Za-z_]\w*)?"
        )
        obligations = []
        for statement in statements:
            for match in pattern.finditer(statement):
                expression = re.sub(r"\s+", "", match.group(0))
                indexes = re.findall(r"\[([^\]]+)\]", expression)
                if not any(re.search(r"[A-Za-z_]", index) for index in indexes):
                    continue
                obligations.append(f"{expression} :: {statement}"[:400])
        return obligations[:128]

    @staticmethod
    def _source_arithmetic_obligations(
        body: str, source_facts: str, *, apply_loop_counts: bool = True
    ) -> dict[str, int]:
        """Derive conservative dynamic MUL/DIV lower bounds from C source.

        Only variable-by-variable operators outside conditional arms are used.
        Constant arithmetic is deliberately excluded because GCC may legally
        strength-reduce it to shifts/adds even at -O0. Conditional-arm
        arithmetic is excluded because this pass does not independently prove
        which mutually exclusive arm the model selected.
        """
        text = StagedPredictor._masked_c_source(body)
        macros = StagedPredictor._integer_macros(source_facts)
        loops = StagedPredictor._proven_for_loops(text, macros)
        variable_nested = StagedPredictor._variable_nested_loop_counts(text, macros)
        conditional_arms = [
            arm
            for _, _, arms in StagedPredictor._braced_if_chains(text)
            for arm in arms
        ]
        token_pattern = re.compile(
            r"0[xX][0-9A-Fa-f]+[uUlL]*|\d+[uUlL]*|[A-Za-z_]\w*|"
            r"<<=|>>=|==|!=|<=|>=|&&|\|\||\+\+|--|->|[{}()\[\];,*/%+\-&|^~!=<>?:.]"
        )
        tokens = [
            (match.group(0), match.start())
            for match in token_pattern.finditer(text)
        ]
        c_type_words = {
            "void", "char", "short", "int", "long", "float", "double",
            "signed", "unsigned", "const", "volatile", "struct", "union",
            "enum", "static", "register", "extern", "auto", "restrict",
        }

        def is_constant(token: str) -> bool:
            clean = re.sub(r"[uUlL]+$", "", token)
            return bool(re.fullmatch(r"0[xX][0-9A-Fa-f]+|\d+", clean)) or (
                token in macros
            )

        def in_conditional_arm(position: int) -> bool:
            return any(start <= position < end for start, end in conditional_arms)

        obligations = {"multiply": 0, "integer_divide_worst_case": 0}
        for index, (token, position) in enumerate(tokens):
            if token not in {"*", "/"} or index == 0 or index + 1 >= len(tokens):
                continue
            if in_conditional_arm(position):
                continue
            previous = tokens[index - 1][0]
            following = tokens[index + 1][0]
            previous_is_value = bool(re.fullmatch(
                r"[A-Za-z_]\w*|0[xX][0-9A-Fa-f]+[uUlL]*|\d+[uUlL]*|\]|\)",
                previous,
            ))
            following_is_value = bool(re.fullmatch(
                r"[A-Za-z_]\w*|0[xX][0-9A-Fa-f]+[uUlL]*|\d+[uUlL]*|\(",
                following,
            ))
            if not (previous_is_value and following_is_value):
                continue
            if token == "*" and (
                previous in c_type_words
                or previous.endswith("_t")
            ):
                # Pointer declarator, not multiplication.
                continue
            if is_constant(previous) or is_constant(following):
                continue
            multiplier = 1
            if apply_loop_counts:
                exact_nested = next(
                    (total for start, end, total, _ in variable_nested
                     if start <= position < end),
                    None,
                )
                if exact_nested is not None:
                    multiplier = exact_nested
                else:
                    for start, end, trip_count, _ in loops:
                        if start <= position < end:
                            multiplier *= trip_count
            instruction_class = (
                "multiply" if token == "*" else "integer_divide_worst_case"
            )
            obligations[instruction_class] += multiplier
        return obligations

    @staticmethod
    def _validate_source_operation_coverage(
        name: str, body: str, plan: FunctionAssemblyPlan,
        ledger: FunctionLedger, source_facts: str
    ) -> list[str]:
        """Reject a semantically incomplete assembly trace before SUPPORTED."""
        required_dynamic = StagedPredictor._source_arithmetic_obligations(
            body, source_facts
        )
        required_static = StagedPredictor._source_arithmetic_obligations(
            body, source_facts, apply_loop_counts=False
        )
        emitted_dynamic = {
            item.instruction_class: item.dynamic_count_per_invocation
            for item in ledger.instruction_counts
        }
        emitted_static = {"multiply": 0, "integer_divide_worst_case": 0}
        for section in plan.sections:
            for instruction in StagedPredictor._section_instructions(section):
                classified = StagedPredictor._classify_instruction(instruction)
                for instruction_class in emitted_static:
                    emitted_static[instruction_class] += classified.get(
                        instruction_class, 0
                    )
        errors = []
        for instruction_class, minimum in required_static.items():
            actual = emitted_static.get(instruction_class, 0)
            if actual < minimum:
                errors.append(
                    f"{name}: source requires at least {minimum} static "
                    f"{instruction_class} operations on the proven non-conditional "
                    f"path, but synthesized assembly contains {actual}"
                )
        for instruction_class, minimum in required_dynamic.items():
            actual = emitted_dynamic.get(instruction_class, 0)
            if actual < minimum:
                errors.append(
                    f"{name}: source requires at least {minimum} dynamic "
                    f"{instruction_class} operations on the proven non-conditional "
                    f"path, but synthesized assembly contains {actual}"
                )
        return errors

    @staticmethod
    def _braced_if_chains(body: str) -> list[tuple[int, int, list[tuple[int, int]]]]:
        """Return braced if/else-if/else chains and their arm ranges."""
        text = StagedPredictor._masked_c_source(body)
        chains: list[tuple[int, int, list[tuple[int, int]]]] = []
        for match in re.finditer(r"\bif\s*\(", text):
            # An `else if` belongs to the chain that started at the preceding if.
            if re.search(r"\belse\s*$", text[:match.start()]):
                continue
            cursor = match.start()
            arms: list[tuple[int, int]] = []
            chain_end = cursor
            while True:
                condition_open = text.find("(", cursor)
                if condition_open < 0:
                    break
                condition_close = StagedPredictor._matching_delimiter(
                    text, condition_open, "(", ")"
                )
                if condition_close is None:
                    break
                arm_open = condition_close + 1
                while arm_open < len(text) and text[arm_open].isspace():
                    arm_open += 1
                if arm_open >= len(text) or text[arm_open] != "{":
                    break
                arm_close = StagedPredictor._matching_brace(text, arm_open)
                if arm_close is None:
                    break
                arms.append((arm_open + 1, arm_close))
                chain_end = arm_close + 1
                cursor = chain_end
                while cursor < len(text) and text[cursor].isspace():
                    cursor += 1
                else_match = re.match(r"else\b", text[cursor:])
                if not else_match:
                    break
                cursor += else_match.end()
                while cursor < len(text) and text[cursor].isspace():
                    cursor += 1
                if re.match(r"if\s*\(", text[cursor:]):
                    continue
                if cursor < len(text) and text[cursor] == "{":
                    arm_close = StagedPredictor._matching_brace(text, cursor)
                    if arm_close is not None:
                        arms.append((cursor + 1, arm_close))
                        chain_end = arm_close + 1
                break
            if arms:
                chains.append((match.start(), chain_end, arms))
        return chains

    @staticmethod
    def _max_direct_callee_calls_on_one_branch_path(
        body: str, callee_name: str, source_facts: str
    ) -> int:
        """Conservative maximum across mutually exclusive braced branch arms."""
        sites = list(re.finditer(rf"\b{re.escape(callee_name)}\s*\(", body))
        macros = StagedPredictor._integer_macros(source_facts)
        loops = StagedPredictor._proven_for_loops(body, macros)
        weighted_sites = []
        for site in sites:
            multiplier = 1
            for start, end, trip_count, _ in loops:
                if start <= site.start() < end:
                    multiplier *= trip_count
            weighted_sites.append((site.start(), multiplier))

        # Only outermost chains are needed here. Nested chains remaining inside
        # one arm make this an upper bound, never an unsafe under-count.
        outer_chains: list[tuple[int, int, list[tuple[int, int]]]] = []
        for chain in sorted(
            StagedPredictor._braced_if_chains(body),
            key=lambda item: (item[0], -item[1]),
        ):
            if any(start <= chain[0] and chain[1] <= end
                   for start, end, _ in outer_chains):
                continue
            outer_chains.append(chain)

        assigned: set[int] = set()
        maximum = 0
        for _, _, arms in outer_chains:
            arm_totals: list[int] = []
            arm_site_indices: set[int] = set()
            for arm_start, arm_end in arms:
                indices = {
                    index for index, (position, _) in enumerate(weighted_sites)
                    if arm_start <= position < arm_end
                }
                arm_site_indices.update(indices)
                arm_totals.append(sum(weighted_sites[index][1] for index in indices))
            if arm_site_indices:
                maximum += max([0, *arm_totals])
                assigned.update(arm_site_indices)
        maximum += sum(
            weight for index, (_, weight) in enumerate(weighted_sites)
            if index not in assigned
        )
        return maximum

    @staticmethod
    def _proven_for_loops(
        body: str, macro_values: dict[str, int]
    ) -> list[tuple[int, int, int, str]]:
        """Return braced, canonical for-loop body ranges and trip counts."""
        body = StagedPredictor._masked_c_source(body)
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
    def _variable_nested_loop_counts(
        body: str, macro_values: dict[str, int]
    ) -> list[tuple[int, int, int, str]]:
        """Resolve geometric bounds/strides carried by a proven outer loop.

        This covers source patterns where an outer stage doubles variables used
        as a middle-loop stride and an inner-loop bound. It derives execution
        counts only; assembly selection remains model-owned.
        """
        results: list[tuple[int, int, int, str]] = []
        outer_loops = StagedPredictor._proven_for_loops(body, macro_values)
        middle_pattern = re.compile(
            r"\bfor\s*\(\s*(?:[A-Za-z_]\w*\s+)*([A-Za-z_]\w*)\s*=\s*"
            r"(\d+)[uUlL]*\s*;\s*\1\s*<\s*([A-Za-z_]\w*|\d+[uUlL]*)"
            r"\s*;\s*\1\s*\+=\s*([A-Za-z_]\w*)\s*\)\s*\{"
        )
        inner_pattern = re.compile(
            r"\bfor\s*\(\s*(?:[A-Za-z_]\w*\s+)*([A-Za-z_]\w*)\s*=\s*"
            r"(\d+)[uUlL]*\s*;\s*\1\s*<\s*([A-Za-z_]\w*)"
            r"\s*;\s*(?:\+\+\s*\1|\1\s*\+\+)\s*\)\s*\{"
        )

        def integer_value(token: str) -> int | None:
            clean = re.sub(r"[uUlL]+$", "", token)
            return int(clean) if clean.isdigit() else macro_values.get(clean)

        for outer_start, outer_end, stages, outer_desc in outer_loops:
            for middle in middle_pattern.finditer(body, outer_start, outer_end):
                _, middle_start_text, middle_bound_text, stride_var = middle.groups()
                middle_bound = integer_value(middle_bound_text)
                if middle_bound is None:
                    continue
                middle_open = middle.end() - 1
                middle_close = StagedPredictor._matching_brace(body, middle_open)
                if middle_close is None or middle_close > outer_end:
                    continue
                inner = inner_pattern.search(body, middle_open + 1, middle_close)
                if not inner:
                    continue
                _, inner_start_text, bound_var = inner.groups()
                prefix = body[:outer_start]
                stride_initials = list(re.finditer(
                    rf"\b{re.escape(stride_var)}\s*=\s*(\d+)[uUlL]*\s*;", prefix
                ))
                bound_initials = list(re.finditer(
                    rf"\b{re.escape(bound_var)}\s*=\s*(\d+)[uUlL]*\s*;", prefix
                ))
                outer_text = body[outer_start:outer_end]
                stride_shift = re.search(
                    rf"\b{re.escape(stride_var)}\s*<<=\s*(\d+)[uUlL]*", outer_text
                )
                bound_shift = re.search(
                    rf"\b{re.escape(bound_var)}\s*<<=\s*(\d+)[uUlL]*", outer_text
                )
                if not (stride_initials and bound_initials and stride_shift and bound_shift):
                    continue
                stride = int(stride_initials[-1].group(1))
                inner_bound = int(bound_initials[-1].group(1))
                middle_start = int(middle_start_text)
                inner_start = int(inner_start_text)
                stride_factor = 1 << int(stride_shift.group(1))
                bound_factor = 1 << int(bound_shift.group(1))
                per_stage: list[int] = []
                for _ in range(stages):
                    middle_trips = max(
                        0, (middle_bound - middle_start + stride - 1) // stride
                    )
                    inner_trips = max(0, inner_bound - inner_start)
                    per_stage.append(middle_trips * inner_trips)
                    stride *= stride_factor
                    inner_bound *= bound_factor
                inner_open = inner.end() - 1
                inner_close = StagedPredictor._matching_brace(body, inner_open)
                if inner_close is None:
                    continue
                results.append((
                    inner_open + 1,
                    inner_close,
                    sum(per_stage),
                    f"{outer_desc}; per-stage inner executions={per_stage}",
                ))
        return results

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

        # If any call site is inside a conditional branch (if, else, switch, case),
        # its execution is dynamic and path-dependent, NOT statically guaranteed for all paths.
        for token in re.finditer(r"\b(?:if\s*\(|else\b|switch\s*\(|case\b)", body):
            opening = body.find("{", token.end())
            if opening < 0:
                semicolon = body.find(";", token.end())
                if semicolon > 0 and any(token.end() <= site.start() <= semicolon for site in sites):
                    return None, "call is inside a conditional branch"
                continue
            closing = StagedPredictor._matching_brace(body, opening)
            if closing is None:
                continue
            if any(opening < site.start() < closing for site in sites):
                return None, "call is inside a conditional branch"

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
        synthesized_calls = {
            item.function_name: item.calls_per_invocation
            for item in ledger.callees
        }
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
            elif callee_name in synthesized_calls and synthesized_calls[callee_name] > 0:
                calls_per_invocation = synthesized_calls[callee_name]
                path_maximum = StagedPredictor._max_direct_callee_calls_on_one_branch_path(
                    functions[name], callee_name, source_facts
                )
                if calls_per_invocation > path_maximum:
                    errors.append(
                        f"{name}->{callee_name}: selected assembly contains "
                        f"{calls_per_invocation} BL calls, exceeding the source "
                        f"single-path maximum {path_maximum}; clamped to {path_maximum}"
                    )
                    calls_per_invocation = path_maximum
                    evidence = (
                        f"synthesized BL calls ({synthesized_calls[callee_name]}) exceeded "
                        f"source single-path maximum; clamped to single-path bound {path_maximum}"
                    )
                else:
                    evidence = (
                        f"synthesized BL calls on selected path: {calls_per_invocation} "
                        f"({call_sites} syntactic sites: {proof})"
                    )
            else:
                # A syntactic helper that appears only in an unselected branch
                # legitimately has zero calls on this dynamic path.
                if (parent_map.get(callee_name) == {name}
                        and parent_calls > 0 and child_calls > 0):
                    errors.append(
                        f"{name}->{callee_name}: pass 1 selected the callee, but "
                        "the selected assembly path contains no BL call"
                    )
                continue
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

        assembly_plans: dict[str, FunctionAssemblyPlan] = {}
        ledgers: dict[str, FunctionLedger] = {}
        for name, body in functions.items():
            function_evidence = retrieve_assembly_evidence(
                source, self.gcc_pattern_path, function_name=name, limit=8
            )
            assembly_plan, raw = self.client.predict(
                self._assembly_prompt(
                    name, body, functions, plan, source_facts,
                    analysis_context, function_evidence,
                ),
                response_schema=FunctionAssemblyPlan,
            )
            raw_outputs.append(raw)
            assembly_plans[name] = assembly_plan
            errors.extend(self._validate_assembly_plan(assembly_plan))
            ledger = self._assembly_plan_to_ledger(assembly_plan, functions)
            if ledger.function_name != name:
                errors.append(
                    f"ledger function mismatch: expected {name}, "
                    f"received {ledger.function_name}"
                )
            ledger, relation_errors = self._normalize_ledger_relations(
                name, ledger, functions, planned, parent_map, source_facts
            )
            errors.extend(relation_errors)
            errors.extend(self._validate_source_operation_coverage(
                name, body, assembly_plan, ledger, source_facts
            ))
            unknown_callees = {
                item.function_name for item in ledger.callees
            } - set(functions)
            if unknown_callees:
                errors.append(
                    f"{name} ledger calls unknown functions: "
                    f"{sorted(unknown_callees)}"
                )
            ledgers[name] = ledger

        try:
            composed_calls = self._compose_call_counts(target, ledgers)
        except ValueError as exc:
            errors.append(str(exc))
            composed_calls = {}
        composed_all = {
            function_name: composed_calls.get(function_name, 0)
            for function_name in functions
        }
        if composed_calls and composed_all != planned:
            planned = composed_all
            for item in plan.functions:
                if item.function_name in composed_all:
                    item.dynamic_calls = composed_all[item.function_name]
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
        suppress_estimate = bool(errors or unresolved)
        prediction = StagedPrediction(
            analysis_status=status,
            provider=self.client.provider,
            model=self.client.model,
            target_function=target,
            hardware_profile_id=self.hardware["hardware_profile_id"],
            structure_plan=plan,
            function_assembly_plans=list(assembly_plans.values()),
            function_ledgers=list(ledgers.values()),
            function_contributions=contributions,
            aggregate_instruction_ledger=aggregate,
            estimated_source_execution_cycles=(
                None if suppress_estimate else total
            ),
            estimated_source_execution_us=(
                None if suppress_estimate else total / 48.0
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
