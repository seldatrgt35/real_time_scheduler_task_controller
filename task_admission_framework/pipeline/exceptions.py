"""Custom exceptions for STAR analysis pipeline failures."""

from __future__ import annotations


class PipelineError(Exception):
    """Base class for analysis pipeline failures."""


class PipelineStageError(PipelineError):
    """Raised when one named analysis pipeline stage fails."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"{stage} failed: {message}")
        self.stage = stage
        self.message = message
