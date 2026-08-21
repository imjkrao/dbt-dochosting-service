import pytest
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from app.config import Settings
from app.storage import AzureBlobStorage


class _FakeBlobClient:
    def __init__(self, store: dict, name: str):
        self._store = store
        self._name = name

    def get_blob_properties(self):
        if self._name not in self._store:
            raise ResourceNotFoundError("not found")
        return {}


class _FakeDownloader:
    def __init__(self, data: bytes):
        self._data = data

    def readall(self) -> bytes:
        return self._data


class _FakeContainerClient:
    def __init__(self):
        self._store: dict[str, bytes] = {}

    def upload_blob(self, name, data, overwrite=True, content_settings=None):
        self._store[name] = data

    def download_blob(self, name):
        if name not in self._store:
            raise ResourceNotFoundError("not found")
        return _FakeDownloader(self._store[name])

    def get_blob_client(self, name):
        return _FakeBlobClient(self._store, name)


class _FakeServiceClient:
    def __init__(self):
        self.container = _FakeContainerClient()

    def get_container_client(self, name):
        return self.container


@pytest.fixture
def fake_container(monkeypatch):
    fake_service = _FakeServiceClient()
    monkeypatch.setattr(
        BlobServiceClient, "from_connection_string", staticmethod(lambda *_a, **_kw: fake_service)
    )
    return fake_service.container


def test_put_get_exists_roundtrip(fake_container):
    settings = Settings(
        storage_backend="azure",
        azure_container="docs",
        azure_connection_string="UseDevelopmentStorage=true",
        upload_api_key="k",
    )
    store = AzureBlobStorage(settings)

    assert store.object_exists("index.html") is False

    store.put_object("index.html", b"<html>docs</html>", "text/html")

    assert store.object_exists("index.html") is True
    assert store.get_object("index.html") == b"<html>docs</html>"
