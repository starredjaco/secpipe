"""Settings for the harness-validator module."""

from fuzzforge_modules_sdk.api.models import FuzzForgeModulesSettingsBase


class Settings(FuzzForgeModulesSettingsBase):
    """Settings for the harness-validator module."""

    #: Timeout for compiling each harness (seconds)
    compile_timeout: int = 120
    
    #: Whether to stop on first error
    fail_fast: bool = False
