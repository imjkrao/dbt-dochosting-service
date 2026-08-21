"""Pluggable object storage.

Backends work in a *logical* key space (``orgs/…/versions/…/index.html``). Each
implementation maps that onto its own physical layout by applying the configured
prefix, and strips the prefix again on the way out, so callers never see it.

``get_presigned_url`` returns ``None`` when a backend cannot issue one (local
storage always; Azure without an account key). Callers must fall back to
proxying the bytes themselves rather than assuming a URL is available.
"""

import abc
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from .config import Settings, get_settings


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    last_modified: datetime | None = None
    etag: str | None = None


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    def put_object(self, key: str, body: bytes, content_type: str) -> None: ...

    @abc.abstractmethod
    def get_object(self, key: str) -> bytes: ...

    @abc.abstractmethod
    def object_exists(self, key: str) -> bool: ...

    @abc.abstractmethod
    def delete_object(self, key: str) -> None:
        """Delete a key. Deleting a missing key is not an error."""

    @abc.abstractmethod
    def list_objects(self, prefix: str) -> list[ObjectInfo]:
        """List objects under a logical prefix, sorted by key."""

    @abc.abstractmethod
    def get_metadata(self, key: str) -> ObjectInfo | None:
        """Return metadata for a key, or None when it does not exist."""

    @abc.abstractmethod
    def get_presigned_url(self, key: str, expires_in: int) -> str | None:
        """A time-limited direct download URL, or None if unsupported."""

    def health_check(self) -> None:
        """Raise if the backend is unreachable or misconfigured."""
        self.object_exists("__healthcheck__")


class _PrefixedBackend(StorageBackend):
    """Shared logical-key <-> physical-key translation."""

    _prefix: str = ""

    def _physical(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    def _logical(self, key: str) -> str:
        if self._prefix and key.startswith(f"{self._prefix}/"):
            return key[len(self._prefix) + 1 :]
        return key


class S3Storage(_PrefixedBackend):
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

    @staticmethod
    def _is_missing(exc: ClientError) -> bool:
        return exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey")

    def put_object(self, key: str, body: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=self._physical(key), Body=body, ContentType=content_type
        )

    def get_object(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=self._physical(key))
        return response["Body"].read()

    def object_exists(self, key: str) -> bool:
        return self.get_metadata(key) is not None

    def delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._physical(key))

    def list_objects(self, prefix: str) -> list[ObjectInfo]:
        paginator = self._client.get_paginator("list_objects_v2")
        found: list[ObjectInfo] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._physical(prefix)):
            for item in page.get("Contents", []):
                found.append(
                    ObjectInfo(
                        key=self._logical(item["Key"]),
                        size=item["Size"],
                        last_modified=item.get("LastModified"),
                        etag=(item.get("ETag") or "").strip('"') or None,
                    )
                )
        return sorted(found, key=lambda o: o.key)

    def get_metadata(self, key: str) -> ObjectInfo | None:
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=self._physical(key))
        except ClientError as exc:
            if self._is_missing(exc):
                return None
            raise
        return ObjectInfo(
            key=key,
            size=head["ContentLength"],
            last_modified=head.get("LastModified"),
            etag=(head.get("ETag") or "").strip('"') or None,
        )

    def get_presigned_url(self, key: str, expires_in: int) -> str | None:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": self._physical(key)},
            ExpiresIn=expires_in,
        )


