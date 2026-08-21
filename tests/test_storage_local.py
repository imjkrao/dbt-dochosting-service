"""Local-backend specifics not covered by the shared contract suite."""

import pytest

from app.config import Settings
from app.storage import LocalFileStorage


def _store(tmp_path):
    settings = Settings(storage_backend="local", local_storage_path=str(tmp_path), upload_api_key="k")
    return LocalFileStorage(settings)


def test_creates_storage_directory_if_missing(tmp_path):
    target = tmp_path / "nested" / "docs"
    settings = Settings(storage_backend="local", local_storage_path=str(target), upload_api_key="k")

    LocalFileStorage(settings)

    assert target.is_dir()


@pytest.mark.parametrize("key", ["../escape.txt", "a/../../escape.txt", "../../etc/passwd"])
def test_rejects_path_traversal(tmp_path, key):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.put_object(key, b"nope", "text/plain")


def test_nested_keys_create_intermediate_directories(tmp_path):
    store = _store(tmp_path)
    store.put_object("orgs/default/projects/p/versions/v1/index.html", b"x", "text/html")
    assert (tmp_path / "orgs/default/projects/p/versions/v1/index.html").is_file()


def test_health_check_fails_when_root_disappears(tmp_path):
    store = _store(tmp_path)
    (tmp_path).rmdir()
    with pytest.raises(RuntimeError):
        store.health_check()
