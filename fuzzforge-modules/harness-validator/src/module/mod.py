"""Harness Validator module for FuzzForge.

This module validates that fuzz harnesses compile correctly.
It takes a Rust project with a fuzz directory containing harnesses
and runs cargo build to verify they compile.
"""

from __future__ import annotations

import json
import subprocess
import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from fuzzforge_modules_sdk.api.constants import PATH_TO_INPUTS, PATH_TO_OUTPUTS
from fuzzforge_modules_sdk.api.models import FuzzForgeModuleResults
from fuzzforge_modules_sdk.api.modules.base import FuzzForgeModule

from module.models import Input, Output, ValidationResult, HarnessStatus
from module.settings import Settings

if TYPE_CHECKING:
    from fuzzforge_modules_sdk.api.models import FuzzForgeModuleResource

logger = structlog.get_logger()


class Module(FuzzForgeModule):
    """Harness Validator module - validates that fuzz harnesses compile."""

    _settings: Settings | None
    _results: list[ValidationResult]

    def __init__(self) -> None:
        """Initialize an instance of the class."""
        name: str = "harness-validator"
        version: str = "0.1.0"
        FuzzForgeModule.__init__(self, name=name, version=version)
        self._settings = None
        self._results = []

    @classmethod
    def _get_input_type(cls) -> type[Input]:
        """Return the input type."""
        return Input

    @classmethod
    def _get_output_type(cls) -> type[Output]:
        """Return the output type."""
        return Output

    def _prepare(self, settings: Settings) -> None:  # type: ignore[override]
        """Prepare the module.

        :param settings: Module settings.

        """
        self._settings = settings
        logger.info("harness-validator preparing", settings=settings.model_dump() if settings else {})

    def _run(self, resources: list[FuzzForgeModuleResource]) -> FuzzForgeModuleResults:
        """Run the harness validator.

        :param resources: Input resources (fuzz project directory).
        :returns: Module execution result.

        """
        logger.info("harness-validator starting", resource_count=len(resources))

        # Find the fuzz project directory
        fuzz_project_src = self._find_fuzz_project(resources)
        if fuzz_project_src is None:
            logger.error("No fuzz project found in resources")
            return FuzzForgeModuleResults.FAILURE

        logger.info("Found fuzz project", path=str(fuzz_project_src))

        # Copy the project to a writable location since /data/input is read-only
        # and cargo needs to write Cargo.lock and build artifacts
        import shutil
        work_dir = Path("/tmp/fuzz-build")
        if work_dir.exists():
            shutil.rmtree(work_dir)
        
        # Copy entire project root (parent of fuzz directory)
        project_root = fuzz_project_src.parent
        work_project = work_dir / project_root.name
        shutil.copytree(project_root, work_project, dirs_exist_ok=True)
        
        # Adjust fuzz_project to point to the copied location
        fuzz_project = work_dir / project_root.name / fuzz_project_src.name
        logger.info("Copied project to writable location", work_dir=str(fuzz_project))

        # Find all harness targets
        targets = self._find_harness_targets(fuzz_project)
        if not targets:
            logger.error("No harness targets found")
            return FuzzForgeModuleResults.FAILURE

        logger.info("Found harness targets", count=len(targets))

        # Validate each harness
        all_valid = True
        for target in targets:
            result = self._validate_harness(fuzz_project, target)
            self._results.append(result)
            if result.status != HarnessStatus.VALID:
                all_valid = False
                logger.warning("Harness validation failed", 
                             target=target, 
                             status=result.status.value,
                             errors=result.errors)
            else:
                logger.info("Harness valid", target=target)

        # Set output data for results.json
        valid_targets = [r.target for r in self._results if r.status == HarnessStatus.VALID]
        invalid_targets = [r.target for r in self._results if r.status != HarnessStatus.VALID]
        
        self.set_output(
            fuzz_project=str(fuzz_project),
            total_targets=len(self._results),
            valid_count=len(valid_targets),
            invalid_count=len(invalid_targets),
            valid_targets=valid_targets,
            invalid_targets=invalid_targets,
            results=[r.model_dump() for r in self._results],
        )

        valid_count = sum(1 for r in self._results if r.status == HarnessStatus.VALID)
        logger.info("harness-validator completed",
                   total=len(self._results),
                   valid=valid_count,
                   invalid=len(self._results) - valid_count)

        return FuzzForgeModuleResults.SUCCESS

    def _cleanup(self, settings: Settings) -> None:  # type: ignore[override]
        """Clean up after execution.

        :param settings: Module settings.

        """
        pass

    def _find_fuzz_project(self, resources: list[FuzzForgeModuleResource]) -> Path | None:
        """Find the fuzz project directory in the resources.

        :param resources: List of input resources.
        :returns: Path to fuzz project or None.

        """
        for resource in resources:
            path = Path(resource.path)
            
            # Check if it's a fuzz directory with Cargo.toml
            if path.is_dir():
                cargo_toml = path / "Cargo.toml"
                if cargo_toml.exists():
                    # Check if it has fuzz_targets directory
                    fuzz_targets = path / "fuzz_targets"
                    if fuzz_targets.is_dir():
                        return path
                
                # Check for fuzz subdirectory
                fuzz_dir = path / "fuzz"
                if fuzz_dir.is_dir():
                    cargo_toml = fuzz_dir / "Cargo.toml"
                    if cargo_toml.exists():
                        return fuzz_dir

        return None

    def _find_harness_targets(self, fuzz_project: Path) -> list[str]:
        """Find all harness target names in the fuzz project.

        :param fuzz_project: Path to the fuzz project.
        :returns: List of target names.

        """
        targets = []
        fuzz_targets_dir = fuzz_project / "fuzz_targets"
        
        if fuzz_targets_dir.is_dir():
            for rs_file in fuzz_targets_dir.glob("*.rs"):
                # Target name is the file name without extension
                target_name = rs_file.stem
                targets.append(target_name)

        return targets

    def _validate_harness(self, fuzz_project: Path, target: str) -> ValidationResult:
        """Validate a single harness by compiling it.

        :param fuzz_project: Path to the fuzz project.
        :param target: Name of the harness target.
        :returns: Validation result.

        """
        harness_file = fuzz_project / "fuzz_targets" / f"{target}.rs"
        
        if not harness_file.exists():
            return ValidationResult(
                target=target,
                file_path=str(harness_file),
                status=HarnessStatus.NOT_FOUND,
                errors=["Harness file not found"],
            )

        # Try to compile just this target
        try:
            env = os.environ.copy()
            env["CARGO_INCREMENTAL"] = "0"
            
            result = subprocess.run(
                [
                    "cargo", "build",
                    "--bin", target,
                    "--message-format=json",
                ],
                cwd=fuzz_project,
                capture_output=True,
                text=True,
                timeout=self._settings.compile_timeout if self._settings else 120,
                env=env,
            )

            # Parse cargo output for errors
            errors = []
            warnings = []
            
            for line in result.stdout.splitlines():
                try:
                    msg = json.loads(line)
                    if msg.get("reason") == "compiler-message":
                        message = msg.get("message", {})
                        level = message.get("level", "")
                        rendered = message.get("rendered", "")
                        
                        if level == "error":
                            errors.append(rendered.strip())
                        elif level == "warning":
                            warnings.append(rendered.strip())
                except json.JSONDecodeError:
                    pass

            # Also check stderr for any cargo errors
            if result.returncode != 0 and not errors:
                errors.append(result.stderr.strip() if result.stderr else "Build failed with unknown error")

            if result.returncode == 0:
                return ValidationResult(
                    target=target,
                    file_path=str(harness_file),
                    status=HarnessStatus.VALID,
                    errors=[],
                    warnings=warnings,
                )
            else:
                return ValidationResult(
                    target=target,
                    file_path=str(harness_file),
                    status=HarnessStatus.COMPILE_ERROR,
                    errors=errors,
                    warnings=warnings,
                )

        except subprocess.TimeoutExpired:
            return ValidationResult(
                target=target,
                file_path=str(harness_file),
                status=HarnessStatus.TIMEOUT,
                errors=["Compilation timed out"],
            )
        except Exception as e:
            return ValidationResult(
                target=target,
                file_path=str(harness_file),
                status=HarnessStatus.ERROR,
                errors=[str(e)],
            )

    def _write_output(self, fuzz_project: Path) -> None:
        """Write the validation results to output.

        :param fuzz_project: Path to the fuzz project.

        """
        output_path = PATH_TO_OUTPUTS / "validation.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        valid_targets = [r.target for r in self._results if r.status == HarnessStatus.VALID]
        invalid_targets = [r.target for r in self._results if r.status != HarnessStatus.VALID]

        output_data = {
            "fuzz_project": str(fuzz_project),
            "total_targets": len(self._results),
            "valid_count": len(valid_targets),
            "invalid_count": len(invalid_targets),
            "valid_targets": valid_targets,
            "invalid_targets": invalid_targets,
            "results": [r.model_dump() for r in self._results],
        }

        output_path.write_text(json.dumps(output_data, indent=2))
        logger.info("wrote validation results", path=str(output_path))