class AzureBlobStorage(_PrefixedBackend):
    def __init__(self, settings: Settings):
        from azure.storage.blob import BlobServiceClient

        self._prefix = settings.azure_prefix.strip("/")
        self._container = settings.azure_container

        if settings.azure_connection_string:
            service_client = BlobServiceClient.from_connection_string(settings.azure_connection_string)
        else:
            service_client = BlobServiceClient(
                account_url=settings.azure_account_url,
                credential=settings.azure_account_key,
            )
        self._service_client = service_client
        self._container_client = service_client.get_container_client(settings.azure_container)
        # Needed to sign SAS URLs; absent when authenticating by token credential.
        self._account_key = settings.azure_account_key or getattr(
            service_client.credential, "account_key", None
        )

    def put_object(self, key: str, body: bytes, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        self._container_client.upload_blob(
            name=self._physical(key),
            data=body,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    def get_object(self, key: str) -> bytes:
        return self._container_client.download_blob(self._physical(key)).readall()

    def object_exists(self, key: str) -> bool:
        return self.get_metadata(key) is not None

    def delete_object(self, key: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._container_client.delete_blob(self._physical(key))
        except ResourceNotFoundError:
            pass

    def list_objects(self, prefix: str) -> list[ObjectInfo]:
        found = [
            ObjectInfo(
                key=self._logical(blob.name),
                size=blob.size or 0,
                last_modified=blob.last_modified,
                etag=(blob.etag or "").strip('"') or None,
            )
            for blob in self._container_client.list_blobs(name_starts_with=self._physical(prefix))
        ]
        return sorted(found, key=lambda o: o.key)

    def get_metadata(self, key: str) -> ObjectInfo | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            props = self._container_client.get_blob_client(self._physical(key)).get_blob_properties()
        except ResourceNotFoundError:
            return None
        return ObjectInfo(
            key=key,
            size=props.size or 0,
            last_modified=props.last_modified,
            etag=(props.etag or "").strip('"') or None,
        )

    def get_presigned_url(self, key: str, expires_in: int) -> str | None:
        if not self._account_key:
            return None

        from datetime import timedelta

        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        physical = self._physical(key)
        token = generate_blob_sas(
            account_name=self._service_client.account_name,
            container_name=self._container,
            blob_name=physical,
            account_key=self._account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        )
        return f"{self._service_client.url.rstrip('/')}/{self._container}/{physical}?{token}"


class LocalFileStorage(StorageBackend):
    def __init__(self, settings: Settings):
        self._root = Path(settings.local_storage_path).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if path != self._root and self._root not in path.parents:
            raise ValueError(f"Invalid storage key: {key}")
        return path

    def _info(self, path: Path) -> ObjectInfo:
        stat = path.stat()
        return ObjectInfo(
            key=path.relative_to(self._root).as_posix(),
            size=stat.st_size,
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            etag=f"{int(stat.st_mtime_ns)}-{stat.st_size}",
        )

    def put_object(self, key: str, body: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def get_object(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def object_exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete_object(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def list_objects(self, prefix: str) -> list[ObjectInfo]:
        # Resolve the prefix's parent so a partial trailing segment still matches.
        base = self._path(prefix) if prefix else self._root
        search_root = base if base.is_dir() else base.parent
        if not search_root.exists():
            return []
        found = [
            self._info(path)
            for path in search_root.rglob("*")
            if path.is_file() and path.relative_to(self._root).as_posix().startswith(prefix)
        ]
        return sorted(found, key=lambda o: o.key)

    def get_metadata(self, key: str) -> ObjectInfo | None:
        path = self._path(key)
        return self._info(path) if path.is_file() else None

    def get_presigned_url(self, key: str, expires_in: int) -> str | None:
        return None  # No URL to hand out; the caller proxies the bytes.

    def health_check(self) -> None:
        if not self._root.is_dir():
            raise RuntimeError(f"Storage path is not a directory: {self._root}")


_BACKENDS: dict[str, type[StorageBackend]] = {
    "s3": S3Storage,
    "azure": AzureBlobStorage,
    "local": LocalFileStorage,
}


def build_storage_backend(settings: Settings) -> StorageBackend:
    return _BACKENDS[settings.storage_backend](settings)


def get_storage_backend() -> StorageBackend:
    """FastAPI dependency.

    Deliberately *not* ``lru_cache``d: a process-wide singleton cannot support
    per-tenant configuration later. The app builds one backend at startup and
    overrides this dependency, so construction does not happen per request.
    """
    return build_storage_backend(get_settings())
