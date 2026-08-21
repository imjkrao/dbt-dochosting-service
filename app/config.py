from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: 100 MiB. Real dbt manifests on large projects reach tens of megabytes; this
#: bounds how much a single upload can ask the process to hold.
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOCHOST_", extra="ignore", frozen=True)

    upload_api_key: str
    storage_backend: Literal["s3", "azure", "local"] = "local"

    # Serving and limits
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    #: Redirect large artifacts to a time-limited storage URL instead of
    #: proxying the bytes. Off by default: it makes the browser fetch
    #: cross-origin, so the bucket needs a CORS rule first. See README.
    presigned_redirects: bool = False
    presigned_expiry_seconds: int = 900

    # Observability
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Local filesystem backend
    local_storage_path: str = "./data/docs"

    # S3 / S3-compatible backend
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_prefix: str = "docs"

    # Azure Blob Storage backend
    azure_container: str | None = None
    azure_connection_string: str | None = None
    azure_account_url: str | None = None
    azure_account_key: str | None = None
    azure_prefix: str = "docs"

    @model_validator(mode="after")
    def _validate_backend_config(self) -> "Settings":
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("DOCHOST_S3_BUCKET is required when DOCHOST_STORAGE_BACKEND=s3")
        if self.storage_backend == "azure":
            if not self.azure_container:
                raise ValueError("DOCHOST_AZURE_CONTAINER is required when DOCHOST_STORAGE_BACKEND=azure")
            if not (self.azure_connection_string or (self.azure_account_url and self.azure_account_key)):
                raise ValueError(
                    "DOCHOST_AZURE_CONNECTION_STRING, or both DOCHOST_AZURE_ACCOUNT_URL and "
                    "DOCHOST_AZURE_ACCOUNT_KEY, are required when DOCHOST_STORAGE_BACKEND=azure"
                )
        if self.max_upload_bytes <= 0:
            raise ValueError("DOCHOST_MAX_UPLOAD_BYTES must be positive")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
