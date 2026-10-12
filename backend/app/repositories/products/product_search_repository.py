import uuid

from elasticsearch import Elasticsearch

from app.search.products_index import alias

SEARCH_FIELDS = ["name^3", "sku^3", "category_name", "description"]


class ProductSearchRepository:
    def __init__(self, es: Elasticsearch) -> None:
        self.es = es

    def search(
        self, query: str, *, skip: int, limit: int
    ) -> tuple[list[uuid.UUID], int]:
        response = self.es.search(
            index=alias(),
            query={"multi_match": {"query": query, "fields": SEARCH_FIELDS}},
            source=False,
            from_=skip,
            size=limit,
            track_total_hits=True,
        )
        hits = response["hits"]
        return [uuid.UUID(hit["_id"]) for hit in hits["hits"]], hits["total"]["value"]
