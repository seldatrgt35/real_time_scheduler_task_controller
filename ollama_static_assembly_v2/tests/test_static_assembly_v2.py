from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ollama_static_assembly_v2.predictor import StaticAssemblyPredictor
from ollama_static_assembly_v2.schemas import StaticAssemblyFunction


ROOT = Path(__file__).resolve().parents[2]


class FakeClient:
    model = "fake-static-assembly"

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def predict(self, prompt: str, response_schema):
        self.prompts.append(prompt)
        data = self.responses.pop(0)
        raw = json.dumps(data)
        return response_schema.model_validate(data), raw


class StaticAssemblyV2Tests(unittest.TestCase):
    def predictor(self, client: FakeClient) -> StaticAssemblyPredictor:
        return StaticAssemblyPredictor(ROOT, client)

    def test_prompt_requests_static_assembly_not_path_or_cycle_math(self):
        client = FakeClient([{
            "function_name": "Task",
            "assembly": [
                "Task:", "push {r7, lr}", "add r7, sp, #0", "bl Helper",
                "cmp r0, #0", "beq .Ldone", "bl Helper", ".Ldone:", "pop {r7, pc}",
            ],
            "unresolved": [],
        }, {
            "function_name": "Task",
            "verdict": "PASS",
            "errors": [],
        }, {
            "function_name": "Helper",
            "assembly": ["Helper:", "push {r7}", "mov r0, r0", "pop {r7}", "bx lr"],
            "unresolved": [],
        }, {
            "function_name": "Helper",
            "verdict": "PASS",
            "errors": [],
        }])
        source = """
        static int Helper(int x) { return x; }
        void Task(void) { if (Helper(1)) { Helper(2); } }
        """
        report, _ = self.predictor(client).predict(source, "Task")
        self.assertEqual("SUPPORTED", report.analysis_status)
        prompt = client.prompts[0]
        self.assertIn("STATIC", prompt)
        self.assertIn("NEVER unroll a loop", prompt)
        self.assertIn("Do not calculate cycles", prompt)
        self.assertIn("HARD LIMIT of 480 items", prompt)
        self.assertIn("do not emit their", prompt)
        self.assertIn("SYMBOL KIND CONTRACT", prompt)
        self.assertIn("subscripted DATA expression", prompt)
        self.assertIn("using its C width", prompt)
        self.assertIn("Do not invent incoming argument", prompt)
        self.assertIn("Preserve the declared C access width", prompt)
        self.assertIn("stack frame self-consistent", prompt)
        self.assertIn("Preserve loop initialization", prompt)
        self.assertIn("Treat `r0`-`r3` and `r12` as call-clobbered", prompt)
        self.assertIn("Every global or static DATA symbol referenced", prompt)
        self.assertIn("FUNCTION SIGNATURE AND ABI CONTRACT", prompt)
        self.assertIn("Task: `void Task(void)`; entry no incoming argument registers", prompt)
        self.assertIn("Helper: `static int Helper(int x)`; entry r0 <- int x", prompt)
        self.assertIn("CALL-SITE ARGUMENT CONTRACT FOR Task", prompt)
        self.assertIn("before `bl Helper`: r0 <- `1`", prompt)
        self.assertIn("DATA TYPE AND ACCESS-WIDTH CONTRACT", prompt)
        self.assertNotIn('"execution_count"', prompt)
        review_prompt = client.prompts[1]
        self.assertIn("SEMANTIC REVIEW", review_prompt)
        self.assertIn("Do not generate replacement assembly", review_prompt)
        self.assertIn("pointer/scalar register dataflow", review_prompt)
        self.assertNotIn("calculate cycles", review_prompt.lower().replace("do not calculate cycles", ""))

    def test_initialized_data_array_is_not_callable(self):
        declarations = """
        static const uint8_t sbox[256] = { 1, 2, 3 };
        static uint32_t state[2][2];
        extern volatile uint8_t sink;
        static void Helper(void);
        static void Apply(uint8_t parameter_state[16], uint32_t parameter_i);
        static uint8_t Transform(uint8_t parameter_b);
        """
        symbols = StaticAssemblyPredictor._data_symbols(declarations)
        self.assertEqual({"sbox", "state", "sink"}, symbols)
        type_contracts = StaticAssemblyPredictor._data_type_contracts(declarations)
        self.assertIn("sbox: static const uint8_t[256]", type_contracts)
        self.assertIn("state: static uint32_t[2][2]", type_contracts)
        self.assertIn("sink: extern volatile uint8_t", type_contracts)
        self.assertNotIn("parameter_state", type_contracts)

        draft = StaticAssemblyFunction(
            function_name="Task",
            assembly=["Task:", "push {r7, lr}", "bl sbox", "pop {r7, pc}"],
        )
        errors = self.predictor(FakeClient([]))._audit(
            draft, "Task", "void Task(void) { value = sbox[index]; }",
            {"Task": ""}, declarations=declarations,
        )
        self.assertTrue(any("call data symbol" in error for error in errors))

    def test_llm_schema_caps_static_assembly_length(self):
        schema = StaticAssemblyFunction.model_json_schema()
        self.assertEqual(480, schema["properties"]["assembly"]["maxItems"])

    def test_loop_requires_backward_branch(self):
        draft = StaticAssemblyFunction(
            function_name="Loop",
            assembly=["Loop:", "push {r7}", "adds r0, #1", "pop {r7}", "bx lr"],
        )
        predictor = self.predictor(FakeClient([]))
        errors = predictor._audit(
            draft, "Loop", "void Loop(void) { for (int i=0; i<4; ++i) {} }",
            {"Loop": ""},
        )
        self.assertTrue(any("backward branch" in error for error in errors))

    def test_backward_conditional_branch_is_accepted(self):
        draft = StaticAssemblyFunction(
            function_name="Loop",
            assembly=[
                "Loop:", "push {r7}", "movs r0, #0", ".Lbody:",
                "adds r0, #1", "cmp r0, #4", "blt .Lbody", "pop {r7}", "bx lr",
            ],
        )
        errors = self.predictor(FakeClient([]))._audit(
            draft, "Loop", "void Loop(void) { for (int i=0; i<4; ++i) {} }",
            {"Loop": ""},
        )
        self.assertFalse(errors)

    def test_each_static_call_site_must_be_present(self):
        draft = StaticAssemblyFunction(
            function_name="Task",
            assembly=["Task:", "push {r7, lr}", "bl Helper", "pop {r7, pc}"],
        )
        errors = self.predictor(FakeClient([]))._audit(
            draft, "Task",
            "void Task(void) { if (x) Helper(); else Helper(); }",
            {"Task": "", "Helper": ""},
        )
        self.assertTrue(any("2 static call site" in error for error in errors))

    def test_repeated_generation_is_rejected(self):
        unit = [
            "ldr r0, [r7]", "adds r0, #1", "str r0, [r7]", "cmp r0, #9",
            "bne .Lloop", "mov r1, r0", "eor r1, r0", "str r1, [r7, #4]",
        ]
        draft = StaticAssemblyFunction(
            function_name="Task",
            assembly=["Task:", "push {r7}"] + unit * 3 + ["pop {r7}", "bx lr"],
        )
        errors = self.predictor(FakeClient([]))._audit(
            draft, "Task", "void Task(void) {}", {"Task": ""},
        )
        self.assertTrue(any("repeated 8-instruction" in error for error in errors))

    def test_static_counts_are_python_derived(self):
        predictor = self.predictor(FakeClient([]))
        draft = StaticAssemblyFunction(
            function_name="Leaf",
            assembly=["Leaf:", "push {r7}", "ldr r0, [r7]", "adds r0, #1", "pop {r7}", "bx lr"],
        )
        analysis = predictor._analyze(draft, [])
        self.assertEqual(5, analysis.instruction_count)
        self.assertGreater(analysis.static_core_cycle_sum, 0)
        self.assertFalse(analysis.validation_errors)
    def test_data_symbol_call_with_bl_is_rejected(self):
        draft = StaticAssemblyFunction(
            function_name="Task",
            assembly=["Task:", "push {r7, lr}", "bl s_aes_sbox", "pop {r7, pc}"],
        )
        predictor = self.predictor(FakeClient([]))
        decls = "static const uint8_t s_aes_sbox[256];"
        errors = predictor._audit(draft, "Task", "void Task(void) {}", {"Task": ""}, declarations=decls)
        self.assertTrue(any("attempts to call data symbol 's_aes_sbox' with BL" in e for e in errors))

    def test_referenced_data_symbol_must_remain_in_assembly(self):
        predictor = self.predictor(FakeClient([]))
        declarations = "static const uint8_t lookup[256] = { 0 };"
        body = "void Apply(uint8_t *state) { state[0] = lookup[state[0]]; }"

        missing = StaticAssemblyFunction(
            function_name="Apply",
            assembly=["Apply:", "push {r7}", "ldrb r0, [r0]", "pop {r7}", "bx lr"],
        )
        errors = predictor._audit(
            missing, "Apply", body, {"Apply": body}, declarations=declarations,
        )
        self.assertTrue(any("assembly never names it" in error for error in errors))

        preserved = StaticAssemblyFunction(
            function_name="Apply",
            assembly=[
                "Apply:", "push {r7}", "ldr r2, =lookup", "ldrb r1, [r0]",
                "ldrb r1, [r2, r1]", "strb r1, [r0]", "pop {r7}", "bx lr",
            ],
        )
        errors = predictor._audit(
            preserved, "Apply", body, {"Apply": body}, declarations=declarations,
        )
        self.assertFalse(any("assembly never names it" in error for error in errors))

    def test_numeric_branch_offset_target_is_rejected(self):
        draft = StaticAssemblyFunction(
            function_name="Task",
            assembly=["Task:", "push {r7}", "loop_start:", "cmp r0, #4", "bls.n 10 <Task+0x10>", "pop {r7}", "bx lr"],
        )
        predictor = self.predictor(FakeClient([]))
        errors = predictor._audit(draft, "Task", "void Task(void) {}", {"Task": ""})
        self.assertTrue(any("numeric or an offset" in e for e in errors))

    def test_data_directives_are_rejected(self):
        draft = StaticAssemblyFunction(
            function_name="Task",
            assembly=["Task:", "push {r7}", ".word 0x1234", "pop {r7}", "bx lr"],
        )
        predictor = self.predictor(FakeClient([]))
        errors = predictor._audit(draft, "Task", "void Task(void) {}", {"Task": ""})
        self.assertTrue(any("assembly contains data directive '.word 0x1234'" in e for e in errors))

    def test_stack_offset_overflow_is_rejected(self):
        draft = StaticAssemblyFunction(
            function_name="Task",
            assembly=["Task:", "push {r7}", "sub sp, #16", "ldr r0, [r7, #24]", "adds r7, #16", "pop {r7}", "bx lr"],
        )
        predictor = self.predictor(FakeClient([]))
        errors = predictor._audit(draft, "Task", "void Task(void) {}", {"Task": ""})
        self.assertTrue(any("exceeds allocated frame size #16" in e for e in errors))
        self.assertTrue(any("with width 4 requires 28 bytes" in e for e in errors))

    def test_loop_relational_operator_consistency_is_checked(self):
        draft = StaticAssemblyFunction(
            function_name="Task",
            assembly=["Task:", "push {r7}", "loop:", "adds r0, #1", "cmp r0, #16", "bls loop", "pop {r7}", "bx lr"],
        )
        predictor = self.predictor(FakeClient([]))
        body = "void Task(void) { for (int i = 0; i < 16; ++i) {} }"
        errors = predictor._audit(draft, "Task", body, {"Task": ""})
        self.assertTrue(any("loop condition is strictly '< 16'" in e for e in errors))

    def test_pointer_declaration_and_dereference_are_not_multiplication(self):
        draft = StaticAssemblyFunction(
            function_name="Step",
            assembly=[
                "Step:", "push {r7}", "ldr r1, [r0]", "asrs r1, r1, #1",
                "str r1, [r0]", "pop {r7}", "bx lr",
            ],
        )
        body = "void Step(int32_t *x) { int32_t value = *x; *x = value >> 1; }"
        errors = self.predictor(FakeClient([]))._audit(
            draft, "Step", body, {"Step": body},
        )
        self.assertFalse(any("multiplication" in error for error in errors))

    def test_muls_variant_satisfies_variable_multiplication_audit(self):
        draft = StaticAssemblyFunction(
            function_name="Multiply",
            assembly=["Multiply:", "push {r7}", "muls r0, r1", "pop {r7}", "bx lr"],
        )
        body = "int Multiply(int a, int b) { return a * b; }"
        errors = self.predictor(FakeClient([]))._audit(
            draft, "Multiply", body, {"Multiply": body},
        )
        self.assertFalse(any("multiplication" in error for error in errors))

    def test_semantic_reviewer_can_regenerate_only_failed_function(self):
        client = FakeClient([
            {
                "function_name": "Task",
                "assembly": [
                    "Task:", "push {r7}", "ldr r0, =g_value", "movs r1, #0",
                    "str r1, [r0]", "pop {r7}", "bx lr",
                ],
                "unresolved": [],
            },
            {
                "function_name": "Task",
                "verdict": "FAIL",
                "errors": ["C increments g_value, but assembly stores zero without loading its value."],
            },
            {
                "function_name": "Task",
                "assembly": [
                    "Task:", "push {r7}", "ldr r0, =g_value", "ldr r1, [r0]",
                    "adds r1, r1, #1", "str r1, [r0]", "pop {r7}", "bx lr",
                ],
                "unresolved": [],
            },
            {
                "function_name": "Task",
                "verdict": "PASS",
                "errors": [],
            },
        ])
        source = "static int32_t g_value; void Task(void) { g_value += 1; }"
        with patch.dict(os.environ, {"OLLAMA_V2_SEMANTIC_ATTEMPTS": "2"}):
            report, raw = self.predictor(client).predict(source, "Task")

        self.assertEqual("SUPPORTED", report.analysis_status)
        self.assertEqual(4, len(client.prompts))
        self.assertEqual(4, len(raw))
        self.assertIn("semantic reviewer:", client.prompts[2])
        self.assertIn("stores zero", client.prompts[2])

    def test_legalize_assembly_fixes_stack_frame_and_loop_branch(self):
        draft = StaticAssemblyFunction(
            function_name="Worker",
            assembly=[
                "Worker:",
                "push {r7}",
                "sub sp, #16",
                "add r7, sp, #0",
                "movs r3, #0",
                "str r3, [r7, #28]",  # requires 32 bytes (offset 28 + 4)
                "b.n loop_start",
                "loop_body:",
                "adds r3, #1",
                "str r3, [r7, #28]",
                "cmp r3, #10",
                "bls.n loop_body",    # loop condition is < 10, should be blt
                "adds r7, #16",
                "mov sp, r7",
                "pop {r7}",
                "bx lr",
            ],
            unresolved=[],
        )
        body = "void Worker(void) { for (int i = 0; i < 10; ++i) { ... } }"
        legalized = StaticAssemblyPredictor._legalize_assembly(draft, body)
        # 1. Stack frame enlarged to 32 bytes in prologue and epilogue
        self.assertIn("sub sp, #32", legalized.assembly)
        self.assertIn("adds r7, #32", legalized.assembly)
        # 2. Missing loop_start: label created right before loop_body:
        self.assertIn("loop_start:", legalized.assembly)
        # 3. bls.n converted to blt.n
        self.assertIn("blt.n loop_body", legalized.assembly)
        self.assertNotIn("bls.n loop_body", legalized.assembly)

    def test_filter_spurious_review_errors(self):
        raw_errors = [
            "semantic reviewer: Function does not preserve r0 across the call to Helper.",
            "semantic reviewer: Assembly fails to preserve r12 register.",
            "semantic reviewer: Load from s_acc_state into r0 which is semantically correct.",
            "semantic reviewer: Real arithmetic error: missing division by 10.",
        ]
        filtered = StaticAssemblyPredictor._filter_spurious_review_errors(raw_errors)
        self.assertEqual(1, len(filtered))
        self.assertIn("Real arithmetic error", filtered[0])

    def test_predict_computes_execution_cycles(self):
        client = FakeClient([
            {
                "function_name": "Task",
                "assembly": [
                    "Task:", "push {r7, lr}", "sub sp, #16", "add r7, sp, #0",
                    "movs r3, #0", "str r3, [r7, #4]",
                    "b.n .Lcond",
                    ".Lbody:",
                    "ldr r0, [r7, #4]", "bl Helper",
                    "ldr r3, [r7, #4]", "adds r3, #1", "str r3, [r7, #4]",
                    ".Lcond:",
                    "ldr r3, [r7, #4]", "cmp r3, #4", "blt .Lbody",
                    "adds r7, #16", "mov sp, r7", "pop {r7, pc}",
                ],
                "unresolved": [],
            },
            {
                "function_name": "Task",
                "verdict": "PASS",
                "errors": [],
            },
            {
                "function_name": "Helper",
                "assembly": ["Helper:", "push {r7}", "mov r0, r0", "pop {r7}", "bx lr"],
                "unresolved": [],
            },
            {
                "function_name": "Helper",
                "verdict": "PASS",
                "errors": [],
            },
        ])
        source = """
        static int Helper(int x) { return x; }
        void Task(void) { for (int i = 0; i < 4; ++i) { Helper(i); } }
        """
        report, _ = self.predictor(client).predict(source, "Task")
        self.assertEqual("SUPPORTED", report.analysis_status)
        self.assertIsNotNone(report.estimated_execution_cycles)
        self.assertIsNotNone(report.estimated_execution_cycles)
        self.assertGreater(report.estimated_execution_cycles, 0)
        self.assertIsNotNone(report.estimated_execution_us)

    def test_audit_flags_missing_parameter_array_stores(self):
        draft = StaticAssemblyFunction(
            function_name="ArrayMutator",
            assembly=[
                "ArrayMutator:",
                "push {r7}",
                "sub sp, #16",
                "add r7, sp, #0",
                "movs r3, #42",
                "str r3, [r7, #4]",  # stores only to local stack
                "adds r7, #16",
                "mov sp, r7",
                "pop {r7}",
                "bx lr",
            ],
            unresolved=[],
        )
        body = "void ArrayMutator(int16_t real[16]) { real[0] = 42; }"
        errors = self.predictor(FakeClient([]))._audit(draft, "ArrayMutator", body, {"ArrayMutator": body})
        self.assertTrue(any("source assigns to parameter array(s) 'real'" in e for e in errors))

    def test_prompt_repair_handles_repetition_without_dumping_garbage(self):
        draft = StaticAssemblyFunction(
            function_name="Looper",
            assembly=["mov r0, r1"] * 100,
            unresolved=[],
        )
        predictor = self.predictor(FakeClient([]))
        prompt = predictor._prompt(
            "Looper", "void Looper(void) {}", "", "",
            {"Looper"}, set(), "", "", "", "",
            audit_errors=["assembly reached the output ceiling and is probably truncated"],
            previous=draft,
        )
        self.assertIn("entered a repetitive loop or was truncated", prompt)
        # Should not dump 60+ repeated mov r0, r1 instructions
        self.assertNotIn("mov r0, r1\n" * 50, prompt)

    def test_evaluate_cfg_dag_selects_longest_mutually_exclusive_branch(self):
        predictor = self.predictor(FakeClient([]))
        assembly = [
            "BranchFn:",
            "cmp r0, #0",
            "bgt ArmB",
            "movs r0, #1",
            "b End",
            "ArmB:",
            "movs r0, #10",
            "adds r0, #1",
            "adds r0, #2",
            "End:",
            "bx lr",
        ]
        res = predictor._evaluate_cfg_dag(assembly)
        self.assertIsNotNone(res)
        cycles, callees = res
        self.assertLess(cycles, 18)
        self.assertGreaterEqual(cycles, 11)


if __name__ == "__main__":
    unittest.main()

