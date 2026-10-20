"""Unit tests verify retry decisions without waiting for production backoff."""
import pytest


@pytest.fixture(autouse=True)
def immediate_default_recovery_wait(monkeypatch):
    # Leave real clocks, lease heartbeat timing, and explicit test sleepers alone.
    # Tests of delays inject a recording sleeper via recovery_context or kwargs.
    monkeypatch.setattr("molstat.recovery._sleep", lambda seconds: None)
