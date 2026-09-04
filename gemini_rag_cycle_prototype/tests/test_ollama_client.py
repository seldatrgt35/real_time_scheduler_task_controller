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


if __name__ == "__main__":
    unittest.main()
