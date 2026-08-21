import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.config import Settings, get_settings
from app.main import app

TEST_SETTINGS = Settings(
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
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(get_settings, None)
