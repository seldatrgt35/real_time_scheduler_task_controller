from __future__ import annotations

import math
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from gemini_rag_cycle_prototype.rag.index_builder import Embedder, RagIndex
from gemini_rag_cycle_prototype.rag.measurement_loader import (
    extract_function,
    normalize_source,
    source_fingerprint,
)
from gemini_rag_cycle_prototype.schemas import RagRecord


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


@dataclass
class RetrievalResult:
    hits: list[RetrievalHit] = field(default_factory=list)
    excluded: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Retriever:
    def __init__(self, index: RagIndex, embedder: Embedder):
        self.index = index
        self.embedder = embedder

    def retrieve(
        self, query_source: str, query_function: str,
        hardware_profile_id: str, *, top_k: int = 5,
        minimum_similarity: float = 0.45,
        exclude_task_id: str | None = None,
        exclude_function: str | None = None,
        exclude_source_path: str | None = None,
        near_duplicate_threshold: float = 0.97,
    ) -> RetrievalResult:
        # A source file can contain several unrelated task entry points. Rank
        # references from the requested task body, not from the entire file;
        # otherwise every task in one suite produces nearly the same query.
        target_source = extract_function(query_source, query_function) or query_source
        normalized_query = normalize_source(target_source)
        fingerprint = source_fingerprint(target_source)
        query_text = (
            f"Task: {query_function}\nC source:\n{target_source}"
        )
        query_embedding = self.embedder.embed_query(query_text)
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
            if similarity >= minimum_similarity:
                candidates.append(RetrievalHit(record, similarity))
        result.hits = sorted(
            candidates, key=lambda hit: hit.similarity, reverse=True
        )[:top_k]
        return result
