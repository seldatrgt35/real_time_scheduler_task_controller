from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class StaticAssemblyFunction(BaseModel):
    """The only structure the LLM is allowed to produce."""

    function_name: str = Field(min_length=1, max_length=128)
    # A single static GCC function should not need a dynamic trace-sized
    # response.  This bound is also emitted in Ollama's JSON schema, so the
    # decoder can close the response before exhausting the output budget.
    assembly: list[str] = Field(min_length=1, max_length=320)
    unresolved: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def clean_lines(self) -> "StaticAssemblyFunction":
        self.assembly = [line.strip() for line in self.assembly if line.strip()]
        if not self.assembly:
            raise ValueError("assembly must contain at least one non-empty line")
        return self


class SemanticAssemblyReview(BaseModel):
    """Compact second-pass verdict comparing one C function with its assembly."""

    function_name: str = Field(min_length=1, max_length=128)
    verdict: Literal["PASS", "FAIL"]
    errors: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def verdict_matches_errors(self) -> "SemanticAssemblyReview":
        self.errors = [error.strip() for error in self.errors if error.strip()]
        if self.verdict == "PASS" and self.errors:
            raise ValueError("PASS review must not contain errors")
        if self.verdict == "FAIL" and not self.errors:
            raise ValueError("FAIL review requires at least one concrete error")
        return self


class StaticInstructionClassCount(BaseModel):
    instruction_class: str
    static_count: int = Field(ge=0)
    cycles_each: int = Field(ge=1)
    static_cycle_sum: int = Field(ge=0)


class StaticFunctionAnalysis(BaseModel):
    function_name: str
    assembly: list[str]
    instruction_count: int = Field(ge=0)
    instruction_classes: list[StaticInstructionClassCount]
    static_core_cycle_sum: int = Field(ge=0)
    unresolved: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)


class StaticAssemblyReport(BaseModel):
    analysis_status: Literal["SUPPORTED", "VALIDATION_REQUIRED"]
    provider: str = "ollama"
    model: str
    target_function: str
    compiler_profile: str
    functions: list[StaticFunctionAnalysis]
    estimated_execution_cycles: int | None = None
    estimated_execution_us: float | None = None
    warnings: list[str] = Field(default_factory=list)
