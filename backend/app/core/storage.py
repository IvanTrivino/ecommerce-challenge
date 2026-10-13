import logging
import time
from functools import lru_cache
from typing import TYPE_CHECKING, BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from app.core.config import settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)


def _build_client(endpoint_url: str | None) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": settings.S3_ADDRESSING_STYLE},
            # Newer boto3 adds CRC checksums by default, which many
            # S3-compatible stores reject. Only send them when required.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


@lru_cache
def get_s3() -> S3Client:
    return _build_client(settings.S3_ENDPOINT_URL)


@lru_cache
def _get_presign_client() -> S3Client:
    # Presigned URLs embed the host, so sign them against the endpoint
    # that browsers can reach (e.g. localhost vs the Docker service name).
    return _build_client(settings.S3_PUBLIC_ENDPOINT_URL or settings.S3_ENDPOINT_URL)


def ensure_bucket(bucket: str = settings.S3_BUCKET, wait_seconds: int = 60) -> None:
    """Create the bucket if missing, waiting for the store to come up."""
    s3 = get_s3()
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            s3.head_bucket(Bucket=bucket)
            return
        except EndpointConnectionError:
            if time.monotonic() > deadline:
                raise
            logger.info("Object storage not reachable yet, retrying")
            time.sleep(2)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
                raise
            logger.info("Creating bucket %s", bucket)
            s3.create_bucket(Bucket=bucket)
            return


def upload_file(fileobj: BinaryIO, key: str, content_type: str | None = None) -> None:
    extra = {"ContentType": content_type} if content_type else None
    get_s3().upload_fileobj(fileobj, settings.S3_BUCKET, key, ExtraArgs=extra)


def delete_file(key: str) -> None:
    get_s3().delete_object(Bucket=settings.S3_BUCKET, Key=key)


def presigned_url(key: str, expires_in: int = 3600) -> str:
    return _get_presign_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )
