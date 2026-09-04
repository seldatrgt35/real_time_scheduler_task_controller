from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from pydantic import BaseModel

from gemini_rag_cycle_prototype.cli import create_client
from gemini_rag_cycle_prototype.ollama_client import OllamaClient


class SmallResponse(BaseModel):
    value: int


class OllamaClientTest(unittest.TestCase):
    def client(self, dimensions: int = 3) -> OllamaClient:
        return OllamaClient(
            model="qwen-test", embedding_model="embed-test",
            embedding_dimensions=dimensions, base_url="http://localhost:11434",
        )

    def test_three_documents_return_three_ordered_embeddings(self):
        client = self.client()
        client._post = lambda endpoint, payload: {
            "embeddings": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        }
        result = client.embed_documents(["first", "second", "third"])
        self.assertEqual(result, [
            [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
        ])

    def test_embedding_count_mismatch_is_rejected(self):
        client = self.client()
        client._post = lambda endpoint, payload: {"embeddings": [[1, 2, 3]]}
        with self.assertRaisesRegex(
            ValueError, "expected 2, received 1"
        ):
            client.embed_documents(["first", "second"])

    def test_embedding_dimension_mismatch_is_rejected(self):
        client = self.client()
        client._post = lambda endpoint, payload: {"embeddings": [[1, 2]]}
        with self.assertRaisesRegex(
            ValueError, "expected 3, received 2"
        ):
            client.embed_query("query")

    def test_predict_uses_schema_and_validates_response(self):
        client = self.client()
        captured = {}

        def fake_post(payload):
            captured.update(payload)
            return {"response": json.dumps({"value": 7})}

        client._generate_streaming = fake_post
        parsed, raw = client.predict("prompt", response_schema=SmallResponse)
        self.assertEqual(parsed.value, 7)
        self.assertEqual(json.loads(raw), {"value": 7})
        self.assertEqual(captured["model"], "qwen-test")
        self.assertEqual(captured["format"]["title"], "SmallResponse")
        self.assertEqual(captured["options"]["temperature"], 0.0)

    def test_cli_provider_factory_selects_ollama(self):
        with patch.dict("os.environ", {"OLLAMA_MODEL": "qwen-local"}):
            client = create_client("ollama")
        self.assertIsInstance(client, OllamaClient)
        self.assertEqual(client.model, "qwen-local")

    def test_opcode_used_as_timing_class_is_normalized(self):
        from gemini_rag_cycle_prototype.schemas import InstructionCycleEstimate

        item = InstructionCycleEstimate.model_validate({
            "instruction_class": "sub",
            "dynamic_count": 4,
            "cycles_each": 1,
            "total_cycles": 4,
            "evidence": "estimated Thumb-2 instruction",
        })
        self.assertEqual(item.instruction_class, "alu_move_compare_shift")

    def test_pop_alias_selects_transfer_or_pc_refill_from_timing(self):
        from gemini_rag_cycle_prototype.schemas import InstructionCycleEstimate

        common = {
            "instruction_class": "pop", "dynamic_count": 2,
            "evidence": "estimated Thumb-2 instruction",
        }
        transfer = InstructionCycleEstimate.model_validate({
            **common, "cycles_each": 1, "total_cycles": 2,
        })
        refill = InstructionCycleEstimate.model_validate({
            **common, "cycles_each": 3, "total_cycles": 6,
        })
        self.assertEqual(
            transfer.instruction_class, "push_or_pop_register_transfer"
        )
        self.assertEqual(
            refill.instruction_class, "pop_pc_pipeline_refill_worst_case"
        )

    def test_compact_response_normalizes_redundant_aggregate_arithmetic(self):
        from gemini_rag_cycle_prototype.schemas import CompactPredictionResponse

        payload = {
            "analysis_status": "PARTIAL",
            "function_name": "Task",
            "hardware_profile_id": "s32k148-cortex-m4-48mhz-gcc-o0-pflash",
            "source_analysis": {},
            "instruction_cycle_ledger": [{
                "instruction_class": "sub",
                "dynamic_count": 4,
                "cycles_each": 1,
                "total_cycles": 4,
                "evidence": "source analysis",
            }],
            "estimated_source_execution_cycles": 99,
            "estimated_source_execution_us": 99.0,
            "confidence_percent": 40,
            "estimation_reasoning_summary": "test",
        }
        parsed = CompactPredictionResponse.model_validate(payload)
        self.assertEqual(parsed.estimated_source_execution_cycles, 4)
        self.assertEqual(parsed.estimated_source_execution_us, 4 / 48.0)
        self.assertIn("normalized", parsed.warnings[-1])


if __name__ == "__main__":
    unittest.main()
