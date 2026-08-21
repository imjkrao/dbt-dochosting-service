import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from .config import Settings


def get_s3_client(settings: Settings):
    return boto3.client(
        "s3",
        region_name=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=Config(signature_version="s3v4"),
    )


def object_key(settings: Settings, filename: str) -> str:
    return f"{settings.s3_prefix.strip('/')}/{filename}"


def put_object(settings: Settings, filename: str, body: bytes, content_type: str) -> None:
    client = get_s3_client(settings)
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=object_key(settings, filename),
        Body=body,
        ContentType=content_type,
    )


def get_object(settings: Settings, filename: str) -> bytes:
    client = get_s3_client(settings)
    response = client.get_object(Bucket=settings.s3_bucket, Key=object_key(settings, filename))
    return response["Body"].read()


def object_exists(settings: Settings, filename: str) -> bool:
    client = get_s3_client(settings)
    try:
        client.head_object(Bucket=settings.s3_bucket, Key=object_key(settings, filename))
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            return False
        raise
