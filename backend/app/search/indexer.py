import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final

import elasticsearch
from elasticsearch import Elasticsearch, helpers
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import engine
from app.models import OutboxEvent, OutboxTopic, Product, ProductCategory
from app.repositories import OutboxRepository, ProductRepository
from app.search.products_index import (
    alias,
    create_index,
    is_indexable,
    new_index_name,
    to_document,
    version,
)

logger = logging.getLogger(__name__)

INDEXER_LOCK_KEY: Final = 0x53_45_41_52_43_48
CHUNK_SIZE: Final = 500

type Action = dict[str, Any]


@dataclass
class BatchResult:
    claimed: int = 0
    indexed: int = 0
    deleted: int = 0
    retried: int = 0
    failed: int = 0


def _index_action(index: str, product: Product, category: ProductCategory) -> Action:
    return {
        "_op_type": "index",
        "_index": index,
        "_id": str(product.id),
        "_source": to_document(product, category),
        "version": version(product, category),
        "version_type": "external",
    }


def _delete_action(index: str, product: Product, category: ProductCategory) -> Action:
    return {
        "_op_type": "delete",
        "_index": index,
        "_id": str(product.id),
        "version": version(product, category),
        "version_type": "external",
    }


def _build_actions(
    product_ids: Iterable[uuid.UUID],
    rows: dict[uuid.UUID, tuple[Product, ProductCategory]],
) -> list[Action]:
    """One action per product, however many events pointed at it."""
    actions: list[Action] = []
    for product_id in product_ids:
        row = rows.get(product_id)
        if row is None:
            actions.append(
                {"_op_type": "delete", "_index": alias(), "_id": str(product_id)}
            )
        elif is_indexable(*row):
            actions.append(_index_action(alias(), *row))
        else:
            actions.append(_delete_action(alias(), *row))
    return actions


def _targets(
    events: list[OutboxEvent],
    rows: dict[uuid.UUID, tuple[Product, ProductCategory]],
) -> dict[int, set[uuid.UUID]]:
    """Map each event id to the product ids it affects."""
    by_category: dict[uuid.UUID, set[uuid.UUID]] = {}
    for product, _ in rows.values():
        by_category.setdefault(product.category_uuid, set()).add(product.id)
    targets: dict[int, set[uuid.UUID]] = {}
    for event in events:
        if event.topic == OutboxTopic.SEARCH_PRODUCT:
            targets[event.id] = {event.aggregate_id}
        else:
            targets[event.id] = by_category.get(event.aggregate_id, set())
    return targets


def _send(
    es: Elasticsearch, actions: list[Action]
) -> tuple[dict[uuid.UUID, str], int, int]:
    """Run the bulk; return failures by product id, plus indexed and deleted counts."""
    failures: dict[uuid.UUID, str] = {}
    indexed = deleted = 0
    results = helpers.streaming_bulk(
        es,
        actions,
        chunk_size=CHUNK_SIZE,
        raise_on_error=False,
        raise_on_exception=False,
        max_retries=0,
    )
    for ok, item in results:
        op, detail = next(iter(item.items()))
        status = detail.get("status")
        if ok or status == 409 or (op == "delete" and status == 404):
            if op == "delete":
                deleted += 1
            else:
                indexed += 1
            continue
        failures[uuid.UUID(detail["_id"])] = str(detail.get("error", detail))
    return failures, indexed, deleted


def _settle(
    repo: OutboxRepository,
    events: list[OutboxEvent],
    targets: dict[int, set[uuid.UUID]],
    failures: dict[uuid.UUID, str],
    result: BatchResult,
) -> None:
    done: list[OutboxEvent] = []
    for event in events:
        errors = [failures[pid] for pid in targets[event.id] if pid in failures]
        if not errors:
            done.append(event)
            continue
        repo.mark_retry(
            event, errors[0], max_attempts=settings.SEARCH_OUTBOX_MAX_ATTEMPTS
        )
        _count_retry(event, result)
    repo.mark_done(done)


def _count_retry(event: OutboxEvent, result: BatchResult) -> None:
    if event.status == "failed":
        result.failed += 1
    else:
        result.retried += 1


def process_once(session: Session, es: Elasticsearch) -> BatchResult:
    result = BatchResult()
    if not session.scalar(
        select(func.pg_try_advisory_xact_lock_shared(INDEXER_LOCK_KEY))
    ):
        session.rollback()
        return result 

    outbox = OutboxRepository(session)
    events = outbox.claim_batch(settings.SEARCH_OUTBOX_BATCH_SIZE)
    result.claimed = len(events)
    if not events:
        session.commit()
        return result

    products = ProductRepository(session)
    product_ids = {
        e.aggregate_id for e in events if e.topic == OutboxTopic.SEARCH_PRODUCT
    }
    category_ids = {
        e.aggregate_id for e in events if e.topic == OutboxTopic.SEARCH_PRODUCT_CATEGORY
    }
    if category_ids:
        product_ids.update(products.list_ids_by_category(category_ids))
    rows = {p.id: (p, c) for p, c in products.get_many_with_category(product_ids)}
    targets = _targets(events, rows)

    all_ids = product_ids | {pid for ids in targets.values() for pid in ids}
    actions = _build_actions(sorted(all_ids), rows)
    try:
        failures, result.indexed, result.deleted = _send(es, actions)
    except (elasticsearch.ApiError, elasticsearch.TransportError) as exc:
        for event in events:
            outbox.mark_retry(
                event, repr(exc), max_attempts=settings.SEARCH_OUTBOX_MAX_ATTEMPTS
            )
            _count_retry(event, result)
    else:
        _settle(outbox, events, targets, failures, result)

    session.commit()
    logger.info(
        "claimed=%d indexed=%d deleted=%d retried=%d failed=%d",
        result.claimed,
        result.indexed,
        result.deleted,
        result.retried,
        result.failed,
    )
    return result


def _current_indices(es: Elasticsearch) -> list[str]:
    if not es.indices.exists_alias(name=alias()):
        return []
    return list(es.indices.get_alias(name=alias()))


def reindex_all(es: Elasticsearch) -> str:
    with engine.connect() as lock_conn:
        lock_conn.execute(select(func.pg_advisory_lock(INDEXER_LOCK_KEY)))
        try:
            new_name = new_index_name()
            create_index(es, new_name)
            with Session(engine) as session:
                repo = ProductRepository(session)
                helpers.bulk(
                    es,
                    (
                        _index_action(new_name, product, category)
                        for product, category in repo.iter_indexable(CHUNK_SIZE)
                    ),
                    chunk_size=CHUNK_SIZE,
                )
            es.indices.refresh(index=new_name)

            old = _current_indices(es)
            actions: list[dict[str, Any]] = [
                {"remove": {"index": name, "alias": alias()}} for name in old
            ]
            actions.append({"add": {"index": new_name, "alias": alias()}})
            es.indices.update_aliases(actions=actions)
            for name in old:
                es.indices.delete(index=name, ignore_unavailable=True)
            return new_name
        finally:
            lock_conn.execute(select(func.pg_advisory_unlock(INDEXER_LOCK_KEY)))
            lock_conn.commit()
