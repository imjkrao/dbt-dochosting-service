import boto3
from moto import mock_aws

from app.config import Settings
from app.storage import S3Storage


def _settings(**overrides):
    defaults = {"storage_backend": "s3", "s3_bucket": "unit-test-bucket", "upload_api_key": "k"}
    return Settings(**{**defaults, **overrides})


def test_put_get_exists_roundtrip():
    with mock_aws():
        settings = _settings()
        boto3.client("s3", region_name=settings.s3_region).create_bucket(Bucket=settings.s3_bucket)
        store = S3Storage(settings)

        assert store.object_exists("index.html") is False

        store.put_object("index.html", b"<html>docs</html>", "text/html")

        assert store.object_exists("index.html") is True
        assert store.get_object("index.html") == b"<html>docs</html>"


def test_keys_are_namespaced_by_prefix():
    with mock_aws():
        settings = _settings(s3_prefix="my-project")
        client = boto3.client("s3", region_name=settings.s3_region)
        client.create_bucket(Bucket=settings.s3_bucket)
        store = S3Storage(settings)

        store.put_object("index.html", b"content", "text/html")

        client.head_object(Bucket=settings.s3_bucket, Key="my-project/index.html")
