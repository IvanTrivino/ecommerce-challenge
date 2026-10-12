import json
import logging
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from itertools import batched
from typing import TYPE_CHECKING, Any, BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from app.core.config import settings

PRODUCT_IMAGES_PREFIX = "products/"
_NOT_FOUND_CODES = ("404", "NoSuchKey", "NotFound")

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
        verify=settings.S3_CA_BUNDLE,
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


def ensure_bucket(bucket: str | None = None, wait_seconds: int = 60) -> None:
    """Create the bucket if missing, waiting for the store to come up."""
    bucket = bucket or settings.S3_BUCKET
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

@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    content_type: str | None
    last_modified: datetime


def _public_read_policy(bucket: str) -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/{PRODUCT_IMAGES_PREFIX}*"],
            }
        ],
    }


def ensure_product_images_bucket() -> None:
    """Create the public images bucket and (re)apply its policy and CORS. Idempotent."""
    bucket = settings.S3_PRODUCT_IMAGES_BUCKET
    ensure_bucket(bucket)
    s3 = get_s3()
    s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(_public_read_policy(bucket)))
    s3.put_bucket_cors(
        Bucket=bucket,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedOrigins": [settings.FRONTEND_HOST],
                    "AllowedMethods": ["GET", "POST"],
                    "AllowedHeaders": ["*"],
                    "MaxAgeSeconds": 3600,
                }
            ]
        },
    )


def product_images_public_url() -> str:
    """Browser-reachable URL of the images bucket root, without a trailing slash."""
    bucket = settings.S3_PRODUCT_IMAGES_BUCKET
    if settings.S3_PRODUCT_IMAGES_PUBLIC_URL:
        return settings.S3_PRODUCT_IMAGES_PUBLIC_URL.rstrip("/")
    endpoint = settings.S3_PUBLIC_ENDPOINT_URL or settings.S3_ENDPOINT_URL
    if endpoint:
        return f"{endpoint.rstrip('/')}/{bucket}"
    return f"https://{bucket}.s3.{settings.S3_REGION}.amazonaws.com"


def product_image_url(key: str) -> str:
    return f"{product_images_public_url()}/{key}"


def presign_post(
    bucket: str, key: str, *, fields: dict[str, str], max_bytes: int, expires_in: int
) -> dict[str, str]:
    """Form fields for a browser POST upload of `key`. Every field in `fields` is pinned by the policy."""
    post = get_s3().generate_presigned_post(
        bucket,
        key,
        Fields=fields,
        Conditions=[{name: value} for name, value in fields.items()]
        + [["content-length-range", 1, max_bytes]],
        ExpiresIn=expires_in,
    )
    return dict(post["fields"])


def head_object(bucket: str, key: str) -> StoredObject | None:
    """None if the object doesn't exist. Other errors propagate."""
    try:
        response = get_s3().head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in _NOT_FOUND_CODES:
            return None
        raise
    return StoredObject(
        key=key,
        size=response["ContentLength"],
        content_type=response.get("ContentType"),
        last_modified=response["LastModified"],
    )


def read_prefix(bucket: str, key: str, length: int) -> bytes:
    response = get_s3().get_object(
        Bucket=bucket, Key=key, Range=f"bytes=0-{length - 1}"
    )
    return response["Body"].read()


def iter_objects(bucket: str, prefix: str) -> Iterator[StoredObject]:
    paginator = get_s3().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            yield StoredObject(
                key=item["Key"],
                size=item["Size"],
                content_type=None,
                last_modified=item["LastModified"],
            )


def delete_objects(bucket: str, keys: Sequence[str]) -> None:
    for chunk in batched(keys, 1000, strict=False):
        response = get_s3().delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
        )
        for error in response.get("Errors", []):
            logger.warning(
                "Could not delete %s from %s: %s",
                error.get("Key"),
                bucket,
                error.get("Message"),
            )
