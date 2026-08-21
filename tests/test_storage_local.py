import pytest

from app.config import Settings
from app.storage import LocalFileStorage


def _store(tmp_path):
    settings = Settings(storage_backend="local", local_storage_path=str(tmp_path), upload_api_key="k")
    return LocalFileStorage(settings)


def test_put_get_exists_roundtrip(tmp_path):
    store = _store(tmp_path)

    assert store.object_exists("index.html") is False

    store.put_object("index.html", b"<html>docs</html>", "text/html")

    assert store.object_exists("index.html") is True
    assert store.get_object("index.html") == b"<html>docs</html>"


def test_creates_storage_directory_if_missing(tmp_path):
    target = tmp_path / "nested" / "docs"
    settings = Settings(storage_backend="local", local_storage_path=str(target), upload_api_key="k")

    LocalFileStorage(settings)

    assert target.is_dir()


def test_rejects_path_traversal(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(ValueError):
        store.put_object("../escape.txt", b"nope", "text/plain")
