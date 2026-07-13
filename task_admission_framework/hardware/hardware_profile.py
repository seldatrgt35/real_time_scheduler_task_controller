"""Generic embedded hardware profile model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    """Describes target hardware capabilities without decision logic."""

    name: str
    vendor: str
    family: str
    architecture: str
    core: str
    cpu_frequency_mhz: int
    flash_kb: int
    ram_kb: int
    fpu: bool
    dma: bool
    mpu: bool
    cache: bool
    adc_units: int
    can_units: int
    uart_units: int
    spi_units: int
    i2c_units: int
    operating_mode: str | None = None
    compiler: str | None = None
    compiler_version: str | None = None
    optimization_level: str | None = None
    flash_wait_states: int | None = None
    execution_location: str | None = None
    freertos_tick_hz: int | None = None
    calibration_profile_id: str | None = None
