"""Known API metadata for task static analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ApiDatabase:
    """Central registry of RTOS, peripheral, libc, and memory APIs."""

    tracked_apis: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "GPIO_Write",
                "GPIO_Read",
                "ADC_Read",
                "ADC_Start",
                "CAN_Send",
                "CAN_Receive",
                "UART_Send",
                "UART_Read",
                "SPI_Transfer",
                "I2C_Write",
                "I2C_Read",
                "xQueueSend",
                "xQueueReceive",
                "xSemaphoreTake",
                "xSemaphoreGive",
                "vTaskDelay",
                "malloc",
                "calloc",
                "realloc",
                "free",
                "printf",
            }
        )
    )
    dynamic_memory_apis: frozenset[str] = field(
        default_factory=lambda: frozenset({"malloc", "calloc", "realloc", "free"})
    )
    blocking_apis: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"xQueueReceive", "xSemaphoreTake", "vTaskDelay", "CAN_Receive", "UART_Read"}
        )
    )

    def is_tracked(self, api_name: str) -> bool:
        return api_name in self.tracked_apis

    def is_dynamic_memory(self, api_name: str) -> bool:
        return api_name in self.dynamic_memory_apis

    def is_blocking(self, api_name: str) -> bool:
        return api_name in self.blocking_apis

    def empty_usage(self) -> dict[str, int]:
        """Return a deterministic zero-filled usage map."""

        return {api_name: 0 for api_name in sorted(self.tracked_apis)}
