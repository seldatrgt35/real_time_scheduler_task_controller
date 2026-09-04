from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from gemini_rag_cycle_prototype.rag.measurement_loader import (
    extract_function,
    extract_reachable_helpers,
    function_names,
)

from ollama_staged_cycle_prototype.schemas import (
    AggregateInstructionCycles,
    FunctionContribution,
    FunctionLedger,
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
        self, target: str, functions: dict[str, str]
    ) -> str:
        return f"""You are pass 1 of a staged GCC -O0 source timing analysis.
Analyze only control flow and dynamic function-call multiplicities on the most
expensive feasible source path. Do not calculate cycles or write assembly.

Target: {target}
Compiler: ARM GCC 11.4 -O0, Cortex-M4 Thumb-2

Required rules:
- The target function has dynamic_calls=1.
- Include every supplied reachable function exactly once.
- A helper's dynamic_calls is its total invocation count during one target call.
- Expand loop call sites using their proven source bounds.
- Never invent a helper or omit a supplied reachable helper.
- Put genuinely unprovable source bounds in unresolved.

Functions supplied:
{json.dumps(list(functions), indent=2)}

Source:
```c
{chr(10).join(functions.values())}
```
"""

    def _ledger_prompt(
        self, name: str, body: str, all_functions: dict[str, str],
        plan: StructurePlan,
    ) -> str:
        return f"""You are pass 2 of a staged GCC 11.4 -O0 timing analysis.
Predict the aggregate Thumb-2 instruction-class counts for EXACTLY ONE
invocation of function {name} along its most expensive feasible source path.
Do not multiply this ledger by the function's global dynamic call count.

Hardware profile:
{json.dumps(self.hardware, indent=2)}

Authoritative timing profile:
{json.dumps(self.timing, indent=2)}

Allowed instruction classes and cycles:
{json.dumps(TIMING_PROFILE_CYCLES, indent=2)}

Pass-1 structure plan:
{plan.model_dump_json(indent=2)}

Rules:
- Emit at most one instruction_counts row per instruction class.
- Count GCC -O0 stack parameter homing, local loads/stores, loop control,
  comparisons, address calculations, prologue and epilogue.
- callees lists direct calls made during one invocation of {name}; expand
  loop-contained call sites into calls_per_invocation.
- BL ledger count must equal the sum of direct callee calls.
- Do not include callee body instructions here. Each callee is analyzed in a
  separate request and Python composes it later.
- Include exactly one function return path per invocation.
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

    def predict(self, source: str, target: str) -> tuple[StagedPrediction, list[str]]:
        functions = self._relevant_functions(source, target)
        raw_outputs: list[str] = []
        plan, raw = self.client.predict(
            self._structure_prompt(target, functions), response_schema=StructurePlan
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

        ledgers: dict[str, FunctionLedger] = {}
        for name, body in functions.items():
            ledger, raw = self.client.predict(
                self._ledger_prompt(name, body, functions, plan),
                response_schema=FunctionLedger,
            )
            raw_outputs.append(raw)
            if ledger.function_name != name:
                errors.append(
                    f"ledger function mismatch: expected {name}, "
                    f"received {ledger.function_name}"
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
        status = "VALIDATION_REQUIRED" if errors or plan.unresolved else "SUPPORTED"
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
            estimated_source_execution_cycles=(total if not errors else None),
            estimated_source_execution_us=(total / 48.0 if not errors else None),
            validation_errors=errors,
            warnings=[
                "Experimental source-only estimate; not a formal WCET bound.",
                "Compiler-sensitive and PFlash effects not priced by supplied "
                "evidence remain outside this source-level estimate.",
            ],
        )
        return prediction, raw_outputs
