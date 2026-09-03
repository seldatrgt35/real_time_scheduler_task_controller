from __future__ import annotations

import json
from pathlib import Path
import re

from gemini_rag_cycle_prototype.gemini_client import GeminiClient
from gemini_rag_cycle_prototype.gcc_evidence import retrieve_gcc_evidence
from gemini_rag_cycle_prototype.rag.index_builder import RagIndex
from gemini_rag_cycle_prototype.rag.measurement_loader import HARDWARE_PROFILE_ID
from gemini_rag_cycle_prototype.rag.measurement_loader import (
    extract_function, extract_initialization_context,
    extract_reachable_helpers, extract_relevant_defines, function_names,
)
from gemini_rag_cycle_prototype.rag.retriever import RetrievalResult, Retriever
from gemini_rag_cycle_prototype.schemas import PredictionResponse


class LeakageError(RuntimeError):
    pass


STRONG_REFERENCE_SCORE = 0.85


def indexed_access_obligations(source_code: str, function_name: str) -> list[str]:
    """List variable-indexed accesses in the selected caller/callee region."""
    relevant = "\n".join(filter(None, (
        extract_function(source_code, function_name),
        extract_reachable_helpers(source_code, function_name),
    )))
    pattern = re.compile(
        r"\b[A-Za-z_]\w*(?:\s*\[[^\]]+\])+"
        r"(?:\s*(?:\.|->)\s*[A-Za-z_]\w*)?"
    )
    obligations: list[str] = []
    for match in pattern.finditer(relevant):
        expression = re.sub(r"\s+", "", match.group(0))
        indexes = re.findall(r"\[([^\]]+)\]", expression)
        if not any(re.search(r"[A-Za-z_]", index) for index in indexes):
            continue
        if expression not in obligations:
            obligations.append(expression)
    return obligations


def source_analysis_bundle(
    source_code: str, function_name: str, supplied_context: str = ""
) -> tuple[str, str]:
    """Remove unrelated task bodies while preserving declarations and context."""
    target = extract_function(source_code, function_name)
    if target is None:
        return source_code, supplied_context
    helpers = extract_reachable_helpers(source_code, function_name)
    relevant = "\n\n".join(filter(None, (target, helpers)))
    starts = [
        source_code.find(body)
        for name in function_names(source_code)
        if (body := extract_function(source_code, name)) is not None
    ]
    preamble = source_code[:min(starts)] if starts else ""
    defines = extract_relevant_defines(source_code, relevant)
    analysis_source = "\n\n".join(filter(None, (preamble, defines, relevant)))
    initialization = extract_initialization_context(source_code)
    analysis_context = "\n\n".join(filter(None, (
        supplied_context,
        "Initialization context (outside timed interval):\n" + initialization
        if initialization else "",
    )))
    return analysis_source, analysis_context


def canonicalize_reference_ids(
    returned_ids: set[str], retrieval: RetrievalResult
) -> set[str]:
    """Resolve only exact IDs or unique names from the already-filtered hits."""
    allowed_ids = {hit.record.task_id for hit in retrieval.hits}
    names: dict[str, list[str]] = {}
    for hit in retrieval.hits:
        names.setdefault(hit.record.task_name, []).append(hit.record.task_id)
    canonical = set()
    unknown = set()
    for returned in returned_ids:
        if returned in allowed_ids:
            canonical.add(returned)
        elif len(names.get(returned, [])) == 1:
            canonical.add(names[returned][0])
        else:
            unknown.add(returned)
    if unknown:
        raise LeakageError(
            "Gemini cited references outside the leakage-filtered retrieval "
            f"set: returned={sorted(unknown)}; allowed_ids={sorted(allowed_ids)}; "
            f"allowed_names={sorted(names)}"
        )
    return canonical


