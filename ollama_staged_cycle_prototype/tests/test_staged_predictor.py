from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ollama_staged_cycle_prototype.predictor import StagedPredictor
from ollama_staged_cycle_prototype.schemas import (
    FunctionBlockPlan, FunctionLedger, StructurePlan,
)


SOURCE = """
static int Helper(int x) { return x + 1; }
void Task(void) { for (int i = 0; i < 3; ++i) { Helper(i); } }
"""

MACRO_SOURCE = """
#define LOOP_COUNT (3)
void Task(void) { for (int i = 0; i < LOOP_COUNT; ++i) {} }
"""


class FakeClient:
    provider = "ollama"
    model = "test-model"

    def __init__(self, wrong_plan: bool = False, unresolved_ledger: bool = False):
        self.wrong_plan = wrong_plan
        self.unresolved_ledger = unresolved_ledger

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
        elif (response_schema is FunctionBlockPlan
              and ("invocation of function Task." in prompt
                   or "invocation of function\nTask." in prompt)):
            value = {
                "function_name": "Task",
                "callees": [{"function_name": "Helper",
                             "calls_per_invocation": 3, "evidence": "loop"}],
                "blocks": [{
                    "block_id": "entry", "source_region": "whole function",
                    "execution_count_per_invocation": 1,
                    "execution_count_evidence": "one invocation",
                    "instruction_counts": [
                        {"instruction_class": "function_call_bl_with_refill",
                         "static_count": 3, "evidence": "calls"},
                        {"instruction_class": "conditional_branch_taken",
                         "static_count": 3, "evidence": "loop"},
                        {"instruction_class": "conditional_branch_not_taken",
                         "static_count": 1, "evidence": "exit"},
                        {"instruction_class": "function_return_with_refill",
                         "static_count": 1, "evidence": "return"},
                    ],
                }],
            }
        else:
            value = {
                "function_name": "Helper",
                "blocks": [{
                    "block_id": "entry", "source_region": "whole function",
                    "execution_count_per_invocation": 1,
                    "execution_count_evidence": "one invocation",
                    "instruction_counts": [
                        {"instruction_class": "alu_move_compare_shift",
                         "static_count": 2, "evidence": "body"},
                        {"instruction_class": "function_return_with_refill",
                         "static_count": 1, "evidence": "return"},
                    ],
                }],
                "unresolved": (["unknown loop bound"]
                               if self.unresolved_ledger else []),
            }
        raw = json.dumps(value)
        return response_schema.model_validate(value), raw


