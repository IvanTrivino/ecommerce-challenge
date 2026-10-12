from typing import Literal

from pydantic import BaseModel, Field

ProductImageContentType = Literal["image/jpeg", "image/png", "image/webp"]


class ProductImageUploadRequest(BaseModel):
    content_type: ProductImageContentType
    size: int = Field(gt=0)


class ProductImageUpload(BaseModel):
    url: str
    fields: dict[str, str]
    key: str
    image_url: str
    max_bytes: int
    expires_in: int
