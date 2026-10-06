import mongomock
import pytest


@pytest.fixture(autouse=True)
def _sin_clave_de_api(monkeypatch):
    """Las pruebas no dependen de la clave que haya en el `.env` local."""
    monkeypatch.delenv("BETITO_API_KEY", raising=False)


@pytest.fixture
def db():
    return mongomock.MongoClient()["test"]
