"""One contract suite run against every backend.

The three implementations must behave identically in logical key space; this is
what makes swapping DOCHOST_STORAGE_BACKEND safe.
"""

import boto3
import pytest
from moto import mock_aws

from app.config import Settings
from app.storage import AzureBlobStorage, LocalFileStorage, S3Storage
from tests.fake_azure import fake_azure_service


@pytest.fixture(params=["local", "s3", "azure"])
def store(request, tmp_path, monkeypatch):
    kind = request.param

    if kind == "local":
        settings = Settings(
            storage_backend="local", local_storage_path=str(tmp_path), upload_api_key="k"
        )
        yield LocalFileStorage(settings)

    elif kind == "s3":
        settings = Settings(
            storage_backend="s3", s3_bucket="contract-bucket", s3_prefix="docs", upload_api_key="k"
        )
        with mock_aws():
            boto3.client("s3", region_name=settings.s3_region).create_bucket(Bucket=settings.s3_bucket)
            yield S3Storage(settings)

    else:
        settings = Settings(
            storage_backend="azure",
            azure_container="docs",
            azure_connection_string="UseDevelopmentStorage=true",
            upload_api_key="k",
        )
        with fake_azure_service(monkeypatch):
            yield AzureBlobStorage(settings)


def test_put_get_exists_roundtrip(store):
    assert store.object_exists("a/b/index.html") is False

    store.put_object("a/b/index.html", b"<html>hi</html>", "text/html")

    assert store.object_exists("a/b/index.html") is True
    assert store.get_object("a/b/index.html") == b"<html>hi</html>"


def test_get_metadata_reports_size_and_is_none_when_missing(store):
    assert store.get_metadata("a/missing.json") is None

    store.put_object("a/present.json", b'{"x": 1}', "application/json")
    info = store.get_metadata("a/present.json")

    assert info is not None
    assert info.key == "a/present.json"
    assert info.size == 8


def test_list_objects_returns_logical_keys_sorted(store):
    store.put_object("proj/v2/catalog.json", b"{}", "application/json")
    store.put_object("proj/v1/index.html", b"x", "text/html")
    store.put_object("other/v1/index.html", b"x", "text/html")

    listed = store.list_objects("proj/")

    assert [o.key for o in listed] == ["proj/v1/index.html", "proj/v2/catalog.json"]


def test_list_objects_is_empty_for_unknown_prefix(store):
    store.put_object("proj/v1/index.html", b"x", "text/html")
    assert store.list_objects("nothing/here/") == []


def test_delete_object_removes_it(store):
    store.put_object("proj/v1/index.html", b"x", "text/html")
    store.delete_object("proj/v1/index.html")
    assert store.object_exists("proj/v1/index.html") is False


def test_delete_missing_object_is_not_an_error(store):
    store.delete_object("proj/never/existed.html")


def test_overwrite_replaces_content(store):
    store.put_object("proj/v1/index.html", b"old", "text/html")
    store.put_object("proj/v1/index.html", b"new", "text/html")
    assert store.get_object("proj/v1/index.html") == b"new"


def test_health_check_passes_when_reachable(store):
    store.health_check()


def test_presigned_url_is_a_url_or_none(store):
    store.put_object("proj/v1/manifest.json", b"{}", "application/json")
    url = store.get_presigned_url("proj/v1/manifest.json", 900)
    assert url is None or url.startswith("http")


def test_local_backend_returns_no_presigned_url(tmp_path):
    settings = Settings(storage_backend="local", local_storage_path=str(tmp_path), upload_api_key="k")
    store = LocalFileStorage(settings)
    store.put_object("a.json", b"{}", "application/json")
    assert store.get_presigned_url("a.json", 900) is None


def test_s3_presigned_url_points_at_the_prefixed_key():
    settings = Settings(
        storage_backend="s3", s3_bucket="presign-bucket", s3_prefix="docs", upload_api_key="k"
    )
    with mock_aws():
        boto3.client("s3", region_name=settings.s3_region).create_bucket(Bucket=settings.s3_bucket)
        url = S3Storage(settings).get_presigned_url("proj/manifest.json", 900)

    assert "docs/proj/manifest.json" in url
    assert "Signature" in url or "X-Amz-Signature" in url
