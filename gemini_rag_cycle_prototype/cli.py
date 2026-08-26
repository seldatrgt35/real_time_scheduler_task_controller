from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gemini_rag_cycle_prototype.gemini_client import GeminiClient
from gemini_rag_cycle_prototype.predictor import Predictor
from gemini_rag_cycle_prototype.rag.index_builder import build_index, load_index
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
    result.add_argument("--output", type=Path)
    result.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    return result


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


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.repository_root.resolve()
    prototype = root / "gemini_rag_cycle_prototype"
    index_path = prototype / "index" / "measurements.json"
    loader = MeasurementLoader(root)
    records = loader.load()
    if args.discover:
        print(json.dumps(loader.discovery_report(records), indent=2))
        if not (args.build_index or args.rebuild_index or args.source):
            return 0
    client = None
    if args.build_index or args.rebuild_index or not index_path.exists():
        client = GeminiClient()
        build_index(
            records, client, index_path,
            client.embedding_model, client.embedding_dimensions,
        )
        print(f"Built index with {len(records)} records: {index_path}")
        if not args.source:
            return 0
    if not args.source:
        if args.build_index or args.rebuild_index:
            return 0
        parser().error("--source and --function are required for prediction")
    if not args.function:
        parser().error("--function is required for prediction")
    source_code = read_required(args.source, "C source")
    context_parts = [read_required(path, "context file") for path in args.context_file]
    client = client or GeminiClient()
    prediction, raw, retrieval = Predictor(
        root, load_index(index_path), client
    ).predict(
        source_code,
        args.function,
        context_code="\n\n".join(context_parts),
        top_k=args.top_k,
        minimum_similarity=args.minimum_similarity,
        exclude_task_id=args.exclude_task_id,
        exclude_function=args.exclude_function,
        exclude_source_path=(
            args.exclude_source_path
            or repository_relative_or_absolute(args.source, root)
        ),
    )
    output = args.output or prototype / "results" / f"{args.function}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(prediction.model_dump_json(indent=2), encoding="utf-8")
    output.with_suffix(".raw.txt").write_text(raw, encoding="utf-8")
    output.with_suffix(".retrieval.json").write_text(
        json.dumps({
            "hits": [
                {"task_id": hit.record.task_id, "task_name": hit.record.task_name, "similarity": hit.similarity}
                for hit in retrieval.hits
            ],
            "excluded": retrieval.excluded,
            "warnings": retrieval.warnings,
        }, indent=2),
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
