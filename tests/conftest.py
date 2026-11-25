import pytest

from receipts.config import Settings
from receipts.samples.simulated import SimulatedAgents


@pytest.fixture
def cfg() -> Settings:
    return Settings(parity_timeout_s=2.0)


@pytest.fixture
def agents() -> SimulatedAgents:
    return SimulatedAgents()
