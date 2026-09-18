from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ollama_staged_cycle_prototype.predictor import StagedPredictor
from ollama_staged_cycle_prototype.schemas import (
    AssemblySection, FunctionAssemblyPlan, FunctionBlockPlan, FunctionLedger, StructurePlan,
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
                "selected_path": ["loop executes three times", "return"],
                "functions": [
                    {"function_name": "Task", "dynamic_calls": 1,
                     "call_count_evidence": "entry",
                     "selected_path": ["loop executes three times", "return"],
                     "selected_statement_ids": [1]},
                    {"function_name": "Helper", "dynamic_calls": calls,
                     "call_count_evidence": "three loop iterations",
                     "selected_path": ["straight-line return"],
                     "selected_statement_ids": [1]},
                ],
                "loop_bounds": ["i=0..2"],
            }
        elif response_schema is FunctionAssemblyPlan:
            if "function Task." in prompt or "function\nTask." in prompt:
                value = {
                    "function_name": "Task",
                    "selected_source_path": ["loop executes three times", "return"],
                    "sections": [
                        {
                            "section_name": "prologue_and_init",
                            "execution_count": 1,
                            "statement_blocks": [{
                                "block_id": "task_prologue",
                                "statement_id": None,
                                "source_statement": "compiler prologue and loop init",
                                "instructions": [
                                    "push {r7, lr}", "sub sp, #8", "add r7, sp, #0",
                                    "movs r3, #0", "str r3, [r7, #4]",
                                ],
                            }],
                        },
                        {
                            "section_name": "loop_body",
                            "execution_count": 3,
                            "statement_blocks": [{
                                "block_id": "task_statement_1",
                                "statement_id": 1,
                                "source_statement": "Helper(i)",
                                "instructions": [
                                    "ldr r0, [r7, #4]", "bl Helper",
                                    "ldr r3, [r7, #4]", "adds r3, #1", "str r3, [r7, #4]",
                                ],
                            }],
                        },
                        {
                            "section_name": "epilogue_and_return",
                            "execution_count": 1,
                            "statement_blocks": [{
                                "block_id": "task_epilogue",
                                "statement_id": None,
                                "source_statement": "compiler epilogue",
                                "instructions": ["adds r7, #8", "mov sp, r7", "pop {r7, pc}"],
                            }],
                        },
                    ],
                }
            else:
                value = {
                    "function_name": "Helper",
                    "selected_source_path": ["straight-line return"],
                    "sections": [
                        {
                            "section_name": "straight_line",
                            "execution_count": 1,
                            "statement_blocks": [{
                                "block_id": "helper_prologue",
                                "statement_id": None,
                                "source_statement": "compiler prologue",
                                "instructions": [
                                    "push {r7}", "sub sp, #12", "add r7, sp, #0",
                                    "str r0, [r7, #4]",
                                ],
                            }, {
                                "block_id": "helper_statement_1",
                                "statement_id": 1,
                                "source_statement": "return x + 1",
                                "instructions": [
                                    "ldr r3, [r7, #4]", "adds r3, #1", "mov r0, r3",
                                ],
                            }, {
                                "block_id": "helper_epilogue",
                                "statement_id": None,
                                "source_statement": "compiler epilogue",
                                "instructions": [
                                    "adds r7, #12", "mov sp, r7", "pop {r7}", "bx lr",
                                ],
                            }],
                        }
                    ],
                    "unresolved": (["unknown loop bound"]
                                   if self.unresolved_ledger else []),
                }
        elif (response_schema is FunctionBlockPlan
              and ("invocation of function Task." in prompt
                   or "invocation of function\nTask." in prompt)):
            value = {
                "function_name": "Task",
                "selected_path": [
                    "entry", "loop_condition", "loop_body", "exit"
                ],
                "callees": [{"function_name": "Helper",
                             "calls_per_invocation": 3, "evidence": "loop"}],
                "blocks": [
                    {"block_id": "entry", "source_region": "entry",
                     "execution_count_per_invocation": 1,
                     "execution_count_evidence": "one invocation",
                     "instruction_counts": [{"instruction_class":
                         "alu_move_compare_shift", "static_count": 0,
                         "evidence": "none"}]},
                    {"block_id": "loop_condition", "source_region": "loop test",
                     "execution_count_per_invocation": 4,
                     "execution_count_evidence": "N plus one",
                     "successors": ["loop_body", "exit"],
                     "instruction_counts": [{"instruction_class":
                         "alu_move_compare_shift", "static_count": 0,
                         "evidence": "omitted in fixture"}]},
                    {"block_id": "loop_body", "source_region": "loop body",
                     "execution_count_per_invocation": 3,
                     "execution_count_evidence": "three iterations",
                     "instruction_counts": [{"instruction_class":
                         "function_call_bl_with_refill", "static_count": 1,
                         "evidence": "one call"}]},
                    {"block_id": "exit", "source_region": "return",
                     "execution_count_per_invocation": 1,
                     "execution_count_evidence": "one invocation",
                     "instruction_counts": [{"instruction_class":
                         "function_return_with_refill", "static_count": 1,
                         "evidence": "return"}]},
                ],
                "edges": [
                    {"source_block": "loop_condition",
                     "target_block": "loop_body", "kind": "conditional_taken",
                     "execution_count_per_invocation": 3,
                     "evidence": "three successful tests"},
                    {"source_block": "loop_condition",
                     "target_block": "exit", "kind": "conditional_not_taken",
                     "execution_count_per_invocation": 1,
                     "evidence": "final failed test"},
                ],
            }
        else:
            value = {
                "function_name": "Helper",
                "selected_path": ["entry"],
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
            "selected_path": ["loop_body"],
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
        self.assertEqual(prediction.estimated_source_execution_cycles, 104)
        # One structure call plus assembly section calls for two functions.
        self.assertEqual(len(raw), 3)

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

    def test_loop_execution_obligations_nested_loop(self):
        source = """
        #define ROWS (8U)
        #define COLS (4U)
        void Matrix(void) {
            for (int r = 0; r < ROWS; ++r) {
                for (int c = 0; c < COLS; ++c) {
                    sink += 1;
                }
            }
        }
        """
        facts = StagedPredictor._source_facts(source)
        functions = {"Matrix": source}
        obs = StagedPredictor._loop_execution_obligations("Matrix", source, functions, facts)
        self.assertEqual(len(obs), 2)
        self.assertIn("BODY EXECUTION COUNT = 8", obs[0])
        self.assertIn("COMPOUND INNER BODY EXECUTION COUNT = 32", obs[1])

    def test_dead_branch_block_zeroed_by_cfg_reachability(self):
        plan = FunctionBlockPlan.model_validate({
            "function_name": "TestFunc",
            "selected_path": ["entry", "branch_taken"],
            "blocks": [
                {"block_id": "entry", "source_region": "entry",
                 "execution_count_per_invocation": 10,
                 "instruction_counts": [{"instruction_class": "alu_move_compare_shift", "static_count": 1, "evidence": "cmp"}]},
                {"block_id": "branch_taken", "source_region": "if arm",
                 "execution_count_per_invocation": 10,
                 "instruction_counts": [{"instruction_class": "alu_move_compare_shift", "static_count": 1, "evidence": "add"}]},
                {"block_id": "branch_not_taken", "source_region": "else arm",
                 "execution_count_per_invocation": 10,
                 "instruction_counts": [{"instruction_class": "alu_move_compare_shift", "static_count": 1, "evidence": "sub"}]},
            ],
            "edges": [
                {"source_block": "entry", "target_block": "branch_taken",
                 "kind": "conditional_taken", "execution_count_per_invocation": 10, "evidence": "all taken"},
                {"source_block": "entry", "target_block": "branch_not_taken",
                 "kind": "conditional_not_taken", "execution_count_per_invocation": 0, "evidence": "never not taken"},
            ],
        })
        # The not_taken block had incoming edge = 0, so its execution count should be zeroed
        not_taken_block = next(b for b in plan.blocks if b.block_id == "branch_not_taken")
        self.assertEqual(not_taken_block.execution_count_per_invocation, 0)

    def test_conditional_call_sites_not_summed_by_lexical_proof(self):
        source = """
        void Caller(int state) {
            if (state == 1) {
                Helper();
            } else if (state == 2) {
                Helper();
            }
        }
        """
        calls, proof = StagedPredictor._proven_direct_callee_calls(source, "Helper", "")
        self.assertIsNone(calls)
        self.assertIn("conditional branch", proof)

    def test_else_if_call_sites_have_single_path_maximum_one(self):
        body = """
        void Caller(int state) {
            if (state == 1) {
                Helper();
            } else if (state == 2) {
                Helper();
            } else {
                Sink();
            }
        }
        """
        self.assertEqual(
            StagedPredictor._max_direct_callee_calls_on_one_branch_path(
                body, "Helper", ""
            ),
            1,
        )

    def test_independent_if_calls_are_not_treated_as_mutually_exclusive(self):
        body = """
        void Caller(int a, int b) {
            if (a) { Helper(); }
            if (b) { Helper(); }
        }
        """
        self.assertEqual(
            StagedPredictor._max_direct_callee_calls_on_one_branch_path(
                body, "Helper", ""
            ),
            2,
        )

    def test_selected_trace_branch_metadata_drives_branch_timing(self):
        plan = FunctionAssemblyPlan.model_validate({
            "function_name": "Branching",
            "selected_source_path": ["x != 0: false", "return"],
            "sections": [{
                "section_name": "straight_line",
                "execution_count": 1,
                "instructions": [
                    "push {r7, lr}", "cmp r0, #0", "bne.n chosen",
                    "movs r0, #0", "pop {r7, pc}",
                ],
                "conditional_branches": [{
                    "instruction_index": 2,
                    "taken_count": 0,
                    "not_taken_count": 1,
                    "evidence": "selected fallthrough arm",
                }],
            }],
        })
        self.assertEqual(StagedPredictor._validate_assembly_plan(plan), [])
        ledger = StagedPredictor._assembly_plan_to_ledger(
            plan, {"Branching": "int Branching(int x) { return x ? 1 : 0; }"}
        )
        counts = {
            item.instruction_class: item.dynamic_count_per_invocation
            for item in ledger.instruction_counts
        }
        self.assertEqual(counts.get("conditional_branch_not_taken"), 1)
        self.assertNotIn("conditional_branch_taken", counts)

    def test_missing_branch_metadata_rejects_selected_trace(self):
        plan = FunctionAssemblyPlan.model_validate({
            "function_name": "Branching",
            "selected_source_path": ["x != 0: false", "return"],
            "sections": [{
                "section_name": "straight_line",
                "execution_count": 1,
                "instructions": [
                    "cmp r0, #0", "bne.n chosen", "pop {r7, pc}",
                ],
            }],
        })
        errors = StagedPredictor._validate_assembly_plan(plan)
        self.assertTrue(any("metadata indices" in error for error in errors))

    def test_conditional_selected_assembly_cannot_exceed_branch_path_maximum(self):
        functions = {
            "Caller": """
                void Caller(int state) {
                    if (state == 1) { Helper(); }
                    else if (state == 2) { Helper(); }
                }
            """,
            "Helper": "void Helper(void) { return; }",
        }
        ledger = FunctionLedger.model_validate({
            "function_name": "Caller",
            "selected_path": ["both mutually exclusive arms (invalid)"],
            "callees": [{
                "function_name": "Helper",
                "calls_per_invocation": 2,
                "evidence": "two synthesized BL instructions",
            }],
            "conditional_branch_evaluations_per_invocation": 2,
            "instruction_counts": [{
                "instruction_class": "function_call_bl_with_refill",
                "dynamic_count_per_invocation": 2,
                "evidence": "two BL instructions",
            }],
        })
        _, errors = StagedPredictor._normalize_ledger_relations(
            "Caller", ledger, functions,
            {"Caller": 1, "Helper": 2}, {"Helper": {"Caller"}},
        )
        self.assertTrue(any("single-path maximum 1" in error for error in errors))

    def test_unselected_conditional_helper_remains_zero_calls(self):
        functions = {
            "Caller": "void Caller(int state) { if (state) { Helper(); } }",
            "Helper": "void Helper(void) { return; }",
        }
        ledger = FunctionLedger.model_validate({
            "function_name": "Caller",
            "selected_path": ["state == 0", "return"],
            "conditional_branch_evaluations_per_invocation": 1,
            "instruction_counts": [{
                "instruction_class": "conditional_branch_taken",
                "dynamic_count_per_invocation": 1,
                "evidence": "skip helper arm",
            }],
        })
        normalized, errors = StagedPredictor._normalize_ledger_relations(
            "Caller", ledger, functions,
            {"Caller": 1, "Helper": 0}, {"Helper": {"Caller"}},
        )
        self.assertFalse(errors)
        self.assertEqual(normalized.callees, [])

    def test_fuzzy_branch_instruction_indices_are_positionally_mapped(self):
        plan = FunctionAssemblyPlan.model_validate({
            "function_name": "FuzzyBranching",
            "selected_source_path": ["x > 0: true", "return"],
            "sections": [{
                "section_name": "straight_line",
                "execution_count": 1,
                "instructions": [
                    "push {r7, lr}", "sub sp, #12", "cmp r0, #0", "ble.n skip",
                    "movs r0, #1", "pop {r7, pc}",
                ],
                "conditional_branches": [{
                    "instruction_index": 5,
                    "taken_count": 0,
                    "not_taken_count": 1,
                    "evidence": "branch not taken, fall through",
                }],
            }],
        })
        self.assertEqual(StagedPredictor._validate_assembly_plan(plan), [])
        ledger = StagedPredictor._assembly_plan_to_ledger(
            plan, {"FuzzyBranching": "int FuzzyBranching(int x) { return x > 0 ? 1 : 0; }"}
        )
        counts = {
            item.instruction_class: item.dynamic_count_per_invocation
            for item in ledger.instruction_counts
        }
        self.assertEqual(counts.get("conditional_branch_not_taken"), 1)
        self.assertNotIn("conditional_branch_taken", counts)

    def test_multiple_returns_normalized_to_epilogue(self):
        plan = FunctionAssemblyPlan.model_validate({
            "function_name": "MultiReturnFunc",
            "selected_source_path": ["x > 0: true", "return"],
            "sections": [{
                "section_name": "straight_line",
                "execution_count": 1,
                "instructions": [
                    "push {r7, lr}",
                    "sub sp, #12",
                    "cmp r0, #0",
                    "b.n else_arm",
                    "movs r0, #27",
                    "bx lr",
                    "else_arm:",
                    "movs r0, #0",
                    "adds r7, #12",
                    "pop {r7, pc}",
                ],
            }],
        })
        errors = StagedPredictor._validate_assembly_plan(plan)
        self.assertEqual(errors, [])
        # The early 'bx lr' must have been neutralized to 'nop'
        self.assertEqual(plan.sections[0].instructions[5], "nop")
        self.assertEqual(plan.sections[0].instructions[-1], "pop {r7, pc}")

    def test_source_arithmetic_coverage_rejects_an_empty_loop_stub(self):
        body = """
        void Kernel(int *a, int *b, int *c, int divisor) {
          for (int i = 0; i < 8; ++i) {
            c[i] = (a[i] * b[i] + b[i] * c[i]) / divisor;
          }
        }
        """
        incomplete = FunctionAssemblyPlan.model_validate({
            "function_name": "Kernel",
            "selected_source_path": ["eight loop iterations", "return"],
            "sections": [{
                "section_name": "loop_body",
                "execution_count": 8,
                "instructions": ["ldr r3, [r7, #4]", "adds r3, #1"],
            }, {
                "section_name": "epilogue_and_return",
                "execution_count": 1,
                "instructions": ["pop {r7, pc}"],
            }],
        })
        incomplete_ledger = StagedPredictor._assembly_plan_to_ledger(
            incomplete, {"Kernel": body}
        )
        errors = StagedPredictor._validate_source_operation_coverage(
            "Kernel", body, incomplete, incomplete_ledger, ""
        )
        self.assertTrue(any("static multiply" in error for error in errors))
        self.assertTrue(any("static integer_divide" in error for error in errors))

        complete = FunctionAssemblyPlan.model_validate({
            "function_name": "Kernel",
            "selected_source_path": ["eight loop iterations", "return"],
            "sections": [{
                "section_name": "loop_body",
                "execution_count": 8,
                "instructions": [
                    "mul r2, r0, r1", "mul r3, r1, r2", "udiv r3, r3, r4",
                ],
            }, {
                "section_name": "epilogue_and_return",
                "execution_count": 1,
                "instructions": ["pop {r7, pc}"],
            }],
        })
        complete_ledger = StagedPredictor._assembly_plan_to_ledger(
            complete, {"Kernel": body}
        )
        self.assertEqual(
            StagedPredictor._validate_source_operation_coverage(
                "Kernel", body, complete, complete_ledger, ""
            ),
            [],
        )

    def test_statement_blocks_require_complete_unique_source_coverage(self):
        plan = FunctionAssemblyPlan.model_validate({
            "function_name": "Kernel",
            "selected_source_path": ["straight line"],
            "sections": [{
                "section_name": "straight_line",
                "execution_count": 1,
                "statement_blocks": [{
                    "block_id": "source_1",
                    "statement_id": 1,
                    "source_statement": "x = a + b",
                    "instructions": ["add r0, r1"],
                }, {
                    "block_id": "epilogue",
                    "statement_id": None,
                    "source_statement": "compiler epilogue",
                    "instructions": ["bx lr"],
                }],
            }],
        })
        self.assertEqual(
            StagedPredictor._validate_statement_block_coverage(
                "Kernel", plan, ["x = a + b", "y = x * c"], [1]
            ),
            [],
        )
        errors = StagedPredictor._validate_statement_block_coverage(
            "Kernel", plan, ["x = a + b", "y = x * c"], [1, 2]
        )
        self.assertTrue(any("missing source statement block IDs [2]" in e for e in errors))

    def test_repeated_statement_instruction_sequence_is_rejected(self):
        repeated = [
            "ldr r3, [r7, #4]", "lsls r3, r3, #1", "ldr r2, [r7, #8]",
            "add r3, r2", "ldrh r3, [r3]", "uxth r3, r3", "mov r2, r3",
            "str r2, [r7, #12]",
        ] * 3
        plan = FunctionAssemblyPlan.model_validate({
            "function_name": "Collapsed",
            "selected_source_path": ["return"],
            "sections": [{
                "section_name": "straight_line",
                "execution_count": 1,
                "statement_blocks": [{
                    "block_id": "collapsed_source",
                    "statement_id": 1,
                    "source_statement": "x = table[i]",
                    "instructions": repeated,
                }, {
                    "block_id": "epilogue",
                    "statement_id": None,
                    "source_statement": "compiler epilogue",
                    "instructions": ["bx lr"],
                }],
            }],
        })
        errors = StagedPredictor._validate_assembly_plan(plan)
        self.assertTrue(any("generation collapse" in error for error in errors))

    def test_stage_varying_fft_loops_prove_32_inner_executions(self):
        body = """
        static void Butterfly(int *a) {
          unsigned num_bf = 1U;
          unsigned step = 2U;
          for (unsigned stage = 0U; stage < 4U; ++stage) {
            for (unsigned group = 0U; group < POINTS; group += step) {
              for (unsigned pair = 0U; pair < num_bf; ++pair) {
                a[group + pair] = a[group + pair] * a[pair];
              }
            }
            num_bf <<= 1U;
            step <<= 1U;
          }
        }
        """
        facts = "#define POINTS 16U"
        obligations = StagedPredictor._loop_execution_obligations(
            "Butterfly", body, {}, facts
        )
        self.assertTrue(any("COUNT = 32 times" in item for item in obligations))
        self.assertEqual(
            StagedPredictor._source_arithmetic_obligations(body, facts)["multiply"],
            32,
        )


if __name__ == "__main__":
    unittest.main()

