import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.config import Settings, get_settings
from app.main import app
from app.storage import S3Storage, get_storage_backend

TEST_SETTINGS = Settings(
    storage_backend="s3",
    s3_bucket="test-docs-bucket",
    s3_region="us-east-1",
    upload_api_key="test-api-key",
)


@pytest.fixture
def settings():
    return TEST_SETTINGS


@pytest.fixture
def client(settings):
    with mock_aws():
        boto3.client("s3", region_name=settings.s3_region).create_bucket(Bucket=settings.s3_bucket)

        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_storage_backend] = lambda: S3Storage(settings)
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.clear()
