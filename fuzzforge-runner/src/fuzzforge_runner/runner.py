"""FuzzForge Runner - Main runner interface.

This module provides the high-level interface for FuzzForge OSS,
coordinating module execution, workflow orchestration, and storage.

"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fuzzforge_runner.executor import ModuleExecutor
from fuzzforge_runner.orchestrator import (
    StepResult,
    WorkflowDefinition,
    WorkflowOrchestrator,
    WorkflowResult,
    WorkflowStep,
)
from fuzzforge_runner.settings import Settings
from fuzzforge_runner.storage import LocalStorage

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger


def get_logger() -> BoundLogger:
    """Get structlog logger instance.

    :returns: Configured structlog logger.

    """
    from structlog import get_logger  # noqa: PLC0415

    return cast("BoundLogger", get_logger())


@dataclass
class ModuleInfo:
    """Information about an available module."""

    #: Module identifier/name.
    identifier: str

    #: Module description.
    description: str | None = None

    #: Module version.
    version: str | None = None

    #: Whether module image exists locally.
    available: bool = True


class Runner:
    """Main FuzzForge Runner interface.

    Provides a unified interface for:
    - Module discovery and execution
    - Workflow orchestration
    - Project and asset management

    This is the primary entry point for OSS users and the MCP server.

    """

    #: Runner settings.
    _settings: Settings

    #: Module executor.
    _executor: ModuleExecutor

    #: Local storage backend.
    _storage: LocalStorage

    #: Workflow orchestrator.
    _orchestrator: WorkflowOrchestrator

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize an instance of the class.

        :param settings: Runner settings. If None, loads from environment.

        """
        self._settings = settings or Settings()
        self._executor = ModuleExecutor(self._settings)
        self._storage = LocalStorage(self._settings.storage.path)
        self._orchestrator = WorkflowOrchestrator(self._executor, self._storage)

    @property
    def settings(self) -> Settings:
        """Get runner settings.

        :returns: Current settings instance.

        """
        return self._settings

    @property
    def storage(self) -> LocalStorage:
        """Get storage backend.

        :returns: Storage instance.

        """
        return self._storage

    # -------------------------------------------------------------------------
    # Project Management
    # -------------------------------------------------------------------------

    def init_project(self, project_path: Path) -> Path:
        """Initialize a new project.

        Creates necessary storage directories for a project.

        :param project_path: Path to the project directory.
        :returns: Path to the project storage directory.

        """
        logger = get_logger()
        logger.info("initializing project", path=str(project_path))
        return self._storage.init_project(project_path)

    def set_project_assets(self, project_path: Path, assets_path: Path) -> Path:
        """Set initial assets for a project.

        :param project_path: Path to the project directory.
        :param assets_path: Path to assets (file or directory).
        :returns: Path to stored assets.

        """
        logger = get_logger()
        logger.info("setting project assets", project=str(project_path), assets=str(assets_path))
        return self._storage.store_assets(project_path, assets_path)

    # -------------------------------------------------------------------------
    # Module Discovery
    # -------------------------------------------------------------------------

    def list_modules(self) -> list[ModuleInfo]:
        """List available modules.

        Discovers modules from the configured modules directory.

        :returns: List of available modules.

        """
        logger = get_logger()
        modules: list[ModuleInfo] = []

        modules_path = self._settings.modules_path
        if not modules_path.exists():
            logger.warning("modules directory not found", path=str(modules_path))
            return modules

        # Look for module directories (each should have a Dockerfile or be a built image)
        for item in modules_path.iterdir():
            if item.is_dir():
                # Check for module markers
                has_dockerfile = (item / "Dockerfile").exists()
                has_pyproject = (item / "pyproject.toml").exists()

                if has_dockerfile or has_pyproject:
                    modules.append(
                        ModuleInfo(
                            identifier=item.name,
                            available=has_dockerfile,
                        )
                    )

        logger.info("discovered modules", count=len(modules))
        return modules

    def list_module_images(self, filter_prefix: str = "localhost/") -> list[ModuleInfo]:
        """List available module images from the container engine.

        Uses the container engine API to discover built module images.

        :param filter_prefix: Prefix to filter images (default: "localhost/").
        :returns: List of available module images.

        """
        logger = get_logger()
        modules: list[ModuleInfo] = []
        seen: set[str] = set()

        # Infrastructure images to skip
        skip_images = {"fuzzforge-modules-sdk", "fuzzforge-runner", "fuzzforge-api"}

        engine = self._executor._get_engine()
        images = engine.list_images(filter_prefix=filter_prefix)

        for image in images:
            # Only include :latest images
            if image.tag != "latest":
                continue

            # Extract module name from repository
            full_name = image.repository.split("/")[-1]

            # Skip infrastructure images
            if full_name in skip_images:
                continue

            # Extract clean module name (remove fuzzforge-module- prefix if present)
            if full_name.startswith("fuzzforge-module-"):
                module_name = full_name.replace("fuzzforge-module-", "")
            else:
                module_name = full_name

            # Skip UUID-like names (temporary/broken containers)
            if module_name.count("-") >= 4 and len(module_name) > 30:
                continue

            # Add unique modules
            if module_name not in seen:
                seen.add(module_name)
                modules.append(
                    ModuleInfo(
                        identifier=module_name,
                        description=None,
                        version=image.tag,
                        available=True,
                    )
                )

        logger.info("listed module images", count=len(modules))
        return modules

    def get_module_info(self, module_identifier: str) -> ModuleInfo | None:
        """Get information about a specific module.

        :param module_identifier: Module identifier to look up.
        :returns: Module info, or None if not found.

        """
        modules = self.list_modules()
        for module in modules:
            if module.identifier == module_identifier:
                return module
        return None

    # -------------------------------------------------------------------------
    # Module Execution
    # -------------------------------------------------------------------------

    async def execute_module(
        self,
        module_identifier: str,
        project_path: Path,
        configuration: dict[str, Any] | None = None,
        assets_path: Path | None = None,
    ) -> StepResult:
        """Execute a single module.

        :param module_identifier: Module to execute.
        :param project_path: Path to the project directory.
        :param configuration: Optional module configuration.
        :param assets_path: Optional path to input assets.
        :returns: Execution result.

        """
        logger = get_logger()
        logger.info(
            "executing module",
            module=module_identifier,
            project=str(project_path),
        )

        return await self._orchestrator.execute_single_module(
            module_identifier=module_identifier,
            project_path=project_path,
            assets_path=assets_path,
            configuration=configuration,
        )

    # -------------------------------------------------------------------------
    # Workflow Execution
    # -------------------------------------------------------------------------

    async def execute_workflow(
        self,
        workflow: WorkflowDefinition,
        project_path: Path,
        initial_assets_path: Path | None = None,
    ) -> WorkflowResult:
        """Execute a workflow.

        :param workflow: Workflow definition with steps.
        :param project_path: Path to the project directory.
        :param initial_assets_path: Optional path to initial assets.
        :returns: Workflow execution result.

        """
        logger = get_logger()
        logger.info(
            "executing workflow",
            workflow=workflow.name,
            project=str(project_path),
            steps=len(workflow.steps),
        )

        return await self._orchestrator.execute_workflow(
            workflow=workflow,
            project_path=project_path,
            initial_assets_path=initial_assets_path,
        )

    def create_workflow(
        self,
        name: str,
        steps: list[tuple[str, dict[str, Any] | None]],
        description: str | None = None,
    ) -> WorkflowDefinition:
        """Create a workflow definition.

        Convenience method for creating workflows programmatically.

        :param name: Workflow name.
        :param steps: List of (module_identifier, configuration) tuples.
        :param description: Optional workflow description.
        :returns: Workflow definition.

        """
        workflow_steps = [
            WorkflowStep(
                module_identifier=module_id,
                configuration=config,
                name=f"step-{i}",
            )
            for i, (module_id, config) in enumerate(steps)
        ]

        return WorkflowDefinition(
            name=name,
            steps=workflow_steps,
            description=description,
        )

    # -------------------------------------------------------------------------
    # Results Management
    # -------------------------------------------------------------------------

    def get_execution_results(
        self,
        project_path: Path,
        execution_id: str,
    ) -> Path | None:
        """Get results for an execution.

        :param project_path: Path to the project directory.
        :param execution_id: Execution ID.
        :returns: Path to results archive, or None if not found.

        """
        return self._storage.get_execution_results(project_path, execution_id)

    def list_executions(self, project_path: Path) -> list[str]:
        """List all executions for a project.

        :param project_path: Path to the project directory.
        :returns: List of execution IDs.

        """
        return self._storage.list_executions(project_path)

    def extract_results(self, results_path: Path, destination: Path) -> Path:
        """Extract results archive to a directory.

        :param results_path: Path to results archive.
        :param destination: Destination directory.
        :returns: Path to extracted directory.

        """
        return self._storage.extract_results(results_path, destination)
