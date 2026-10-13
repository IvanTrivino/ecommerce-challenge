import logging

from sqlalchemy.orm import Session

from app.core.db import engine, init_db
from app.core.storage import (
    ensure_bucket,
    ensure_product_images_bucket,
    ensure_product_imports_bucket,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    with Session(engine) as session:
        init_db(session)
    ensure_bucket()
    ensure_product_images_bucket()
    ensure_product_imports_bucket()


def main() -> None:
    logger.info("Creating initial data")
    init()
    logger.info("Initial data created")


if __name__ == "__main__":
    main()