class Predictor:
    def __init__(
        self, repository_root: Path, index: RagIndex, client: GeminiClient
    ):
        self.root = repository_root.resolve()
        self.index = index
        self.client = client
        prototype = self.root / "gemini_rag_cycle_prototype"
        self.profile = json.loads(
            (prototype / "config" / "hardware_profile.json").read_text(
                encoding="utf-8"
            )
        )
        self.instruction_timing_profile = json.loads(
            (prototype / "config" / "cortex_m4_timing_profile.json").read_text(
                encoding="utf-8"
            )
        )
        self.gcc_pattern_path = prototype / "knowledge" / "gcc_o0_patterns.json"
        self.rag_template = (
            prototype / "prompts" / "cycle_prediction_prompt.txt"
        ).read_text(encoding="utf-8")
        self.source_only_template = (
            prototype / "prompts" / "source_only_prediction_prompt.txt"
        ).read_text(encoding="utf-8")
        self.function_template = (
            prototype / "prompts" / "function_assembly_prompt.txt"
        ).read_text(encoding="utf-8")

    def _predict_split_source_only(
        self, source_code: str, function_name: str, context_code: str
    ) -> tuple[PredictionResponse, str]:
        available = set(function_names(source_code))
        if function_name not in available:
            raise ValueError(f"query function not found: {function_name}")
        expected_counts = {function_name: 1}
        pending = [function_name]
        predicted = {}
        raw_fragments = []
        while pending:
            name = pending.pop(0)
            if name in predicted:
                continue
            function_source = extract_function(source_code, name)
            if function_source is None:
                raise ValueError(f"reachable helper body not found: {name}")
            _, source_context = source_analysis_bundle(
                source_code, name, context_code
            )
            evidence = retrieve_gcc_evidence(
                source_code, self.gcc_pattern_path,
                function_name=name, limit=3,
            )
            prompt = self.function_template.format(
                function_name=name,
                execution_count=expected_counts[name],
                function_source=function_source,
                source_context=(
                    source_context or "No additional source context supplied."
                ),
                instruction_timing_profile=json.dumps(
                    self.instruction_timing_profile, separators=(",", ":")
                ),
                gcc_transformation_evidence=json.dumps(
                    evidence, separators=(",", ":")
                ),
            )
            fragment, raw = self.client.predict_function(prompt)
            if fragment.function_name != name:
                raise ValueError(
                    f"function fragment mismatch: expected {name}, "
                    f"received {fragment.function_name}"
                )
            if fragment.execution_count != expected_counts[name]:
                raise ValueError(
                    f"function execution count mismatch for {name}: expected "
                    f"{expected_counts[name]}, received {fragment.execution_count}"
                )
            predicted[name] = fragment
            raw_fragments.append(raw)
            for block in fragment.blocks:
                for instruction in block.instructions:
                    callee = instruction.callee
                    if not callee or not instruction.executed_on_path:
                        continue
                    if callee not in available:
                        raise ValueError(
                            f"BL callee has no supplied source body: {callee}"
                        )
                    dynamic_calls = (
                        block.execution_count * instruction.count_per_block
                    )
                    new_count = expected_counts.get(callee, 0) + dynamic_calls
                    if callee in predicted and new_count != expected_counts[callee]:
                        raise ValueError(
                            "shared callee count changed after its fragment was "
                            f"generated: {callee}"
                        )
                    expected_counts[callee] = new_count
                    if callee not in pending and callee not in predicted:
                        pending.append(callee)
        payload = {
            "analysis_status": "PARTIAL",
            "function_name": function_name,
            "hardware_profile_id": self.profile["hardware_profile_id"],
            "source_analysis": {
                "dynamic_helper_calls": sum(
                    count for name, count in expected_counts.items()
                    if name != function_name
                ),
            },
            "retrieved_examples_used": [],
            "estimation_basis": "SOURCE_ONLY",
            "reference_anchor_task_id": None,
            "reference_anchor_measured_us": None,
            "reference_adjustments": [],
            "cycle_components": [{
                "name": "predicted_thumb2_cycle_sum", "cycles": 1,
                "evidence": "merged single-function structured fragments",
            }],
            "predicted_assembly_outline": [
                f"{name}: {len(fragment.blocks)} validated blocks, "
                f"execution_count={fragment.execution_count}"
                for name, fragment in predicted.items()
            ],
            "predicted_functions": [
                fragment.model_dump() for fragment in predicted.values()
            ],
            "instruction_cycle_ledger": [],
            "estimated_source_execution_cycles": 1,
            "estimated_source_execution_us": 1 / 48.0,
            "formal_guarantee": False,
            "confidence_percent": 45,
            "estimation_reasoning_summary": (
                "Each reachable function was generated and validated "
                "independently; the ledger was merged deterministically."
            ),
            "assumptions": [],
            "unresolved": [
                "Exact compiler binary and PFlash effects are not supplied."
            ],
            "warnings": [
                "SOURCE_ONLY split-function predicted assembly."
            ],
        }
        return PredictionResponse.model_validate(payload), "\n\n".join(raw_fragments)

    def _references(self, retrieval: RetrievalResult) -> str:
        output = []
        for number, hit in enumerate(retrieval.hits, start=1):
            record = hit.record
            output.append(
                "\n".join((
                    f"Reference example ID: {record.task_id}",
                    f"Task name: {record.task_name}",
                    f"Similarity score: {hit.similarity:.6f}",
                    f"Structural similarity score: {hit.structural_similarity:.6f}",
                    f"Combined retrieval score: {hit.ranking_score:.6f}",
                    f"Structural summary: {record.structural_summary.model_dump_json()}",
                    f"Hardware profile: {record.hardware_profile_id}",
                    f"Sample count: {record.measurement.sample_count}",
                    f"Measured mean execution time: {record.measurement.mean_us} us",
                    f"Measured maximum execution time: {record.measurement.maximum_us} us",
                    "Relevant C source:",
                    "```c",
                    record.source_code,
                    "```",
                    "Reachable helper source:",
                    "```c",
                    record.callee_source or "No reachable helper bodies supplied.",
                    "```",
                    "Relevant defines and initialization context:",
                    "```c",
                    record.source_context or "No additional source context supplied.",
                    "```",
                ))
            )
        return "\n\n".join(output) if output else "No sufficiently similar independent references."

    def predict(
        self, source_code: str, function_name: str, *,
        context_code: str = "", top_k: int = 5,
        minimum_similarity: float = 0.45,
        minimum_structural_similarity: float = 0.75,
        exclude_task_id: str | None = None,
        exclude_function: str | None = None,
        exclude_source_path: str | None = None,
        use_rag: bool = True,
    ) -> tuple[PredictionResponse, str, RetrievalResult]:
        retrieval = (
            Retriever(self.index, self.client).retrieve(
                source_code,
                function_name,
                HARDWARE_PROFILE_ID,
                top_k=top_k,
                minimum_similarity=minimum_similarity,
                minimum_structural_similarity=minimum_structural_similarity,
                exclude_task_id=exclude_task_id,
                exclude_function=exclude_function,
                exclude_source_path=exclude_source_path,
            )
            if use_rag
            else RetrievalResult()
        )
        if not use_rag and hasattr(self.client, "predict_function"):
            prediction, raw = self._predict_split_source_only(
                source_code, function_name, context_code
            )
            return prediction, raw, retrieval
        template = self.rag_template if use_rag else self.source_only_template
        gcc_evidence = (
            [] if use_rag else retrieve_gcc_evidence(
                source_code, self.gcc_pattern_path, function_name=function_name
            )
        )
        analysis_source, analysis_context = source_analysis_bundle(
            source_code, function_name, context_code
        )
        prompt = template.format(
            hardware_profile=json.dumps(self.profile, indent=2),
            instruction_timing_profile=json.dumps(
                self.instruction_timing_profile, indent=2
            ),
            gcc_transformation_evidence=json.dumps(gcc_evidence, indent=2),
            indexed_access_obligations=json.dumps(
                indexed_access_obligations(source_code, function_name), indent=2
            ),
            function_name=function_name,
            source_code=analysis_source,
            context_code=(
                analysis_context or "No additional context files supplied."
            ),
            references=self._references(retrieval),
        )
        prediction, raw = self.client.predict(prompt)
        returned_ids = {
            example.task_id for example in prediction.retrieved_examples_used
        }
        canonical_ids = canonicalize_reference_ids(returned_ids, retrieval)
        if canonical_ids != returned_ids:
            prediction.warnings.append(
                "Gemini returned one or more unique retrieved task names instead "
                "of full reference IDs; citations were validated against the "
                "same leakage-filtered top-k set."
            )
        strong_hits = [
            hit for hit in retrieval.hits
            if hit.ranking_score >= STRONG_REFERENCE_SCORE
        ]
        if strong_hits:
            if prediction.estimation_basis != "REFERENCE_ANCHORED":
                raise ValueError(
                    "strong measured reference requires REFERENCE_ANCHORED estimation"
                )
            anchor_ids = canonicalize_reference_ids(
                {prediction.reference_anchor_task_id or ""}, retrieval
            )
            strong_ids = {hit.record.task_id for hit in strong_hits}
            if not anchor_ids.issubset(strong_ids):
                raise ValueError(
                    "reference anchor must be selected from strong retrieval hits"
                )
            anchor_id = next(iter(anchor_ids))
            anchor = next(hit.record for hit in strong_hits if hit.record.task_id == anchor_id)
            measured = anchor.measurement.maximum_us or anchor.measurement.mean_us
            if measured is None or abs(
                measured - (prediction.reference_anchor_measured_us or 0.0)
            ) > 0.01:
                raise ValueError("reference anchor measured time does not match RAG evidence")
        elif prediction.estimation_basis != "SOURCE_ONLY":
            raise ValueError(
                "REFERENCE_ANCHORED estimation requires a strong measured reference"
            )
        if not strong_hits and prediction.confidence_percent > 50:
            raise ValueError(
                "source-only estimation without a strong reference cannot exceed 50 percent confidence"
            )
        if prediction.hardware_profile_id != HARDWARE_PROFILE_ID:
            raise ValueError("prediction used the wrong hardware profile")
        if (
            prediction.estimated_source_execution_cycles is not None
            and prediction.estimated_source_execution_us is not None
        ):
            expected = prediction.estimated_source_execution_cycles / 48.0
            if abs(expected - prediction.estimated_source_execution_us) > max(0.05, expected * 0.01):
                prediction.warnings.append(
                    "Source execution cycle/us values are inconsistent at 48 MHz; values were recorded unchanged."
                )
        prediction.warnings.extend(retrieval.warnings)
        return prediction, raw, retrieval
