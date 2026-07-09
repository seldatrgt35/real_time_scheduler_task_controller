"""Task descriptor validation."""

from __future__ import annotations

from collections.abc import Collection

from task_admission_framework.descriptor.criticality import Criticality
from task_admission_framework.descriptor.exceptions import DescriptorValidationError
from task_admission_framework.descriptor.task_descriptor import TaskDescriptor


class DescriptorValidator:
    """Validates task descriptor semantics against known function names."""

    def validate(
        self,
        descriptor: TaskDescriptor,
        available_functions: Collection[str],
    ) -> None:
        self._validate_not_empty("task_name", descriptor.task_name)
        self._validate_not_empty("entry_function", descriptor.entry_function)
        self._validate_positive("period_ms", descriptor.period_ms)
        self._validate_positive("deadline_ms", descriptor.deadline_ms)

        if descriptor.deadline_ms > descriptor.period_ms:
            raise DescriptorValidationError(
                "deadline_ms must be less than or equal to period_ms."
            )

        if descriptor.priority < 0:
            raise DescriptorValidationError("priority must be greater than or equal to 0.")

        self._validate_positive("stack_size", descriptor.stack_size)

        if not isinstance(descriptor.criticality, Criticality):
            raise DescriptorValidationError("criticality must be a valid Criticality value.")

        if descriptor.entry_function not in available_functions:
            raise DescriptorValidationError(
                "entry_function does not match any discovered function definition: "
                f"{descriptor.entry_function}"
            )

    @staticmethod
    def _validate_not_empty(field_name: str, value: str) -> None:
        if not value.strip():
            raise DescriptorValidationError(f"{field_name} must not be empty.")

    @staticmethod
    def _validate_positive(field_name: str, value: int) -> None:
        if value <= 0:
            raise DescriptorValidationError(f"{field_name} must be greater than 0.")
