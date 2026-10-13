import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ProductImportUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255, pattern=r"(?i)^.+\.csv$")
    size: int = Field(gt=0)


class ProductImportUpload(BaseModel):
    url: str
    fields: dict[str, str]
    key: str
    max_bytes: int
    expires_in: int


class ProductImportCreate(BaseModel):
    key: str = Field(max_length=512)
    filename: str = Field(min_length=1, max_length=255)


ProductImportStatusLiteral = Literal["pending", "running", "completed", "failed"]


class ProductImportPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    filename: str
    status: ProductImportStatusLiteral
    total_bytes: int
    bytes_processed: int
    created_count: int
    updated_count: int
    unchanged_count: int
    error_count: int
    blank_count: int
    categories_created: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    file_deleted_at: datetime | None
    created_by_email: str | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def progress(self) -> int:
        if self.status == "completed":
            return 100
        if self.total_bytes <= 0:
            return 0
        return min(99, self.bytes_processed * 100 // self.total_bytes)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def can_retry(self) -> bool:
        return self.status == "failed" and self.file_deleted_at is None


class ProductImportsPublic(BaseModel):
    data: list[ProductImportPublic]
    count: int


class ProductImportErrorPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line: int
    sku: str | None
    message: str


class ProductImportErrorsPublic(BaseModel):
    data: list[ProductImportErrorPublic]
    count: int
    truncated: bool
