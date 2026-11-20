import pytest
from pydantic import ValidationError

from job_queue.config import Settings


def test_settings_are_read_from_environment(monkeypatch):
    monkeypatch.setenv("QUEUE_CAPACITY", "123")
    monkeypatch.setenv("NUM_WORKERS", "7")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("DRAIN_TIMEOUT_SECONDS", "12.5")

    settings = Settings()

    assert settings.queue_capacity == 123
    assert settings.num_workers == 7
    assert settings.port == 9000
    assert settings.drain_timeout_seconds == 12.5


@pytest.mark.parametrize("name", ["RETENTION_TTL_SECONDS", "RETENTION_TTL"])
def test_retention_ttl_accepts_both_env_names(monkeypatch, name):
    monkeypatch.delenv("RETENTION_TTL_SECONDS", raising=False)
    monkeypatch.delenv("RETENTION_TTL", raising=False)
    monkeypatch.setenv(name, "120")

    assert Settings().retention_ttl_seconds == 120


def test_invalid_settings_fail_at_startup(monkeypatch):
    monkeypatch.setenv("NUM_WORKERS", "0")

    with pytest.raises(ValidationError):
        Settings()
