"""FuzzForge Runner - Local filesystem storage.

This module provides local filesystem storage as an alternative to S3,
enabling zero-configuration operation for OSS deployments.

"""

from __future__ import annotations

import shutil
from pathlib import Path, PurePath
from tarfile import open as Archive  # noqa: N812
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING, cast

from fuzzforge_runner.constants import RESULTS_ARCHIVE_FILENAME
from fuzzforge_runner.exceptions import StorageError

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger


def get_logger() -> BoundLogger:
    """Get structlog logger instance.

    :returns: Configured structlog logger.

    """
    from structlog import get_logger  # noqa: PLC0415

    return cast("BoundLogger", get_logger())


class LocalStorage:
    """Local filesystem storage backend.

    Provides S3-like operations using local filesystem, enabling
    FuzzForge operation without external storage infrastructure.

    Directory structure:
        {base_path}/
            projects/
                {project_id}/
                    assets/         # Initial project assets
                    runs/
                        {execution_id}/
                            results.tar.gz
                        {workflow_id}/
                            modules/
                                step-0-{exec_id}/
                                    results.tar.gz

    """

    #: Base path for all storage operations.
    _base_path: Path

    def __init__(self, base_path: Path) -> None:
        """Initialize an instance of the class.

        :param base_path: Root directory for storage.

        """
        self._base_path = base_path
        self._ensure_base_path()

    def _ensure_base_path(self) -> None:
        """Ensure the base storage directory exists."""
        self._base_path.mkdir(parents=True, exist_ok=True)

    def _get_project_path(self, project_path: Path) -> Path:
        """Get the storage path for a project.

        :param project_path: Original project path (used as identifier).
        :returns: Storage path for the project.

        """
        # Use project path name as identifier
        project_id = project_path.name
        return self._base_path / "projects" / project_id

    def init_project(self, project_path: Path) -> Path:
        """Initialize storage for a new project.

        :param project_path: Path to the project directory.
        :returns: Path to the project storage directory.

        """
        logger = get_logger()
        storage_path = self._get_project_path(project_path)

        # Create directory structure
        (storage_path / "assets").mkdir(parents=True, exist_ok=True)
        (storage_path / "runs").mkdir(parents=True, exist_ok=True)

        logger.info("initialized project storage", project=project_path.name, storage=str(storage_path))

        return storage_path

    def get_project_assets_path(self, project_path: Path) -> Path | None:
        """Get the path to project assets archive.

        :param project_path: Path to the project directory.
        :returns: Path to assets archive, or None if not found.

        """
        storage_path = self._get_project_path(project_path)
        assets_dir = storage_path / "assets"

        # Look for assets archive
        archive_path = assets_dir / "assets.tar.gz"
        if archive_path.exists():
            return archive_path

        # Check if there are any files in assets directory
        if assets_dir.exists() and any(assets_dir.iterdir()):
            # Create archive from directory contents
            return self._create_archive_from_directory(assets_dir)

        return None

    def _create_archive_from_directory(self, directory: Path) -> Path:
        """Create a tar.gz archive from a directory's contents.

        :param directory: Directory to archive.
        :returns: Path to the created archive.

        """
        archive_path = directory.parent / f"{directory.name}.tar.gz"

        with Archive(archive_path, "w:gz") as tar:
            for item in directory.iterdir():
                tar.add(item, arcname=item.name)

        return archive_path

    def create_empty_assets_archive(self, project_path: Path) -> Path:
        """Create an empty assets archive for a project.

        :param project_path: Path to the project directory.
        :returns: Path to the empty archive.

        """
        storage_path = self._get_project_path(project_path)
        assets_dir = storage_path / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        archive_path = assets_dir / "assets.tar.gz"

        # Create empty archive
        with Archive(archive_path, "w:gz") as tar:
            pass  # Empty archive

        return archive_path

    def store_assets(self, project_path: Path, assets_path: Path) -> Path:
        """Store project assets from a local path.

        :param project_path: Path to the project directory.
        :param assets_path: Source path (file or directory) to store.
        :returns: Path to the stored assets.
        :raises StorageError: If storage operation fails.

        """
        logger = get_logger()
        storage_path = self._get_project_path(project_path)
        assets_dir = storage_path / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        try:
            if assets_path.is_file():
                # Copy archive directly
                dest_path = assets_dir / "assets.tar.gz"
                shutil.copy2(assets_path, dest_path)
            else:
                # Create archive from directory
                dest_path = assets_dir / "assets.tar.gz"
                with Archive(dest_path, "w:gz") as tar:
                    for item in assets_path.iterdir():
                        tar.add(item, arcname=item.name)

            logger.info("stored project assets", project=project_path.name, path=str(dest_path))
            return dest_path

        except Exception as exc:
            message = f"Failed to store assets: {exc}"
            raise StorageError(message) from exc

    def store_execution_results(
        self,
        project_path: Path,
        workflow_id: str | None,
        step_index: int,
        execution_id: str,
        results_path: Path,
    ) -> Path:
        """Store execution results.

        :param project_path: Path to the project directory.
        :param workflow_id: Workflow execution ID (None for standalone).
        :param step_index: Step index in workflow.
        :param execution_id: Module execution ID.
        :param results_path: Path to results archive to store.
        :returns: Path to the stored results.
        :raises StorageError: If storage operation fails.

        """
        logger = get_logger()
        storage_path = self._get_project_path(project_path)

        try:
            if workflow_id:
                # Part of workflow
                dest_dir = storage_path / "runs" / workflow_id / "modules" / f"step-{step_index}-{execution_id}"
            else:
                # Standalone execution
                dest_dir = storage_path / "runs" / execution_id

            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / RESULTS_ARCHIVE_FILENAME

            shutil.copy2(results_path, dest_path)

            logger.info(
                "stored execution results",
                execution_id=execution_id,
                path=str(dest_path),
            )

            return dest_path

        except Exception as exc:
            message = f"Failed to store results: {exc}"
            raise StorageError(message) from exc

    def get_execution_results(
        self,
        project_path: Path,
        execution_id: str,
        workflow_id: str | None = None,
        step_index: int | None = None,
    ) -> Path | None:
        """Retrieve execution results.

        :param project_path: Path to the project directory.
        :param execution_id: Module execution ID.
        :param workflow_id: Workflow execution ID (None for standalone).
        :param step_index: Step index in workflow.
        :returns: Path to results archive, or None if not found.

        """
        storage_path = self._get_project_path(project_path)

        if workflow_id and step_index is not None:
            # Direct workflow path lookup
            results_path = (
                storage_path / "runs" / workflow_id / "modules" / f"step-{step_index}-{execution_id}" / RESULTS_ARCHIVE_FILENAME
            )
            if results_path.exists():
                return results_path
        
        # Try standalone path
        results_path = storage_path / "runs" / execution_id / RESULTS_ARCHIVE_FILENAME
        if results_path.exists():
            return results_path
        
        # Search for execution_id in all workflow runs
        runs_dir = storage_path / "runs"
        if runs_dir.exists():
            for workflow_dir in runs_dir.iterdir():
                if not workflow_dir.is_dir():
                    continue
                
                # Check if this is a workflow directory (has 'modules' subdirectory)
                modules_dir = workflow_dir / "modules"
                if modules_dir.exists() and modules_dir.is_dir():
                    # Search for step directories containing this execution_id
                    for step_dir in modules_dir.iterdir():
                        if step_dir.is_dir() and execution_id in step_dir.name:
                            results_path = step_dir / RESULTS_ARCHIVE_FILENAME
                            if results_path.exists():
                                return results_path

        return None

    def list_executions(self, project_path: Path) -> list[str]:
        """List all execution IDs for a project.

        :param project_path: Path to the project directory.
        :returns: List of execution IDs.

        """
        storage_path = self._get_project_path(project_path)
        runs_dir = storage_path / "runs"

        if not runs_dir.exists():
            return []

        return [d.name for d in runs_dir.iterdir() if d.is_dir()]

    def delete_execution(self, project_path: Path, execution_id: str) -> bool:
        """Delete an execution and its results.

        :param project_path: Path to the project directory.
        :param execution_id: Execution ID to delete.
        :returns: True if deleted, False if not found.

        """
        logger = get_logger()
        storage_path = self._get_project_path(project_path)
        exec_path = storage_path / "runs" / execution_id

        if exec_path.exists():
            shutil.rmtree(exec_path)
            logger.info("deleted execution", execution_id=execution_id)
            return True

        return False

    def delete_project(self, project_path: Path) -> bool:
        """Delete all storage for a project.

        :param project_path: Path to the project directory.
        :returns: True if deleted, False if not found.

        """
        logger = get_logger()
        storage_path = self._get_project_path(project_path)

        if storage_path.exists():
            shutil.rmtree(storage_path)
            logger.info("deleted project storage", project=project_path.name)
            return True

        return False

    def extract_results(self, results_path: Path, destination: Path) -> Path:
        """Extract a results archive to a destination directory.

        :param results_path: Path to the results archive.
        :param destination: Directory to extract to.
        :returns: Path to extracted directory.
        :raises StorageError: If extraction fails.

        """
        logger = get_logger()

        try:
            destination.mkdir(parents=True, exist_ok=True)

            with Archive(results_path, "r:gz") as tar:
                tar.extractall(path=destination)

            logger.info("extracted results", source=str(results_path), destination=str(destination))
            return destination

        except Exception as exc:
            message = f"Failed to extract results: {exc}"
            raise StorageError(message) from exc
