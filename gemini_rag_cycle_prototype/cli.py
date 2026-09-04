from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gemini_rag_cycle_prototype.gemini_client import GeminiClient
from gemini_rag_cycle_prototype.ollama_client import OllamaClient
from gemini_rag_cycle_prototype.predictor import Predictor
from gemini_rag_cycle_prototype.rag.index_builder import (
    EMBEDDING_DOCUMENT_FORMAT_VERSION,
    build_index,
    load_index,
)
from gemini_rag_cycle_prototype.rag.measurement_loader import MeasurementLoader


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Gemini RAG source-level execution-time prototype"
    )
    result.add_argument("--build-index", action="store_true")
    result.add_argument("--rebuild-index", action="store_true")
    result.add_argument("--discover", action="store_true")
    result.add_argument("--source", type=Path)
    result.add_argument("--function")
    result.add_argument("--context-file", type=Path, action="append", default=[])
    result.add_argument("--exclude-task-id")
    result.add_argument("--exclude-function")
    result.add_argument("--exclude-source-path")
    result.add_argument("--top-k", type=int, default=5)
    result.add_argument("--minimum-similarity", type=float, default=0.45)
    result.add_argument(
        "--minimum-structural-similarity", type=float, default=0.75,
        help="reject retrieved records below this source-structure score",
    )
    result.add_argument(
        "--no-rag", action="store_true",
        help="skip retrieval and predict from source plus hardware profile only",
    )
    result.add_argument("--output", type=Path)
    result.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    result.add_argument(
        "--provider", choices=("gemini", "ollama"),
        default=os.getenv("LLM_PROVIDER", "gemini"),
        help="generation and embedding backend (default: LLM_PROVIDER or gemini)",
    )
    return result


def create_client(provider: str):
    return OllamaClient() if provider == "ollama" else GeminiClient()


def read_required(path: Path, label: str) -> str:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path.read_text(encoding="utf-8")


def repository_relative_or_absolute(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def load_current_index(path: Path):
    index = load_index(path)
    if index.document_format_version != EMBEDDING_DOCUMENT_FORMAT_VERSION:
        raise ValueError(
            "RAG index format is stale: "
            f"expected {EMBEDDING_DOCUMENT_FORMAT_VERSION}, "
            f"received {index.document_format_version}. "
            "Run: python -m gemini_rag_cycle_prototype.cli --rebuild-index"
        )
    return index


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.repository_root.resolve()
    prototype = root / "gemini_rag_cycle_prototype"
    source_code = read_required(args.source, "C source") if args.source else None
    if args.source and not args.function:
        parser().error("--function is required for prediction")
    index_path = prototype / "index" / "measurements.json"
    loader = MeasurementLoader(root)
    records = loader.load()
    if args.discover:
        print(json.dumps(loader.discovery_report(records), indent=2))
        if not (args.build_index or args.rebuild_index or args.source):
            return 0
    client = None
    if (
        args.build_index or args.rebuild_index
        or (not args.no_rag and not index_path.exists())
    ):
        client = create_client(args.provider)
        build_index(
            records, client, index_path,
            client.embedding_model, client.embedding_dimensions,
        )
        print(
            f"Built board-measurement index with {len(records)} records: "
            f"{index_path}"
        )
        if not args.source:
            return 0
    if not args.source:
        if args.build_index or args.rebuild_index:
            return 0
        parser().error("--source and --function are required for prediction")
    context_parts = [read_required(path, "context file") for path in args.context_file]
    client = client or create_client(args.provider)
    started = time.monotonic()
    index = load_current_index(index_path) if index_path.exists() else None
    if not args.no_rag:
        if index is None:
            raise FileNotFoundError(
                "RAG index does not exist; run --rebuild-index first"
            )
        if (
            index.embedding_model != client.embedding_model
            or index.embedding_dimensions != client.embedding_dimensions
        ):
            raise ValueError(
                "RAG index embedding configuration mismatch: index uses "
                f"{index.embedding_model}/{index.embedding_dimensions}, but "
                f"{client.provider} uses {client.embedding_model}/"
                f"{client.embedding_dimensions}. Run with --provider "
                f"{client.provider} --rebuild-index."
            )
    if index is None:
        from gemini_rag_cycle_prototype.rag.index_builder import RagIndex
        index = RagIndex(
            embedding_model=client.embedding_model,
            embedding_dimensions=client.embedding_dimensions,
            document_format_version=EMBEDDING_DOCUMENT_FORMAT_VERSION,
            records=[],
        )
    prediction, raw, retrieval = Predictor(root, index, client).predict(
        source_code,
        args.function,
        context_code="\n\n".join(context_parts),
        top_k=args.top_k,
        minimum_similarity=args.minimum_similarity,
        minimum_structural_similarity=args.minimum_structural_similarity,
        exclude_task_id=args.exclude_task_id,
        exclude_function=args.exclude_function,
        exclude_source_path=(
            args.exclude_source_path
            or repository_relative_or_absolute(args.source, root)
        ),
        use_rag=not args.no_rag,
    )
    output = args.output or prototype / "results" / f"{args.function}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(prediction.model_dump_json(indent=2), encoding="utf-8")
    output.with_suffix(".raw.txt").write_text(raw, encoding="utf-8")
    output.with_suffix(".retrieval.json").write_text(
        json.dumps({
            "hits": [
                {
                    "task_id": hit.record.task_id,
                    "task_name": hit.record.task_name,
                    "embedding_similarity": hit.similarity,
                    "structural_similarity": hit.structural_similarity,
                    "combined_score": hit.ranking_score,
                    "source_family": hit.record.source_path,
                }
                for hit in retrieval.hits
            ],
            "excluded": retrieval.excluded,
            "warnings": retrieval.warnings,
        }, indent=2),
        encoding="utf-8",
    )
    output.with_suffix(".run.json").write_text(
        json.dumps({
            "provider": client.provider,
            "model": client.model,
            "embedding_model": client.embedding_model,
            "embedding_dimensions": client.embedding_dimensions,
            "rag_enabled": not args.no_rag,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }, indent=2),
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
