from __future__ import annotations

import math
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from gemini_rag_cycle_prototype.rag.index_builder import Embedder, RagIndex
from gemini_rag_cycle_prototype.rag.measurement_loader import (
    extract_function,
    build_reference_context,
    normalize_source,
    source_fingerprint,
    structural_summary,
)
from gemini_rag_cycle_prototype.schemas import RagRecord, StructuralSummary


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("embedding dimensions must match and be non-empty")
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


@dataclass(frozen=True)
class RetrievalHit:
    record: RagRecord
    similarity: float
    structural_similarity: float = 1.0
    combined_score: float | None = None

    @property
    def ranking_score(self) -> float:
        return self.similarity if self.combined_score is None else self.combined_score


@dataclass
class RetrievalResult:
    hits: list[RetrievalHit] = field(default_factory=list)
    excluded: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _jaccard(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    union = left_set | right_set
    return len(left_set & right_set) / len(union)


def _count_similarity(left: int, right: int) -> float:
    if left == 0 and right == 0:
        return 1.0
    return 1.0 - (abs(left - right) / max(left, right, 1))


def structural_similarity(
    query: StructuralSummary, candidate: StructuralSummary
) -> float:
    """Score source shape independently from semantic embedding proximity."""
    query_has_loop = query.loop_count > 0
    candidate_has_loop = candidate.loop_count > 0
    loop_presence = 1.0 if query_has_loop == candidate_has_loop else 0.0
    loop_count = 1.0 - (
        abs(query.loop_count - candidate.loop_count)
        / max(query.loop_count, candidate.loop_count, 1)
    )
    depth = 1.0 - (
        abs(query.nested_loop_depth - candidate.nested_loop_depth)
        / max(query.nested_loop_depth, candidate.nested_loop_depth, 1)
    )
    branch = 1.0 if query.has_branches == candidate.has_branches else 0.0
    helper = 1.0 if query.has_helper_calls == candidate.has_helper_calls else 0.0
    count_shape = sum((
        _count_similarity(query.branch_count, candidate.branch_count),
        _count_similarity(query.helper_call_count, candidate.helper_call_count),
        _count_similarity(query.array_access_count, candidate.array_access_count),
        _count_similarity(query.assignment_count, candidate.assignment_count),
        _count_similarity(query.comparison_count, candidate.comparison_count),
        _count_similarity(
            query.arithmetic_operator_count, candidate.arithmetic_operator_count
        ),
        _count_similarity(
            query.bitwise_operator_count, candidate.bitwise_operator_count
        ),
        _count_similarity(query.divide_modulo_count, candidate.divide_modulo_count),
    )) / 8.0
    return (
        0.10 * loop_presence
        + 0.10 * loop_count
        + 0.10 * depth
        + 0.05 * branch
        + 0.075 * helper
        + 0.30 * count_shape
        + 0.125 * _jaccard(query.operation_families, candidate.operation_families)
        + 0.075 * _jaccard(query.data_types, candidate.data_types)
        + 0.075 * _jaccard(
            query.memory_access_patterns, candidate.memory_access_patterns
        )
    )


class Retriever:
    def __init__(self, index: RagIndex, embedder: Embedder):
        self.index = index
        self.embedder = embedder

    def retrieve(
        self, query_source: str, query_function: str,
        hardware_profile_id: str, *, top_k: int = 5,
        minimum_similarity: float = 0.45,
        minimum_structural_similarity: float = 0.75,
        exclude_task_id: str | None = None,
        exclude_function: str | None = None,
        exclude_source_path: str | None = None,
        near_duplicate_threshold: float = 0.97,
    ) -> RetrievalResult:
        # A source file can contain several unrelated task entry points. Rank
        # references from the requested task body, not from the entire file;
        # otherwise every task in one suite produces nearly the same query.
        target_source = extract_function(query_source, query_function) or query_source
        query_callees, query_context = build_reference_context(
            query_source, query_function
        )
        normalized_query = normalize_source(target_source)
        fingerprint = source_fingerprint(target_source)
        query_text = (
            f"Task: {query_function}\nC source:\n{target_source}"
            f"\nReachable helper source:\n{query_callees or 'None'}"
            f"\nRelevant source context:\n{query_context or 'None'}"
        )
        query_embedding = self.embedder.embed_query(query_text)
        query_structure = structural_summary(target_source + "\n" + query_callees)
        result = RetrievalResult()
        candidates: list[RetrievalHit] = []
        for item in self.index.records:
            record = item.record
            reason = None
            if record.hardware_profile_id != hardware_profile_id:
                reason = "hardware_profile_mismatch"
            elif exclude_task_id and record.task_id == exclude_task_id:
                reason = "same_task_id"
            elif (
                exclude_source_path
                and record.source_path.replace("\\", "/").casefold()
                == exclude_source_path.replace("\\", "/").casefold()
            ):
                reason = "same_source_path"
            elif record.task_name in {query_function, exclude_function}:
                reason = "same_function_name"
            elif record.source_fingerprint == fingerprint:
                reason = "same_source_fingerprint"
            else:
                source_ratio = SequenceMatcher(
                    None, normalized_query, record.normalized_source
                ).ratio()
                if source_ratio >= near_duplicate_threshold:
                    reason = "near_duplicate_source"
                    result.warnings.append(
                        f"Leakage candidate excluded: {record.task_id} "
                        f"source similarity={source_ratio:.4f}"
                    )
            if reason:
                result.excluded.append({"task_id": record.task_id, "reason": reason})
                continue
            similarity = cosine_similarity(query_embedding, item.embedding)
            structure = structural_similarity(
                query_structure,
                structural_summary(record.source_code + "\n" + record.callee_source),
            )
            if similarity < minimum_similarity:
                continue
            if structure < minimum_structural_similarity:
                result.excluded.append({
                    "task_id": record.task_id,
                    "reason": "structural_similarity_below_threshold",
                })
                continue
            candidates.append(RetrievalHit(
                record=record,
                similarity=similarity,
                structural_similarity=structure,
                combined_score=(0.45 * similarity) + (0.55 * structure),
            ))
        ranked = sorted(candidates, key=lambda hit: hit.ranking_score, reverse=True)
        selected: list[RetrievalHit] = []
        selected_families: set[str] = set()
        for hit in ranked:
            family = hit.record.source_path.replace("\\", "/").casefold()
            if family in selected_families:
                continue
            selected.append(hit)
            selected_families.add(family)
            if len(selected) == top_k:
                break
        result.hits = selected
        if not result.hits:
            result.warnings.append(
                "No reference passed both semantic and structural retrieval gates; "
                "prediction must proceed without measured reference evidence."
            )
        return result
