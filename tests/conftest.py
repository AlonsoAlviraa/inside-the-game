import os

# Agent Framework auto-loads .env; tests must stay offline and deterministic.
os.environ["ITG_LLM_PROVIDER"] = "mock"
os.environ.setdefault("ITG_MEMORY_PATH", "/tmp/itg_test_memory.json")
import pytest


@pytest.fixture(autouse=True)
def _reset_limits():
    """Rate-limit state is per process; start every test with a clean slate."""
    from insidethegame import guard, server
    guard.LIMITER.hits.clear()
    server.ROOMS.clear()
    server._SANDBOX.clear()
    yield
