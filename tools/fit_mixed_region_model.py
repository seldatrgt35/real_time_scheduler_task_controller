"""Create an unvalidated mixed-region candidate profile from board CSV data."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from task_admission_framework.calibration.mixed_region_fitting import (
    write_candidate_profile,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("measurements", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    write_candidate_profile(arguments.measurements, arguments.output)


if __name__ == "__main__":
    main()
