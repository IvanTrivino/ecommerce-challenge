import warnings
from typing import Literal, Self

from pydantic import (
    EmailStr,
    PostgresDsn,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    FASTAPI_ENV: Literal["development"] | None = None

    PROJECT_NAME: str
    DATABASE_URL: PostgresDsn

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, value: str | PostgresDsn) -> str:
        database_url = str(value)
        for scheme in ("postgres://", "postgresql://"):
            if database_url.startswith(scheme):
                return database_url.replace(scheme, "postgresql+psycopg://", 1)
        return database_url

    REDIS_CACHE_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6380/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6380/1"

    S3_ENDPOINT_URL: str | None = "http://localhost:9000"
    S3_PUBLIC_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY: str = "changethis"
    S3_SECRET_KEY: str = "changethis"
    S3_REGION: str = "us-east-1"
    S3_BUCKET: str = "ecommerce"
    S3_ADDRESSING_STYLE: Literal["path", "virtual", "auto"] = "path"
    S3_PRODUCT_IMAGES_BUCKET: str = "product-images"
    S3_PRODUCT_IMAGES_PUBLIC_URL: str | None = None
    PRODUCT_IMAGE_MAX_BYTES: int = 5 * 1024 * 1024
    PRODUCT_IMAGE_UPLOAD_EXPIRES_SECONDS: int = 300
    PRODUCT_IMAGE_ORPHAN_GRACE_HOURS: int = 24
    S3_PRODUCT_IMPORTS_BUCKET: str = "product-imports"
    PRODUCT_IMPORT_MAX_BYTES: int = 10 * 1024 * 1024
    PRODUCT_IMPORT_UPLOAD_EXPIRES_SECONDS: int = 300
    PRODUCT_IMPORT_BATCH_SIZE: int = 10
    PRODUCT_IMPORT_MAX_RECORD_BYTES: int = 64 * 1024
    PRODUCT_IMPORT_MAX_STORED_ERRORS: int = 1000
    PRODUCT_IMPORT_RETENTION_DAYS: int = 7
    PRODUCT_IMPORT_STALE_MINUTES: int = 10

    CART_MAX_ITEMS: int = 50
    ORDER_CURRENCY: str = "USD"
    ORDER_NOTIFICATION_REQUEUE_AFTER_SECONDS: int = 120
    ORDER_NOTIFICATION_MAX_ATTEMPTS: int = 5
    ORDER_NOTIFICATION_BACKOFF_SECONDS: int = 30
    S3_CA_BUNDLE: str | None = None

    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTICSEARCH_API_KEY: str | None = None
    ELASTICSEARCH_PRODUCTS_ALIAS: str = "products"
    SEARCH_OUTBOX_POLL_SECONDS: float = 2
    SEARCH_OUTBOX_BATCH_SIZE: int = 500
    SEARCH_OUTBOX_MAX_ATTEMPTS: int = 10
    SEARCH_OUTBOX_RETENTION_DAYS: int = 7

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.FASTAPI_ENV == "development":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        for host in self.DATABASE_URL.hosts():
            self._check_default_secret("DATABASE_URL password", host["password"])
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )
        self._check_default_secret("S3_SECRET_KEY", self.S3_SECRET_KEY)

        return self


settings = Settings()  # type: ignore # ty: ignore[unused-ignore-comment]
