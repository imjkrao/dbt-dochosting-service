from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOCHOST_", extra="ignore", frozen=True)

    upload_api_key: str
    storage_backend: Literal["s3", "azure", "local"] = "local"

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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
