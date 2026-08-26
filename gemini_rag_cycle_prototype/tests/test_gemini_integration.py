import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(
    os.getenv("RUN_GEMINI_INTEGRATION") == "1" and os.getenv("GEMINI_API_KEY"),
    "requires RUN_GEMINI_INTEGRATION=1 and a rotated GEMINI_API_KEY",
)
class GeminiIntegrationTest(unittest.TestCase):
    def test_real_blind_prediction_via_cli(self) -> None:
        prototype = Path(__file__).parents[1]
        root = prototype.parent
        source = root / "task_admission_framework" / "examples" / "nested_loop_automotive_wcet.c"
        output = prototype / "results" / "nested_loop_gemini_blind.json"
        command = [
            sys.executable, "-m", "gemini_rag_cycle_prototype.cli",
            "--build-index", "--source", str(source),
            "--function", "AutomotiveSensorMatrix_Task10ms",
            "--exclude-task-id", "AutomotiveSensorMatrix_Task10ms",
            "--exclude-function", "AutomotiveSensorMatrix_Task10ms",
            "--output", str(output),
        ]
        completed = subprocess.run(
            command, cwd=root, capture_output=True, text=True, timeout=600
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        prediction = json.loads(output.read_text(encoding="utf-8"))
        self.assertIn(
            prediction["analysis_status"],
            {"SUPPORTED", "PARTIAL", "UNRESOLVED"},
        )
        retrieval = json.loads(
            output.with_suffix(".retrieval.json").read_text(encoding="utf-8")
        )
        self.assertNotIn(
            "AutomotiveSensorMatrix_Task10ms",
            {hit["task_id"] for hit in retrieval["hits"]},
        )


if __name__ == "__main__":
    unittest.main()
