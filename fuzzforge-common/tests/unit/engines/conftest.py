import pytest

from fuzzforge_common.sandboxes.engines.podman.engine import Podman


@pytest.fixture
def podman_engine(podman_socket: str) -> Podman:
    """TODO."""
    return Podman(socket=podman_socket)
