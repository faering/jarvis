import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Async tests (``pytest.mark.anyio``) run on asyncio only."""
    return "asyncio"
