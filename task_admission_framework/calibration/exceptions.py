"""Calibration loading and estimation exceptions."""


class CalibrationError(Exception):
    """Base class for calibration failures."""


class CalibrationLoadError(CalibrationError):
    """Raised when a calibration profile cannot be loaded."""


class CalibrationEstimateError(CalibrationError):
    """Raised when execution time cannot be estimated from calibration data."""

