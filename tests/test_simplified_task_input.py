from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from task_admission_framework.descriptor.descriptor_loader import (
    YamlDescriptorLoader,
)
from task_admission_framework.descriptor.descriptor_validator import (
    DescriptorValidator,
)
from task_admission_framework.descriptor.exceptions import DescriptorValidationError


class SimplifiedTaskInputTests(unittest.TestCase):
    def test_scheduler_descriptor_needs_no_criticality_or_stack_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "task.yaml"
            path.write_text(
                "\n".join(
                    [
                        "task_name: BrakeControl",
                        "entry_function: BrakeControlTask",
                        "period_ms: 5",
                        "deadline_ms: 5",
                        "priority: 3",
                    ]
                ),
                encoding="utf-8",
            )
            descriptor = YamlDescriptorLoader().load(path)

        DescriptorValidator().validate(descriptor, {"BrakeControlTask"})
        self.assertEqual(descriptor.criticality.name, "HIGH")
        self.assertEqual(descriptor.stack_size, 512)

    def test_priority_is_restricted_to_three_scheduler_levels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "task.yaml"
            path.write_text(
                "\n".join(
                    [
                        "task_name: BrakeControl",
                        "entry_function: BrakeControlTask",
                        "period_ms: 5",
                        "deadline_ms: 5",
                        "priority: 4",
                    ]
                ),
                encoding="utf-8",
            )
            descriptor = YamlDescriptorLoader().load(path)

        with self.assertRaisesRegex(DescriptorValidationError, "1 \\(LOW\\)"):
            DescriptorValidator().validate(descriptor, {"BrakeControlTask"})


if __name__ == "__main__":
    unittest.main()
