"""In-memory stand-in for Azure Blob Storage.

Azure has no equivalent of moto in the test stack, so the container client is
faked at the seam where ``AzureBlobStorage`` acquires it.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient


@dataclass
class _Blob:
    name: str
    data: bytes
    last_modified: datetime
    etag: str

    @property
    def size(self) -> int:
        return len(self.data)


class _FakeBlobClient:
    def __init__(self, store: dict[str, _Blob], name: str):
        self._store = store
        self._name = name

    def get_blob_properties(self) -> _Blob:
        if self._name not in self._store:
            raise ResourceNotFoundError("not found")
        return self._store[self._name]


class _FakeDownloader:
    def __init__(self, data: bytes):
        self._data = data

    def readall(self) -> bytes:
        return self._data


class _FakeContainerClient:
    def __init__(self):
        self._store: dict[str, _Blob] = {}

    def upload_blob(self, name, data, overwrite=True, content_settings=None):
        if name in self._store and not overwrite:
            raise ValueError("blob exists")
        self._store[name] = _Blob(
            name=name,
            data=data,
            last_modified=datetime.now(timezone.utc),
            etag=f"etag-{len(data)}-{abs(hash(data)) % 100000}",
        )

    def download_blob(self, name):
        if name not in self._store:
            raise ResourceNotFoundError("not found")
        return _FakeDownloader(self._store[name].data)

    def delete_blob(self, name):
        if name not in self._store:
            raise ResourceNotFoundError("not found")
        del self._store[name]

    def list_blobs(self, name_starts_with=""):
        return [b for name, b in self._store.items() if name.startswith(name_starts_with)]

    def get_blob_client(self, name):
        return _FakeBlobClient(self._store, name)


class _FakeServiceClient:
    account_name = "fakeaccount"
    url = "https://fakeaccount.blob.core.windows.net"

    def __init__(self):
        self.container = _FakeContainerClient()
        self.credential = type("Cred", (), {"account_key": None})()

    def get_container_client(self, name):
        return self.container


@contextmanager
def fake_azure_service(monkeypatch):
    """Patch BlobServiceClient construction to return an in-memory fake."""
    service = _FakeServiceClient()
    monkeypatch.setattr(
        BlobServiceClient, "from_connection_string", staticmethod(lambda *a, **kw: service)
    )
    yield service
