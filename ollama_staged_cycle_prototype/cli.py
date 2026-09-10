from __future__ import annotations

import argparse
import os
from pathlib import Path

from gemini_rag_cycle_prototype.ollama_client import OllamaClient
from ollama_staged_cycle_prototype.predictor import StagedPredictor


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Experimental staged Ollama source-level cycle predictor"
    )
    result.add_argument("--source", type=Path, required=True)
    result.add_argument("--function", required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument(
        "--repository-root", type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.source.exists():
        raise FileNotFoundError(f"C source not found: {args.source}")
    # FunctionLedger is intentionally compact; a larger budget encourages
    # small local models to repeat per-instruction rows until truncation.
    os.environ.setdefault("OLLAMA_NUM_PREDICT", "3072")
    client = OllamaClient()
    prediction, raw_outputs = StagedPredictor(
        args.repository_root, client
    ).predict(args.source.read_text(encoding="utf-8"), args.function)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(prediction.model_dump_json(indent=2), encoding="utf-8")
    for index, raw in enumerate(raw_outputs, start=1):
        args.output.with_name(
            f"{args.output.stem}.stage-{index}.raw.json"
        ).write_text(raw, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
