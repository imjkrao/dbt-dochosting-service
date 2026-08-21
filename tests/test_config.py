import pytest
from pydantic import ValidationError

from app.config import Settings


def test_s3_backend_requires_a_bucket():
    with pytest.raises(ValidationError, match="DOCHOST_S3_BUCKET"):
        Settings(storage_backend="s3", upload_api_key="k")


def test_azure_backend_requires_a_container():
    with pytest.raises(ValidationError, match="DOCHOST_AZURE_CONTAINER"):
        Settings(storage_backend="azure", upload_api_key="k")


def test_azure_backend_requires_credentials():
    with pytest.raises(ValidationError, match="DOCHOST_AZURE_CONNECTION_STRING"):
        Settings(storage_backend="azure", azure_container="docs", upload_api_key="k")


def test_azure_accepts_account_url_and_key():
    settings = Settings(
        storage_backend="azure",
        azure_container="docs",
        azure_account_url="https://acct.blob.core.windows.net",
        azure_account_key="secret",
        upload_api_key="k",
    )
    assert settings.azure_container == "docs"


def test_local_backend_needs_no_cloud_config():
    assert Settings(upload_api_key="k").storage_backend == "local"


def test_upload_cap_must_be_positive():
    with pytest.raises(ValidationError, match="MAX_UPLOAD_BYTES"):
        Settings(upload_api_key="k", max_upload_bytes=0)
