"""Settings for harness-tester module."""

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Settings for the harness-tester module."""

    #: Duration for each fuzzing trial in seconds.
    trial_duration_sec: int = Field(default=30, ge=1, le=300)

    #: Timeout for harness execution in seconds.
    execution_timeout_sec: int = Field(default=10, ge=1, le=60)

    #: Whether to generate coverage reports.
    enable_coverage: bool = Field(default=True)

    #: Minimum score threshold for harness to be considered "good".
    min_quality_score: int = Field(default=50, ge=0, le=100)
