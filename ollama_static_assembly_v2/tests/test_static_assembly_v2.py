from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

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
            "function_name": "Helper",
            "assembly": ["Helper:", "push {r7}", "mov r0, r0", "pop {r7}", "bx lr"],
            "unresolved": [],
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
        self.assertNotIn('"execution_count"', prompt)

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


if __name__ == "__main__":
    unittest.main()
