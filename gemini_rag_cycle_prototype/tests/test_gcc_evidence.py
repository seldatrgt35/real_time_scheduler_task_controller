from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gemini_rag_cycle_prototype.gcc_evidence import retrieve_gcc_evidence
from gemini_rag_cycle_prototype.gcc_evidence import _query_tags


class GccEvidenceTest(unittest.TestCase):
    def test_loop_and_helper_query_retrieves_only_relevant_patterns(self) -> None:
        records = [
            {"pattern": "loop", "tags": ["loop", "array"]},
            {"pattern": "call", "tags": ["helper_call", "call_boundary"]},
            {"pattern": "unrelated", "tags": ["floating_point"]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "patterns.json"
            path.write_text(json.dumps(records), encoding="utf-8")
            hits = retrieve_gcc_evidence(
                "void Task(void) { for (int i=0; i<4; ++i) Helper(a[i]); }",
                path,
            )
        names = [hit["pattern"] for hit in hits]
        self.assertIn("loop", names)
        self.assertIn("call", names)
        self.assertNotIn("unrelated", names)

    def test_retrieval_order_is_deterministic(self) -> None:
        root = Path(__file__).resolve().parents[2]
        path = root / "gemini_rag_cycle_prototype" / "knowledge" / "gcc_o0_patterns.json"
        source = "void Task(volatile int *a) { for (int i=0;i<8;i++) a[i]=Helper(a[i]); }"
        first = retrieve_gcc_evidence(source, path)
        second = retrieve_gcc_evidence(source, path)
        self.assertEqual(
            [record["pattern"] for record in first],
            [record["pattern"] for record in second],
        )
        self.assertLessEqual(len(first), 5)

    def test_single_helper_call_is_detected_without_inventing_stack(self) -> None:
        tags = _query_tags("void Task(void) { Helper(value); }")
        self.assertIn("helper_call", tags)
        self.assertNotIn("stack", tags)
        self.assertNotIn("assignment", tags)

    def test_only_selected_function_body_is_tagged(self) -> None:
        source = "void Other(void){ Helper(); } void Task(void){ value = 1; }"
        tags = _query_tags(source, "Task")
        self.assertNotIn("helper_call", tags)
        self.assertIn("assignment", tags)

    def test_generated_call_uses_relocation_symbol(self) -> None:
        root = Path(__file__).resolve().parents[2]
        path = root / "gemini_rag_cycle_prototype" / "knowledge" / "gcc_o0_patterns.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        call = next(record for record in records if record["pattern"] == "single_argument_function_call")
        instruction = next(
            instruction
            for block in call["basic_blocks"]
            for instruction in block["instructions"]
            if instruction["opcode"] == "bl"
        )
        self.assertEqual(instruction["callee"], "PatternLeafIncrement")
        self.assertEqual(instruction["relocation"], "R_ARM_THM_CALL")
        self.assertEqual(instruction["operands"], "PatternLeafIncrement")

    def test_bounded_loop_execution_formulas_match_cfg(self) -> None:
        root = Path(__file__).resolve().parents[2]
        path = root / "gemini_rag_cycle_prototype" / "knowledge" / "gcc_o0_patterns.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        loop = next(record for record in records if record["pattern"] == "bounded_array_loop")
        self.assertEqual(
            [block["execution_formula"] for block in loop["basic_blocks"]],
            ["1", "N", "N+1", "1"],
        )
        branch = next(
            instruction
            for block in loop["basic_blocks"]
            for instruction in block["instructions"]
            if instruction["instruction_class"] == "conditional_branch"
        )
        self.assertEqual(branch["taken_executions"], "N")
        self.assertEqual(branch["not_taken_executions"], "1")

    def test_padding_after_return_is_explicitly_non_executed(self) -> None:
        root = Path(__file__).resolve().parents[2]
        path = root / "gemini_rag_cycle_prototype" / "knowledge" / "gcc_o0_patterns.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        volatile = next(record for record in records if record["pattern"] == "volatile_pointer_read_write")
        self.assertTrue(volatile["non_executed_padding"])
        self.assertTrue(all(not item["executed_on_normal_path"] for item in volatile["non_executed_padding"]))


if __name__ == "__main__":
    unittest.main()
