"""Reusable software cost knowledge base for STAR."""

from __future__ import annotations

from collections.abc import Iterable

from task_admission_framework.cost.cost_category import CostCategory
from task_admission_framework.cost.cost_entry import CostEntry


class CostDatabase:
    """Registry of operation cost metadata.

    The constructor accepts entries so future loaders can populate the same
    public API from JSON files, MCU-specific profiles, RTOS variants, or
    experimentally calibrated data.
    """

    def __init__(self, entries: Iterable[CostEntry] | None = None) -> None:
        initial_entries = entries if entries is not None else self._default_entries()
        self._entries: dict[str, CostEntry] = {
            entry.name: entry for entry in initial_entries
        }

    def get_entry(self, name: str) -> CostEntry | None:
        """Return metadata for one operation, if it is known."""

        return self._entries.get(name)

    def contains(self, name: str) -> bool:
        """Return whether the operation is represented in the database."""

        return name in self._entries

    def list_entries(self) -> list[CostEntry]:
        """Return all entries in deterministic API-name order."""

        return [self._entries[name] for name in sorted(self._entries)]

    def register_entry(self, entry: CostEntry) -> None:
        """Add or replace one entry.

        This supports future calibration or platform-specific overrides without
        changing how consumers read from the database.
        """

        self._entries[entry.name] = entry

    @staticmethod
    def _default_entries() -> tuple[CostEntry, ...]:
        return (
            CostEntry(
                name="GPIO_Write",
                category=CostCategory.PERIPHERAL,
                base_weight=2,
                description="Digital GPIO output write.",
                reference="NXP S32K1 Reference Manual",
                blocking=False,
            ),
            CostEntry(
                name="GPIO_Read",
                category=CostCategory.PERIPHERAL,
                base_weight=2,
                description="Digital GPIO input read.",
                reference="NXP S32K1 Reference Manual",
                blocking=False,
            ),
            CostEntry(
                name="ADC_Read",
                category=CostCategory.PERIPHERAL,
                base_weight=5,
                description="Read ADC conversion result.",
                reference="NXP S32K1 Reference Manual",
                blocking=False,
            ),
            CostEntry(
                name="ADC_Start",
                category=CostCategory.PERIPHERAL,
                base_weight=4,
                description="Start ADC conversion sequence.",
                reference="NXP S32K1 Reference Manual",
                blocking=False,
            ),
            CostEntry(
                name="CAN_Send",
                category=CostCategory.PERIPHERAL,
                base_weight=7,
                description="Transmit CAN frame.",
                reference="NXP S32K1 Reference Manual",
                blocking=False,
            ),
            CostEntry(
                name="CAN_Receive",
                category=CostCategory.PERIPHERAL,
                base_weight=8,
                description="Receive CAN frame.",
                reference="NXP S32K1 Reference Manual",
                blocking=True,
            ),
            CostEntry(
                name="UART_Send",
                category=CostCategory.PERIPHERAL,
                base_weight=5,
                description="Transmit bytes over UART.",
                reference="NXP S32K1 Reference Manual",
                blocking=False,
            ),
            CostEntry(
                name="UART_Read",
                category=CostCategory.PERIPHERAL,
                base_weight=6,
                description="Read bytes from UART.",
                reference="NXP S32K1 Reference Manual",
                blocking=True,
            ),
            CostEntry(
                name="SPI_Transfer",
                category=CostCategory.PERIPHERAL,
                base_weight=7,
                description="Full-duplex SPI transfer.",
                reference="NXP S32K1 Reference Manual",
                blocking=False,
            ),
            CostEntry(
                name="I2C_Write",
                category=CostCategory.PERIPHERAL,
                base_weight=7,
                description="I2C bus write transaction.",
                reference="NXP S32K1 Reference Manual",
                blocking=False,
            ),
            CostEntry(
                name="I2C_Read",
                category=CostCategory.PERIPHERAL,
                base_weight=8,
                description="I2C bus read transaction.",
                reference="NXP S32K1 Reference Manual",
                blocking=False,
            ),
            CostEntry(
                name="xQueueSend",
                category=CostCategory.RTOS,
                base_weight=5,
                description="Send item to a FreeRTOS queue.",
                reference="FreeRTOS API",
                blocking=False,
            ),
            CostEntry(
                name="xQueueReceive",
                category=CostCategory.RTOS,
                base_weight=6,
                description="Receive item from a FreeRTOS queue.",
                reference="FreeRTOS API",
                blocking=True,
            ),
            CostEntry(
                name="xSemaphoreTake",
                category=CostCategory.RTOS,
                base_weight=6,
                description="Acquire a FreeRTOS semaphore.",
                reference="FreeRTOS API",
                blocking=True,
            ),
            CostEntry(
                name="xSemaphoreGive",
                category=CostCategory.RTOS,
                base_weight=4,
                description="Release a FreeRTOS semaphore.",
                reference="FreeRTOS API",
                blocking=False,
            ),
            CostEntry(
                name="vTaskDelay",
                category=CostCategory.RTOS,
                base_weight=3,
                description="Delay the current FreeRTOS task.",
                reference="FreeRTOS API",
                blocking=True,
            ),
            CostEntry(
                name="malloc",
                category=CostCategory.MEMORY,
                base_weight=9,
                description="Allocate dynamic memory.",
                reference="C Standard Library",
                blocking=False,
            ),
            CostEntry(
                name="calloc",
                category=CostCategory.MEMORY,
                base_weight=10,
                description="Allocate zero-initialized dynamic memory.",
                reference="C Standard Library",
                blocking=False,
            ),
            CostEntry(
                name="realloc",
                category=CostCategory.MEMORY,
                base_weight=11,
                description="Resize dynamic memory allocation.",
                reference="C Standard Library",
                blocking=False,
            ),
            CostEntry(
                name="free",
                category=CostCategory.MEMORY,
                base_weight=5,
                description="Release dynamic memory allocation.",
                reference="C Standard Library",
                blocking=False,
            ),
            CostEntry(
                name="printf",
                category=CostCategory.OTHER,
                base_weight=8,
                description="Formatted output routine.",
                reference="C Standard Library",
                blocking=True,
            ),
        )
