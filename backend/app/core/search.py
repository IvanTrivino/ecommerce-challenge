from functools import lru_cache

from elasticsearch import Elasticsearch

from app.core.config import settings


@lru_cache
def get_es() -> Elasticsearch:
    return Elasticsearch(
        settings.ELASTICSEARCH_URL,
        api_key=settings.ELASTICSEARCH_API_KEY,
    )
