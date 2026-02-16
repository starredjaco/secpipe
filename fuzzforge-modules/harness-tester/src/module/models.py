"""Models for harness-tester module."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from fuzzforge_modules_sdk.api.models import (
    FuzzForgeModuleInputBase,
    FuzzForgeModuleOutputBase,
)

from module.settings import Settings


class Input(FuzzForgeModuleInputBase[Settings]):
    """Input for the harness-tester module."""


class Output(FuzzForgeModuleOutputBase):
    """Output for the harness-tester module."""

    #: The test report data.
    report: dict[str, Any] | None = None

    #: Path to the report JSON file.
    report_file: Path | None = None
