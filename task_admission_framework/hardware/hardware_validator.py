"""Hardware profile validation."""

from __future__ import annotations

from task_admission_framework.hardware.exceptions import HardwareValidationError
from task_admission_framework.hardware.hardware_profile import HardwareProfile


class HardwareValidator:
    """Validates hardware profile consistency without scoring or decisions."""

    def validate(self, profile: HardwareProfile) -> None:
        self._validate_positive("cpu_frequency_mhz", profile.cpu_frequency_mhz)
        self._validate_positive("flash_kb", profile.flash_kb)
        self._validate_positive("ram_kb", profile.ram_kb)
        self._validate_non_negative("adc_units", profile.adc_units)
        self._validate_non_negative("can_units", profile.can_units)
        self._validate_non_negative("uart_units", profile.uart_units)
        self._validate_non_negative("spi_units", profile.spi_units)
        self._validate_non_negative("i2c_units", profile.i2c_units)
        self._validate_optional_non_negative(
            "flash_wait_states",
            profile.flash_wait_states,
        )
        self._validate_optional_positive("freertos_tick_hz", profile.freertos_tick_hz)

    @staticmethod
    def _validate_positive(field_name: str, value: int) -> None:
        if value <= 0:
            raise HardwareValidationError(f"{field_name} must be greater than 0.")

    @staticmethod
    def _validate_non_negative(field_name: str, value: int) -> None:
        if value < 0:
            raise HardwareValidationError(
                f"{field_name} must be greater than or equal to 0."
            )

    @staticmethod
    def _validate_optional_positive(field_name: str, value: int | None) -> None:
        if value is not None and value <= 0:
            raise HardwareValidationError(f"{field_name} must be greater than 0.")

    @staticmethod
    def _validate_optional_non_negative(field_name: str, value: int | None) -> None:
        if value is not None and value < 0:
            raise HardwareValidationError(
                f"{field_name} must be greater than or equal to 0."
            )
