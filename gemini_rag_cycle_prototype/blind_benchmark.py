from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


PROTOTYPE = Path(__file__).resolve().parent
ROOT = PROTOTYPE.parent
QUERY_MANIFEST = PROTOTYPE / "config" / "blind_benchmark_queries.json"
TRUTH_MANIFEST = PROTOTYPE / "config" / "blind_benchmark_truth.json"
RESULTS = PROTOTYPE / "results" / "blind_benchmark"


def predict(*, force: bool = False) -> None:
    """Generate predictions without opening the separate truth manifest."""
    queries = json.loads(QUERY_MANIFEST.read_text(encoding="utf-8"))
    RESULTS.mkdir(parents=True, exist_ok=True)
    total = len(queries)
    failures = []
    for position, query in enumerate(queries, start=1):
        output = RESULTS / f"{query['id']}.json"
        if output.exists() and not force:
            print(
                f"[{position}/{total}] SKIP {query['id']} "
                "(prediction already exists)",
                flush=True,
            )
            continue
        print(
            f"[{position}/{total}] START {query['id']} using "
            f"{query['function']}",
            flush=True,
        )
        started = time.monotonic()
        command = [
            sys.executable, "-m", "gemini_rag_cycle_prototype.cli",
            "--source", str(ROOT / query["source"]),
            "--function", query["function"],
            "--exclude-function", query["function"],
            "--exclude-source-path", query["source"],
            "--top-k", "5", "--output", str(output),
        ]
        completed = subprocess.run(command, cwd=ROOT)
        if completed.returncode:
            failures.append(query["id"])
            print(
                f"[{position}/{total}] FAIL {query['id']} "
                f"(exit code {completed.returncode}); continuing",
                flush=True,
            )
            continue
        print(
            f"[{position}/{total}] DONE {query['id']} "
            f"in {time.monotonic() - started:.1f}s",
            flush=True,
        )
    completed_count = sum(
        (RESULTS / f"{query['id']}.json").exists() for query in queries
    )
    print(
        f"Prediction pass finished: {completed_count}/{total} available; "
        f"failed this pass: {', '.join(failures) if failures else 'none'}",
        flush=True,
    )


def evaluate() -> None:
    """Open board truth only after prediction artifacts already exist."""
    queries = json.loads(QUERY_MANIFEST.read_text(encoding="utf-8"))
    truth = json.loads(TRUTH_MANIFEST.read_text(encoding="utf-8"))
    rows = []
    missing = []
    for query in queries:
        prediction_path = RESULTS / f"{query['id']}.json"
        if not prediction_path.exists():
            missing.append(query["id"])
            continue
        prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
        board = float(truth[query["id"]])
        estimate = prediction.get("estimated_execution_us")
        if estimate is None:
            # Read-only compatibility for frozen results created with the old schema.
            estimate = prediction.get("estimated_nominal_us")
        rows.append({
            "id": query["id"],
            "function": query["function"],
            "status": prediction["analysis_status"],
            "board_max_us": board,
            "estimated_execution_us": estimate,
            "absolute_error_percent": (
                abs(float(estimate) - board) / board * 100.0
                if estimate is not None else None
            ),
            "estimate_covers_board": (
                float(estimate) >= board if estimate is not None else False
            ),
            "signed_error_percent": (
                (float(estimate) - board) / board * 100.0
                if estimate is not None else None
            ),
            "confidence_percent": prediction["confidence_percent"],
        })
    summary = {
        "task_count": len(rows),
        "planned_task_count": len(queries),
        "missing_predictions": missing,
        "estimate_coverage_count": sum(row["estimate_covers_board"] for row in rows),
        "rows": rows,
    }
    output = RESULTS / "evaluation.json"
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("predict", "evaluate"))
    parser.add_argument(
        "--force", action="store_true",
        help="regenerate prediction files that already exist",
    )
    args = parser.parse_args()
    predict(force=args.force) if args.phase == "predict" else evaluate()


if __name__ == "__main__":
    main()
