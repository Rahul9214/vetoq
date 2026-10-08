import pytest
from fastapi.testclient import TestClient

from vetoq.config import Settings
from vetoq.main import create_app


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ["VETOQ_ENVIRONMENT", "VETOQ_TRUSTED_HOSTS", "VETOQ_DATABASE_URL"]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client() -> TestClient:
    settings = Settings(_env_file=None, environment="test", trusted_hosts=["testserver"])
    return TestClient(create_app(settings))
