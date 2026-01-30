"""Models for the harness-validator module."""

from enum import Enum

from pydantic import BaseModel, Field
from fuzzforge_modules_sdk.api.models import FuzzForgeModuleInputBase, FuzzForgeModuleOutputBase

from module.settings import Settings


class HarnessStatus(str, Enum):
    """Status of harness validation."""
    
    VALID = "valid"
    COMPILE_ERROR = "compile_error"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    ERROR = "error"


class ValidationResult(BaseModel):
    """Result of validating a single harness."""
    
    #: Name of the harness target
    target: str
    
    #: Path to the harness file
    file_path: str
    
    #: Validation status
    status: HarnessStatus
    
    #: Compilation errors (if any)
    errors: list[str] = Field(default_factory=list)
    
    #: Compilation warnings (if any)
    warnings: list[str] = Field(default_factory=list)


class Input(FuzzForgeModuleInputBase[Settings]):
    """Input for the harness-validator module.
    
    Expects a fuzz project directory with:
    - Cargo.toml
    - fuzz_targets/ directory with .rs harness files
    """


class Output(FuzzForgeModuleOutputBase):
    """Output from the harness-validator module."""
    
    #: Path to the fuzz project
    fuzz_project: str = ""
    
    #: Total number of harness targets
    total_targets: int = 0
    
    #: Number of valid (compilable) harnesses
    valid_count: int = 0
    
    #: Number of invalid harnesses
    invalid_count: int = 0
    
    #: List of valid target names (ready for fuzzing)
    valid_targets: list[str] = Field(default_factory=list)
    
    #: List of invalid target names (need fixes)
    invalid_targets: list[str] = Field(default_factory=list)
    
    #: Detailed validation results per target
    results: list[ValidationResult] = Field(default_factory=list)
