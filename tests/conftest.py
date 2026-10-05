import mongomock
import pytest


@pytest.fixture
def db():
    return mongomock.MongoClient()["test"]
