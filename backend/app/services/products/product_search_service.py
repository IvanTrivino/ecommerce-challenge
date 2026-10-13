import logging
import uuid
from typing import cast

import elasticsearch
from redis.exceptions import RedisError

from app.core import cache
from app.core.exceptions import ServiceUnavailableError
from app.repositories import ProductRepository, ProductSearchRepository
from app.schemas import ProductPublic, ProductsPublic
from app.services.products.cache import PRODUCTS
from app.services.products.product_service import ProductService

logger = logging.getLogger(__name__)


class ProductSearchService:
    def __init__(
        self, search_repo: ProductSearchRepository, repo: ProductRepository
    ) -> None:
        self.search_repo = search_repo
        self.repo = repo

    def search(self, query: str, *, skip: int, limit: int) -> ProductsPublic:
        try:
            ids, total = self.search_repo.search(query, skip=skip, limit=limit)
        except (elasticsearch.ApiError, elasticsearch.TransportError) as exc:
            raise ServiceUnavailableError("Search is temporarily unavailable") from exc

        products = self._load(ids)
        return ProductsPublic(
            data=[products[i] for i in ids if i in products], count=total
        )

    def _load(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, ProductPublic]:
        if not ids:
            return {}
        found: dict[uuid.UUID, ProductPublic] = {}
        keys: list[str] = []
        try:
            keys = PRODUCTS.keys(
                ProductService.get_by_id, [{"product_id": i} for i in ids]
            )
            for product_id, hit in zip(
                ids, cast(list[str | None], cache.get_cache().mget(keys)), strict=True
            ):
                if hit is not None:
                    found[product_id] = ProductPublic.model_validate_json(hit)
        except RedisError:
            logger.warning("Cache read failed, skipping cache", exc_info=True)
            keys = []
            found = {}

        missing = [i for i in ids if i not in found]
        if missing:
            key_by_id = dict(zip(ids, keys, strict=False))
            for product in self.repo.get_many(missing):
                public = ProductPublic.model_validate(product)
                found[product.id] = public
                self._store(key_by_id.get(product.id), public)
        return found

    def _store(self, key: str | None, product: ProductPublic) -> None:
        if key is None:
            return
        try:
            cache.get_cache().set(key, product.model_dump_json(), ex=PRODUCTS.expiry())
        except RedisError:
            logger.warning("Cache write failed", exc_info=True)
