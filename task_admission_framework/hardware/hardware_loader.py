"""Hardware profile loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from task_admission_framework.hardware.exceptions import HardwareLoadError
from task_admission_framework.hardware.hardware_profile import HardwareProfile


class HardwareLoader:
    """Loads hardware profiles from JSON files.

    Sprint 5.1 supports JSON only. The loader remains isolated so future
    profile sources can be added without coupling hardware data to analysis.
    """

    _JSON_SUFFIX = ".json"

    def load(self, profile_path: str | Path) -> HardwareProfile:
        path = Path(profile_path)
        if path.suffix.lower() != self._JSON_SUFFIX:
            raise HardwareLoadError(f"Unsupported hardware profile format: {path.suffix}")

        data = self._load_json(path)
        return self._build_profile(data)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise HardwareLoadError(f"Hardware profile not found: {path}")

        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise HardwareLoadError(f"Could not read hardware profile: {path}") from exc
        except json.JSONDecodeError as exc:
            raise HardwareLoadError(f"Invalid JSON hardware profile: {path}") from exc

        if not isinstance(loaded, dict):
            raise HardwareLoadError("Hardware profile JSON must contain an object.")

        return loaded

    @staticmethod
    def _build_profile(data: dict[str, Any]) -> HardwareProfile:
        try:
            return HardwareProfile(
                name=str(data["name"]),
                vendor=str(data["vendor"]),
                family=str(data["family"]),
                architecture=str(data["architecture"]),
                core=str(data["core"]),
                cpu_frequency_mhz=int(data["cpu_frequency_mhz"]),
                flash_kb=int(data["flash_kb"]),
                ram_kb=int(data["ram_kb"]),
                fpu=HardwareLoader._parse_bool(data["fpu"]),
                dma=HardwareLoader._parse_bool(data["dma"]),
                mpu=HardwareLoader._parse_bool(data["mpu"]),
                cache=HardwareLoader._parse_bool(data["cache"]),
                adc_units=int(data["adc_units"]),
                can_units=int(data["can_units"]),
                uart_units=int(data["uart_units"]),
                spi_units=int(data["spi_units"]),
                i2c_units=int(data["i2c_units"]),
                operating_mode=HardwareLoader._optional_str(data, "operating_mode"),
                compiler=HardwareLoader._optional_str(data, "compiler"),
                compiler_version=HardwareLoader._optional_str(
                    data,
                    "compiler_version",
                ),
                optimization_level=HardwareLoader._optional_str(
                    data,
                    "optimization_level",
                ),
                flash_wait_states=HardwareLoader._optional_int(
                    data,
                    "flash_wait_states",
                ),
                execution_location=HardwareLoader._optional_str(
                    data,
                    "execution_location",
                ),
                freertos_tick_hz=HardwareLoader._optional_int(
                    data,
                    "freertos_tick_hz",
                ),
                calibration_profile_id=HardwareLoader._optional_str(
                    data,
                    "calibration_profile_id",
                ),
            )
        except KeyError as exc:
            raise HardwareLoadError(f"Missing hardware profile field: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise HardwareLoadError("Hardware profile contains invalid field types.") from exc

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1"}:
                return True
            if normalized in {"false", "no", "0"}:
                return False

        raise ValueError(f"Invalid boolean value: {value}")

    @staticmethod
    def _optional_str(data: dict[str, Any], field_name: str) -> str | None:
        value = data.get(field_name)
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _optional_int(data: dict[str, Any], field_name: str) -> int | None:
        value = data.get(field_name)
        if value is None:
            return None
        return int(value)
