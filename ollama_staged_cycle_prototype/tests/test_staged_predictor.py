from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ollama_staged_cycle_prototype.predictor import StagedPredictor
from ollama_staged_cycle_prototype.schemas import FunctionLedger, StructurePlan


SOURCE = """
static int Helper(int x) { return x + 1; }
void Task(void) { for (int i = 0; i < 3; ++i) { Helper(i); } }
"""


class FakeClient:
    provider = "ollama"
    model = "test-model"

    def __init__(self, wrong_plan: bool = False):
        self.wrong_plan = wrong_plan

    def predict(self, prompt, response_schema):
        if response_schema is StructurePlan:
            calls = 2 if self.wrong_plan else 3
            value = {
                "target_function": "Task",
                "functions": [
                    {"function_name": "Task", "dynamic_calls": 1,
                     "call_count_evidence": "entry"},
                    {"function_name": "Helper", "dynamic_calls": calls,
                     "call_count_evidence": "three loop iterations"},
                ],
                "loop_bounds": ["i=0..2"],
            }
        elif "EXACTLY ONE\ninvocation of function Task" in prompt:
            value = {
                "function_name": "Task",
                "callees": [{"function_name": "Helper",
                             "calls_per_invocation": 3, "evidence": "loop"}],
                "conditional_branch_evaluations_per_invocation": 4,
                "instruction_counts": [
                    {"instruction_class": "function_call_bl_with_refill",
                     "dynamic_count_per_invocation": 3, "evidence": "calls"},
                    {"instruction_class": "conditional_branch_taken",
                     "dynamic_count_per_invocation": 3, "evidence": "loop"},
                    {"instruction_class": "conditional_branch_not_taken",
                     "dynamic_count_per_invocation": 1, "evidence": "exit"},
                    {"instruction_class": "function_return_with_refill",
                     "dynamic_count_per_invocation": 1, "evidence": "return"},
                ],
            }
        else:
            value = {
                "function_name": "Helper",
                "conditional_branch_evaluations_per_invocation": 0,
                "instruction_counts": [
                    {"instruction_class": "alu_move_compare_shift",
                     "dynamic_count_per_invocation": 2, "evidence": "body"},
                    {"instruction_class": "function_return_with_refill",
                     "dynamic_count_per_invocation": 1, "evidence": "return"},
                ],
            }
        raw = json.dumps(value)
        return response_schema.model_validate(value), raw


class StagedPredictorTest(unittest.TestCase):
    def test_composes_per_function_ledgers(self):
        root = Path(__file__).resolve().parents[2]
        prediction, raw = StagedPredictor(root, FakeClient()).predict(SOURCE, "Task")
        self.assertEqual(prediction.analysis_status, "SUPPORTED")
        # Task: 3 BL*4 + 3 taken*4 + 1 not-taken + return*4 = 29
        # Helper: (2 ALU + return*4) * 3 calls = 18
        self.assertEqual(prediction.estimated_source_execution_cycles, 47)
        self.assertEqual(len(raw), 3)

    def test_disagreement_is_validation_required_without_estimate(self):
        root = Path(__file__).resolve().parents[2]
        prediction, _ = StagedPredictor(
            root, FakeClient(wrong_plan=True)
        ).predict(SOURCE, "Task")
        self.assertEqual(prediction.analysis_status, "VALIDATION_REQUIRED")
        self.assertIsNone(prediction.estimated_source_execution_cycles)
        self.assertTrue(prediction.validation_errors)


if __name__ == "__main__":
    unittest.main()
