import abc
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from fastapi import Depends

from .config import Settings, get_settings


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    def put_object(self, key: str, body: bytes, content_type: str) -> None: ...

    @abc.abstractmethod
    def get_object(self, key: str) -> bytes: ...

    @abc.abstractmethod
    def object_exists(self, key: str) -> bool: ...


class S3Storage(StorageBackend):
    def __init__(self, settings: Settings):
        self._bucket = settings.s3_bucket
        self._prefix = settings.s3_prefix.strip("/")
        self._client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
        )

    def _key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    def put_object(self, key: str, body: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=self._key(key), Body=body, ContentType=content_type)

    def get_object(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=self._key(key))
        return response["Body"].read()

    def object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._key(key))
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise


class AzureBlobStorage(StorageBackend):
    def __init__(self, settings: Settings):
        from azure.storage.blob import BlobServiceClient

        self._prefix = settings.azure_prefix.strip("/")

        if settings.azure_connection_string:
            service_client = BlobServiceClient.from_connection_string(settings.azure_connection_string)
        else:
            service_client = BlobServiceClient(
                account_url=settings.azure_account_url,
                credential=settings.azure_account_key,
            )
        self._container_client = service_client.get_container_client(settings.azure_container)

    def _key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    def put_object(self, key: str, body: bytes, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        self._container_client.upload_blob(
            name=self._key(key),
            data=body,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    def get_object(self, key: str) -> bytes:
        downloader = self._container_client.download_blob(self._key(key))
        return downloader.readall()

    def object_exists(self, key: str) -> bool:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._container_client.get_blob_client(self._key(key)).get_blob_properties()
            return True
        except ResourceNotFoundError:
            return False


class LocalFileStorage(StorageBackend):
    def __init__(self, settings: Settings):
        self._root = Path(settings.local_storage_path).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if path != self._root and self._root not in path.parents:
            raise ValueError(f"Invalid storage key: {key}")
        return path

    def put_object(self, key: str, body: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def get_object(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def object_exists(self, key: str) -> bool:
        return self._path(key).is_file()


_BACKENDS: dict[str, type[StorageBackend]] = {
    "s3": S3Storage,
    "azure": AzureBlobStorage,
    "local": LocalFileStorage,
}


@lru_cache
def get_storage_backend(settings: Settings = Depends(get_settings)) -> StorageBackend:
    return _BACKENDS[settings.storage_backend](settings)
