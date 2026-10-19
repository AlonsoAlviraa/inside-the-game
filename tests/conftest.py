import os

# Agent Framework auto-loads .env; tests must stay offline and deterministic.
os.environ["ITG_LLM_PROVIDER"] = "mock"
os.environ.setdefault("ITG_MEMORY_PATH", "/tmp/itg_test_memory.json")
