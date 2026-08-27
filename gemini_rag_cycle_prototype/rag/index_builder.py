from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from gemini_rag_cycle_prototype.schemas import RagRecord


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class IndexedRecord(BaseModel):
    record: RagRecord
    embedding: list[float]


class RagIndex(BaseModel):
    embedding_model: str
    embedding_dimensions: int
    records: list[IndexedRecord]


def embedding_text(record: RagRecord) -> str:
    summary = record.structural_summary.model_dump_json()
    return (
        f"Task: {record.task_name}\n"
        f"Structural summary: {summary}\n"
        f"C source:\n{record.source_code}"
        f"\nReachable helper source:\n{record.callee_source or 'None'}"
        f"\nRelevant source context:\n{record.source_context or 'None'}"
    )


def build_index(
    records: list[RagRecord], embedder: Embedder, output_path: Path,
    model_name: str, dimensions: int,
) -> RagIndex:
    reusable: dict[tuple[str, str, str], list[float]] = {}
    if output_path.exists():
        existing = load_index(output_path)
        if (
            existing.embedding_model == model_name
            and existing.embedding_dimensions == dimensions
        ):
            reusable = {
                (
                    item.record.task_id,
                    item.record.source_fingerprint,
                    item.record.context_fingerprint,
                ): item.embedding
                for item in existing.records
                if len(item.embedding) == dimensions
            }

    missing_records = [
        item for item in records
        if (item.task_id, item.source_fingerprint, item.context_fingerprint)
        not in reusable
    ]
    generated = (
        embedder.embed_documents([embedding_text(item) for item in missing_records])
        if missing_records else []
    )
    if len(generated) != len(missing_records):
        raise ValueError(
            "Embedding count mismatch: "
            f"expected {len(missing_records)}, received {len(generated)}"
        )
    for position, embedding in enumerate(generated):
        if len(embedding) != dimensions:
            raise ValueError(
                "Embedding dimension mismatch at record "
                f"{position}: expected {dimensions}, received {len(embedding)}"
            )
    generated_by_key = {
        (record.task_id, record.source_fingerprint, record.context_fingerprint): embedding
        for record, embedding in zip(missing_records, generated)
    }
    embeddings = [
        reusable.get((
            record.task_id, record.source_fingerprint, record.context_fingerprint
        ))
        or generated_by_key[(
            record.task_id, record.source_fingerprint, record.context_fingerprint
        )]
        for record in records
    ]
    index = RagIndex(
        embedding_model=model_name,
        embedding_dimensions=dimensions,
        records=[
            IndexedRecord(record=record, embedding=embedding)
            for record, embedding in zip(records, embeddings)
        ],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(index.model_dump_json(indent=2), encoding="utf-8")
    return index


def load_index(path: Path) -> RagIndex:
    return RagIndex.model_validate_json(path.read_text(encoding="utf-8"))
