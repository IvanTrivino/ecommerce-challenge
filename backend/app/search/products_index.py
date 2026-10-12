from datetime import UTC, datetime, timedelta
from typing import Any

from elasticsearch import Elasticsearch

from app.core.config import settings
from app.models import Product, ProductCategory

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def alias() -> str:
    return settings.ELASTICSEARCH_PRODUCTS_ALIAS


def new_index_name() -> str:
    return f"{alias()}_{datetime.now(UTC):%Y%m%d%H%M%S%f}"


def index_body() -> dict[str, Any]:
    return {
        "settings": {
            "analysis": {
                "normalizer": {
                    "sku_normalizer": {
                        "type": "custom",
                        "filter": ["lowercase", "asciifolding"],
                    }
                }
            }
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "name": {"type": "text", "analyzer": "english"},
                "description": {"type": "text", "analyzer": "english"},
                "sku": {"type": "keyword", "normalizer": "sku_normalizer"},
                "category_name": {"type": "text", "analyzer": "english"},
                "updated_at": {"type": "date", "index": False},
            },
        },
    }


def create_index(es: Elasticsearch, name: str, *, with_alias: bool = False) -> None:
    body = index_body()
    es.indices.create(
        index=name,
        settings=body["settings"],
        mappings=body["mappings"],
        aliases={alias(): {}} if with_alias else None,
    )


def ensure_index(es: Elasticsearch) -> str:
    if es.indices.exists_alias(name=alias()):
        return next(iter(es.indices.get_alias(name=alias())))
    name = new_index_name()
    create_index(es, name, with_alias=True)
    return name


def is_indexable(product: Product, category: ProductCategory) -> bool:
    return not product.is_deleted and not category.is_deleted


def to_document(product: Product, category: ProductCategory) -> dict[str, Any]:
    return {
        "name": product.name,
        "description": product.description,
        "sku": product.sku,
        "category_name": category.name,
        "updated_at": max(product.updated_at, category.updated_at).isoformat(),
    }


def version(product: Product, category: ProductCategory) -> int:
    latest = max(product.updated_at, category.updated_at)
    return (latest - EPOCH) // timedelta(microseconds=1)
