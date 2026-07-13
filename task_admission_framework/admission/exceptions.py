"""Custom exceptions for STAR admission control."""

from __future__ import annotations


class AdmissionError(Exception):
    """Base class for admission controller failures."""


class CalibrationProfileMissingError(AdmissionError):
    """Raised when calibrated mode is requested without calibration metadata."""