class StagedPredictorTest(unittest.TestCase):
    def test_source_facts_preserve_macros_removed_by_function_extraction(self):
        self.assertEqual(
            StagedPredictor._source_facts(MACRO_SOURCE),
            "#define LOOP_COUNT (3)",
        )

    def test_direct_callee_detection_excludes_transitive_calls(self):
        functions = {
            "Task": "void Task(void) { Helper(1); }",
            "Helper": "int Helper(int x) { return x + 1; }",
        }
        self.assertEqual(
            StagedPredictor._direct_callee_names(
                "Task", functions["Task"], functions
            ),
            {"Helper"},
        )

    def test_syntactic_call_sites_are_dynamic_call_lower_bound(self):
        self.assertEqual(
            StagedPredictor._direct_callee_occurrences(
                "void T(void) { H(); H(); }", "H"
            ),
            2,
        )

    def test_lexical_loop_scope_distinguishes_inside_and_after_nested_loop(self):
        body = """
        void Task(void) {
          for (int cylinder = 0; cylinder < CYLINDERS; ++cylinder) {
            for (int sample = 0; sample < SAMPLES; ++sample) { Read(); }
            Clamp();
          }
        }
        """
        facts = "#define CYLINDERS (4U)\n#define SAMPLES (6U)"
        self.assertEqual(
            StagedPredictor._proven_direct_callee_calls(body, "Read", facts)[0],
            24,
        )
        self.assertEqual(
            StagedPredictor._proven_direct_callee_calls(body, "Clamp", facts)[0],
            4,
        )

    def test_multiple_call_sites_are_summed_with_their_own_scopes(self):
        body = """
        void Task(void) {
          Clamp();
          for (int i = 0; i < COUNT; ++i) { Clamp(); }
        }
        """
        calls, _ = StagedPredictor._proven_direct_callee_calls(
            body, "Clamp", "#define COUNT 3U"
        )
        self.assertEqual(calls, 4)

    def test_static_block_counts_are_expanded_by_python(self):
        block_plan = FunctionBlockPlan.model_validate({
            "function_name": "Task",
            "blocks": [{
                "block_id": "loop_body",
                "source_region": "loop body",
                "execution_count_per_invocation": 12,
                "execution_count_evidence": "source bound",
                "instruction_counts": [{
                    "instruction_class": "sram_or_stack_load",
                    "static_count": 3,
                    "evidence": "three loads per iteration",
                }],
            }],
        })
        ledger = StagedPredictor._block_plan_to_ledger(block_plan)
        self.assertEqual(
            ledger.instruction_counts[0].dynamic_count_per_invocation, 36
        )

    def test_composes_per_function_ledgers(self):
        root = Path(__file__).resolve().parents[2]
        prediction, raw = StagedPredictor(root, FakeClient()).predict(SOURCE, "Task")
        self.assertEqual(prediction.analysis_status, "SUPPORTED")
        # Task: 3 BL*4 + 3 taken*4 + 1 not-taken + return*4 = 29
        # Helper: (2 ALU + return*4) * 3 calls = 18
        self.assertEqual(prediction.estimated_source_execution_cycles, 47)
        # One structure call plus draft+review calls for two functions.
        self.assertEqual(len(raw), 5)

    def test_python_normalizes_structure_plan_from_composed_calls(self):
        root = Path(__file__).resolve().parents[2]
        prediction, _ = StagedPredictor(
            root, FakeClient(wrong_plan=True)
        ).predict(SOURCE, "Task")
        self.assertEqual(prediction.analysis_status, "SUPPORTED")
        helper = next(item for item in prediction.function_contributions
                      if item.function_name == "Helper")
        self.assertEqual(helper.dynamic_calls, 3)

    def test_unresolved_function_ledger_suppresses_estimate(self):
        root = Path(__file__).resolve().parents[2]
        prediction, _ = StagedPredictor(
            root, FakeClient(unresolved_ledger=True)
        ).predict(SOURCE, "Task")
        self.assertEqual(prediction.analysis_status, "VALIDATION_REQUIRED")
        self.assertIsNone(prediction.estimated_source_execution_cycles)
        self.assertTrue(any("Unresolved" in item for item in prediction.warnings))

    def test_python_aggregates_duplicate_classes_and_canonicalizes_return(self):
        ledger = FunctionLedger.model_validate({
            "function_name": "Helper",
            "conditional_branch_evaluations_per_invocation": 0,
            "instruction_counts": [
                {"instruction_class": "push_or_pop_register_transfer",
                 "dynamic_count_per_invocation": 2, "evidence": "push"},
                {"instruction_class": "push_or_pop_register_transfer",
                 "dynamic_count_per_invocation": 2, "evidence": "pop"},
                {"instruction_class": "function_return_with_refill",
                 "dynamic_count_per_invocation": 1, "evidence": "return"},
                {"instruction_class": "pop_pc_pipeline_refill_worst_case",
                 "dynamic_count_per_invocation": 1, "evidence": "same return"},
            ],
        })
        normalized, errors = StagedPredictor._normalize_ledger_relations(
            "Helper", ledger, {"Helper": "void Helper(void){}"},
            {"Helper": 1}, {},
        )
        self.assertFalse(errors)
        counts = {item.instruction_class: item.dynamic_count_per_invocation
                  for item in normalized.instruction_counts}
        self.assertEqual(counts["push_or_pop_register_transfer"], 4)
        self.assertEqual(counts["function_return_with_refill"], 1)
        self.assertNotIn("pop_pc_pipeline_refill_worst_case", counts)

    def test_python_adds_single_return_when_model_only_describes_pop(self):
        ledger = FunctionLedger.model_validate({
            "function_name": "Helper",
            "conditional_branch_evaluations_per_invocation": 0,
            "instruction_counts": [
                {"instruction_class": "push_or_pop_register_transfer",
                 "dynamic_count_per_invocation": 2,
                 "evidence": "pop {r7, pc}"},
            ],
        })
        normalized, errors = StagedPredictor._normalize_ledger_relations(
            "Helper", ledger, {"Helper": "void Helper(void){}"},
            {"Helper": 1}, {},
        )
        self.assertFalse(errors)
        counts = {item.instruction_class: item.dynamic_count_per_invocation
                  for item in normalized.instruction_counts}
        self.assertEqual(counts["function_return_with_refill"], 1)

    def test_python_normalizes_redundant_bl_and_branch_arithmetic(self):
        ledger = FunctionLedger.model_validate({
            "function_name": "Task",
            "callees": [{"function_name": "Helper",
                         "calls_per_invocation": 99, "evidence": "model"}],
            "conditional_branch_evaluations_per_invocation": 99,
            "instruction_counts": [
                {"instruction_class": "function_call_bl_with_refill",
                 "dynamic_count_per_invocation": 1, "evidence": "model"},
                {"instruction_class": "conditional_branch_taken",
                 "dynamic_count_per_invocation": 3, "evidence": "loop"},
                {"instruction_class": "conditional_branch_not_taken",
                 "dynamic_count_per_invocation": 1, "evidence": "exit"},
                {"instruction_class": "function_return_with_refill",
                 "dynamic_count_per_invocation": 1, "evidence": "return"},
            ],
        })
        functions = {
            "Task": "void Task(void) { Helper(); }",
            "Helper": "void Helper(void) { return; }",
        }
        normalized, errors = StagedPredictor._normalize_ledger_relations(
            "Task", ledger, functions,
            {"Task": 1, "Helper": 12},
            {"Helper": {"Task"}},
        )
        self.assertFalse(errors)
        # The source contains one call outside any loop, so a contradictory
        # pass-1 total may no longer inflate it to twelve.
        self.assertEqual(normalized.callees[0].calls_per_invocation, 1)
        counts = {item.instruction_class: item.dynamic_count_per_invocation
                  for item in normalized.instruction_counts}
        self.assertEqual(counts["function_call_bl_with_refill"], 1)
        self.assertEqual(normalized.conditional_branch_evaluations_per_invocation, 4)


if __name__ == "__main__":
    unittest.main()
