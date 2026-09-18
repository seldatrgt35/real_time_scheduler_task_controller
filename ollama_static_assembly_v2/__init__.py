"""Version 2: source-to-static-assembly experiment.

This package intentionally lives beside, rather than replacing,
``ollama_staged_cycle_prototype``.
"""

from .predictor import StaticAssemblyPredictor
from .schemas import StaticAssemblyReport

__all__ = ["StaticAssemblyPredictor", "StaticAssemblyReport"]
