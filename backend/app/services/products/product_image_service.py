import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import batched
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from app.core.config import settings
from app.core.exceptions import BadRequestError, ServiceUnavailableError
from app.core.storage import (
    PRODUCT_IMAGES_PREFIX,
    delete_objects,
    head_object,
    iter_objects,
    presign_post,
    product_image_url,
    product_images_public_url,
    read_prefix,
)
from app.repositories import ProductRepository
from app.schemas import ProductImageUpload, ProductImageUploadRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageType:
    extension: str
    matches: Callable[[bytes], bool]


IMAGE_TYPES: dict[str, ImageType] = {
    "image/jpeg": ImageType("jpg", lambda b: b.startswith(b"\xff\xd8\xff")),
    "image/png": ImageType("png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/webp": ImageType("webp", lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
}
CONTENT_TYPE_BY_EXTENSION = {t.extension: ct for ct, t in IMAGE_TYPES.items()}
KEY_PATTERN = re.compile(r"^products/[0-9a-f-]{36}\.(jpg|png|webp)$")
SIGNATURE_BYTES = 12
CACHE_CONTROL = "public, max-age=31536000, immutable"


class ProductImageService:
    def __init__(self, repo: ProductRepository) -> None:
        self.repo = repo

    def presign(self, request: ProductImageUploadRequest) -> ProductImageUpload:
        max_bytes = settings.PRODUCT_IMAGE_MAX_BYTES
        if request.size > max_bytes:
            raise BadRequestError(_too_large_message())
        expires_in = settings.PRODUCT_IMAGE_UPLOAD_EXPIRES_SECONDS
        extension = IMAGE_TYPES[request.content_type].extension
        key = f"{PRODUCT_IMAGES_PREFIX}{uuid4()}.{extension}"
        try:
            fields = presign_post(
                settings.S3_PRODUCT_IMAGES_BUCKET,
                key,
                fields={
                    "Content-Type": request.content_type,
                    "Cache-Control": CACHE_CONTROL,
                },
                max_bytes=max_bytes,
                expires_in=expires_in,
            )
        except (ClientError, BotoCoreError) as exc:
            logger.error("Could not presign product image upload", exc_info=True)
            raise ServiceUnavailableError("Image storage unavailable") from exc
        return ProductImageUpload(
            url=product_images_public_url(),
            fields=fields,
            key=key,
            image_url=product_image_url(key),
            max_bytes=max_bytes,
            expires_in=expires_in,
        )

    def verify(self, key: str) -> None:
        match = KEY_PATTERN.fullmatch(key)
        if not match:
            raise BadRequestError("Invalid image key")
        content_type = CONTENT_TYPE_BY_EXTENSION[match.group(1)]
        bucket = settings.S3_PRODUCT_IMAGES_BUCKET
        try:
            stored = head_object(bucket, key)
            if stored is None:
                raise BadRequestError("Image upload not found")
            if stored.size > settings.PRODUCT_IMAGE_MAX_BYTES:
                raise BadRequestError(_too_large_message())
            if stored.content_type != content_type:
                raise BadRequestError("Image type does not match")
            signature = read_prefix(bucket, key, SIGNATURE_BYTES)
        except (ClientError, BotoCoreError, EndpointConnectionError) as exc:
            logger.error("Could not verify product image %s", key, exc_info=True)
            raise ServiceUnavailableError("Image storage unavailable") from exc
        if not IMAGE_TYPES[content_type].matches(signature):
            raise BadRequestError("File is not a valid image")

    def sweep_orphans(self, *, now: datetime) -> int:
        bucket = settings.S3_PRODUCT_IMAGES_BUCKET
        cutoff = now - timedelta(hours=settings.PRODUCT_IMAGE_ORPHAN_GRACE_HOURS)
        deleted = 0
        for page in batched(
            iter_objects(bucket, PRODUCT_IMAGES_PREFIX), 1000, strict=False
        ):
            try:
                old = [obj.key for obj in page if obj.last_modified < cutoff]
                if not old:
                    continue
                orphans = sorted(set(old) - self.repo.referenced_image_keys(old))
                delete_objects(bucket, orphans)
                deleted += len(orphans)
            except ClientError, BotoCoreError:
                logger.warning("Product image sweep failed for a page", exc_info=True)
        logger.info("Deleted %d orphaned product images", deleted)
        return deleted


def _too_large_message() -> str:
    return f"Image must be {settings.PRODUCT_IMAGE_MAX_BYTES // (1024 * 1024)} MB or smaller"
