from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

    from podman import PodmanClient

    from fuzzforge_common.sandboxes.engines.podman.engine import Podman


def test_can_register_oci(
    path_to_oci: Path,
    podman_engine: Podman,
    podman_client: PodmanClient,
) -> None:
    """TODO."""
    repository: str = str(uuid4())
    podman_engine.register_archive(archive=path_to_oci, repository=repository)
    assert podman_client.images.exists(key=repository)
    podman_client.images.get(name=repository).remove()
