from __future__ import annotations

from typing import Type

from pydantic import BaseModel

from gemini_rag_cycle_prototype.ollama_client import OllamaClient


class StagedOllamaClient(OllamaClient):
    """Keep staged CFG repair guidance out of the shared Ollama client."""

    _response_schema_name = ""

    def predict(
        self, prompt: str, response_schema: Type[BaseModel]
    ) -> tuple[BaseModel, str]:
        self._response_schema_name = response_schema.__name__
        try:
            return super().predict(prompt, response_schema=response_schema)
        finally:
            self._response_schema_name = ""

    def _repair_prompt(
        self,
        original_prompt: str,
        error: Exception,
        schema_name: str | None = None,
    ) -> str:
        active_schema = schema_name or self._response_schema_name
        if active_schema != "FunctionBlockPlan":
            return (
                original_prompt
                + "\n\nVALIDATION REPAIR REQUIRED\n"
                + "Regenerate the complete JSON response from scratch. Return "
                  "JSON only and satisfy the supplied response schema. Do not "
                  "return a patch or explanation.\nValidator diagnostics:\n"
                + str(error)
            )
        return (
            original_prompt
            + "\n\nVALIDATION REPAIR REQUIRED\n"
            + "Regenerate the complete FunctionBlockPlan JSON from scratch. "
              "Return JSON only. Branch control transfers belong only in "
              "edges; never put conditional_branch_taken, "
              "conditional_branch_not_taken, or "
              "unconditional_branch_with_refill in instruction_counts. For "
              "each conditional source block, emit exactly one taken and one "
              "not-taken edge whose execution counts sum to that block's "
              "execution_count_per_invocation. Successors must exactly match "
              "outgoing edge targets.\nValidator diagnostics:\n"
            + str(error)
        )
