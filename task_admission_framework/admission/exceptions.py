"""Custom exceptions for STAR admission control."""

from __future__ import annotations


class AdmissionError(Exception):
    """Base class for admission controller failures."""

