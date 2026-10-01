from __future__ import annotations

import argparse
import os
from pathlib import Path
import re

from gemini_rag_cycle_prototype.ollama_client import OllamaClient

from .predictor import StaticAssemblyPredictor


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="V2 experiment: C source to audited static GCC -O0 assembly"
    )
    result.add_argument("--source", type=Path, required=True)
    result.add_argument("--function", required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--model", default=None)
    result.add_argument(
        "--strict", action="store_true",
        help="return exit code 2 when semantic assembly audits do not pass",
    )
    result.add_argument(
        "--repository-root", type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.source.exists():
        raise FileNotFoundError(f"C source not found: {args.source}")
    os.environ.setdefault("OLLAMA_NUM_PREDICT", "4096")
    client = OllamaClient(model=args.model)
    report, raw_outputs = StaticAssemblyPredictor(
        args.repository_root, client
    ).predict(args.source.read_text(encoding="utf-8"), args.function)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    for label, raw in raw_outputs:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)
        args.output.with_name(
            f"{args.output.stem}.{safe}.raw.json"
        ).write_text(raw, encoding="utf-8")
    print(args.output)
    if report.analysis_status != "SUPPORTED":
        print(
            "Assembly report was saved with analysis_status=VALIDATION_REQUIRED; "
            "inspect functions[].validation_errors."
        )
    return 2 if args.strict and report.analysis_status != "SUPPORTED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
