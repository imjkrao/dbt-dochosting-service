import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.config import Settings
from app.main import create_app

API_KEY = "test-api-key"


def make_settings(**overrides) -> Settings:
    defaults = {
        "storage_backend": "s3",
        "s3_bucket": "test-docs-bucket",
        "s3_region": "us-east-1",
        "upload_api_key": API_KEY,
        "log_format": "text",
    }
    return Settings(**{**defaults, **overrides})


@pytest.fixture
def settings():
    return make_settings()


@pytest.fixture
def client(settings):
    with mock_aws():
        boto3.client("s3", region_name=settings.s3_region).create_bucket(Bucket=settings.s3_bucket)
        yield TestClient(create_app(settings))


@pytest.fixture
def local_client(tmp_path):
    settings = make_settings(storage_backend="local", local_storage_path=str(tmp_path), s3_bucket=None)
    yield TestClient(create_app(settings))


def upload(client, *, project=None, api_key=API_KEY, index=b"<html>docs</html>", run_results=False):
    files = {
        "index_html": ("index.html", index, "text/html"),
        "manifest_json": ("manifest.json", b'{"nodes": {}}', "application/json"),
        "catalog_json": ("catalog.json", b'{"nodes": {}}', "application/json"),
    }
    if run_results:
        files["run_results_json"] = ("run_results.json", b'{"results": []}', "application/json")
    url = "/upload" if project is None else f"/api/v1/projects/{project}/versions"
    return client.post(url, files=files, headers={"x-api-key": api_key})
