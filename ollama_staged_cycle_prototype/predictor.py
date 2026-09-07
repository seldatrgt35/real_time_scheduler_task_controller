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
from gemini_rag_cycle_prototype.gcc_evidence import retrieve_gcc_evidence
from gemini_rag_cycle_prototype.predictor import (
    indexed_access_obligations,
    source_analysis_bundle,
)

from ollama_staged_cycle_prototype.schemas import (
    AggregateInstructionCycles,
    CalleeCount,
    FunctionContribution,
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
        self.gcc_pattern_path = (
            self.root / "gemini_rag_cycle_prototype" / "knowledge"
            / "gcc_o0_patterns.json"
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
        gcc_evidence: list[dict], access_obligations: list[str],
    ) -> str:
        return f"""You are pass 1 of a staged GCC -O0 source timing analysis.
Analyze only control flow and dynamic function-call multiplicities on the most
expensive feasible source path. Do not calculate cycles or write assembly.

Target: {target}
Compiler: ARM GCC 11.4 -O0, Cortex-M4 Thumb-2

Hardware and build profile (same source-only evidence as the Gemini path):
{json.dumps(self.hardware, indent=2)}

Instruction timing profile (do not calculate cycles in this pass):
{json.dumps(self.timing, indent=2)}

GCC 11.4 -O0 transformation evidence:
{json.dumps(gcc_evidence, indent=2)}

Source-derived indexed-access obligations:
{json.dumps(access_obligations, indent=2)}

Required rules:
- The target function has dynamic_calls=1.
- Include every supplied reachable function exactly once.
- A helper's dynamic_calls is its total invocation count during one target call.
- Expand loop call sites using their proven source bounds.
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
        return f"""You are pass 2 of a staged GCC 11.4 -O0 timing analysis.
Predict the aggregate Thumb-2 instruction-class counts for EXACTLY ONE
invocation of function {name} along its most expensive feasible source path.
Do not multiply this ledger by the function's global dynamic call count.

Hardware profile:
{json.dumps(self.hardware, indent=2)}

Authoritative timing profile:
{json.dumps(self.timing, indent=2)}

GCC 11.4 -O0 transformation evidence (identical evidence source used by the
Gemini no-RAG path; these are compiler examples, not board measurements):
{json.dumps(gcc_evidence, indent=2)}

Source-derived indexed-access obligations:
{json.dumps(access_obligations, indent=2)}

Allowed instruction classes and cycles:
{json.dumps(TIMING_PROFILE_CYCLES, indent=2)}

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
- Emit at most one instruction_counts row per instruction class.
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
- Taken plus not-taken conditional counts must equal the declared conditional
  branch evaluations for this invocation.
- Do not calculate final cycles and do not apply a margin.

Function under analysis:
```c
{body}
```

Names of other supplied functions:
{json.dumps([item for item in all_functions if item != name])}
"""

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
            if parent_map.get(callee_name) != {name}:
                errors.append(
                    f"cannot derive per-invocation calls for {callee_name}: "
                    "callee has multiple direct parents"
                )
                continue
            if parent_calls < 1 or child_calls % parent_calls:
                errors.append(
                    f"cannot derive integral call ratio {name}->{callee_name}: "
                    f"parent={parent_calls}, child={child_calls}"
                )
                continue
            callees.append(CalleeCount(
                function_name=callee_name,
                calls_per_invocation=child_calls // parent_calls,
                evidence="derived by Python from pass-1 dynamic calls and "
                         "the syntactic direct-call graph",
            ))

        counts = {
            item.instruction_class: item for item in ledger.instruction_counts
        }
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
        gcc_evidence = retrieve_gcc_evidence(
            source, self.gcc_pattern_path, function_name=target
        )
        access_obligations = indexed_access_obligations(source, target)
        raw_outputs: list[str] = []
        plan, raw = self.client.predict(
            self._structure_prompt(
                target, functions, source_facts, analysis_source,
                analysis_context, gcc_evidence, access_obligations,
            ),
            response_schema=StructurePlan,
        )
        raw_outputs.append(raw)
        errors: list[str] = []
        if plan.target_function != target:
            errors.append("structure plan target does not match requested target")
        planned = {item.function_name: item.dynamic_calls for item in plan.functions}
        if set(planned) != set(functions):
            errors.append(
                "structure plan function set mismatch: expected "
                f"{sorted(functions)}, received {sorted(planned)}"
            )
        if planned.get(target) != 1:
            errors.append("target function dynamic_calls must equal 1")

        parent_map: dict[str, set[str]] = defaultdict(set)
        for caller, body in functions.items():
            for callee in self._direct_callee_names(caller, body, functions):
                parent_map[callee].add(caller)

        ledgers: dict[str, FunctionLedger] = {}
        for name, body in functions.items():
            ledger, raw = self.client.predict(
                self._ledger_prompt(
                    name, body, functions, plan, source_facts,
                    analysis_context, gcc_evidence, access_obligations,
                ),
                response_schema=FunctionLedger,
            )
            raw_outputs.append(raw)
            if ledger.function_name != name:
                errors.append(
                    f"ledger function mismatch: expected {name}, "
                    f"received {ledger.function_name}"
                )
            ledger, relation_errors = self._normalize_ledger_relations(
                name, ledger, functions, planned, parent_map
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
            errors.append(
                "pass-1 dynamic calls disagree with composed per-function calls: "
                f"plan={planned}, composed={composed_calls}"
            )

        aggregate_counts: dict[str, int] = defaultdict(int)
        contributions: list[FunctionContribution] = []
        for name, ledger in ledgers.items():
            calls = composed_calls.get(name, planned.get(name, 0))
            per_call_cycles = sum(
                item.dynamic_count_per_invocation
                * TIMING_PROFILE_CYCLES[item.instruction_class]
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
                cycles_each=TIMING_PROFILE_CYCLES[name],
                total_cycles=count * TIMING_PROFILE_CYCLES[name],
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
        unresolved = list(plan.unresolved)
        unresolved.extend(
            f"{name}: {item}"
            for name, ledger in ledgers.items()
            for item in ledger.unresolved
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
