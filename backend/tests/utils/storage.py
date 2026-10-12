import httpx
from sqlalchemy.orm import Session

from app.core.db import engine
from app.repositories import ProductRepository
from app.schemas import ProductImageUpload, ProductImageUploadRequest
from app.services import ProductImageService

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8cfc0f01f0005000201a5f6e2b70000000049454e44ae426082"
)
JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP_HEADER = b"RIFF\x00\x00\x00\x00WEBPVP8 "


def post_upload(
    ticket: ProductImageUpload, body: bytes, content_type: str | None = None
) -> httpx.Response:
    return httpx.post(
        ticket.url,
        data=ticket.fields,
        files={"file": ("upload", body, content_type or ticket.fields["Content-Type"])},
    )


def upload_image(body: bytes = PNG_1PX, content_type: str = "image/png") -> str:
    with Session(engine) as session:
        service = ProductImageService(ProductRepository(session))
        ticket = service.presign(
            ProductImageUploadRequest.model_validate(
                {"content_type": content_type, "size": len(body)}
            )
        )
    response = post_upload(ticket, body)
    assert response.status_code == 204, response.text
    return ticket.key
