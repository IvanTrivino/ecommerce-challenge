import argparse
import logging
import sys
import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.db import engine
from app.core.search import get_es
from app.models import OutboxTopic
from app.repositories import OutboxRepository, ProductRepository
from app.search import worker
from app.search.indexer import BatchResult, process_once, reindex_all
from app.search.products_index import alias, ensure_index


def _write(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _summary(result: BatchResult) -> int:
    for key, value in vars(result).items():
        _write(f"{key}: {value}")
    return 1 if result.failed or result.retried else 0


def _process(*, drain: bool) -> int:
    es = get_es()
    ensure_index(es)
    total = BatchResult()
    while True:
        with Session(engine) as session:
            result = process_once(session, es)
        for key, value in vars(result).items():
            setattr(total, key, getattr(total, key) + value)
        if not drain or result.claimed == 0:
            break
    return _summary(total)


def _enqueue(raw_ids: list[str]) -> int:
    try:
        ids = [uuid.UUID(raw) for raw in raw_ids]
    except ValueError as exc:
        sys.stderr.write(f"invalid UUID: {exc}\n")
        return 2
    with Session(engine) as session:
        OutboxRepository(session).add_many(OutboxTopic.SEARCH_PRODUCT, ids)
        session.commit()
    _write(f"enqueued: {len(ids)}")
    return 0


def _retry_failed() -> int:
    with Session(engine) as session:
        count = OutboxRepository(session).retry_failed()
        session.commit()
    _write(f"retried: {count}")
    return 0


def _status() -> int:
    es = get_es()
    with Session(engine) as session:
        stats = OutboxRepository(session).stats()
        indexable = ProductRepository(session).count_indexable()
    oldest = stats.oldest_pending_at.isoformat() if stats.oldest_pending_at else "none"
    index = (
        ", ".join(es.indices.get_alias(name=alias()))
        if es.indices.exists_alias(name=alias())
        else "none"
    )
    _write(f"pending: {stats.pending}")
    _write(f"failed: {stats.failed}")
    _write(f"oldest_pending_at: {oldest}")
    _write(f"index: {index}")
    _write(
        f"es_documents: {es.count(index=alias())['count'] if index != 'none' else 0}"
    )
    _write(f"indexable_products: {indexable}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.search")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="run the long-running indexer")
    process = commands.add_parser("process", help="process pending events")
    mode = process.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--drain", action="store_true")
    enqueue = commands.add_parser("enqueue", help="enqueue products for indexing")
    enqueue.add_argument("ids", nargs="+", metavar="product-uuid")
    commands.add_parser("retry-failed", help="requeue failed events")
    commands.add_parser("reindex", help="full reindex with alias swap")
    commands.add_parser("status", help="show backlog and index state")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = _parser().parse_args(argv)
    match args.command:
        case "run":
            worker.run()
            return 0
        case "process":
            return _process(drain=args.drain)
        case "enqueue":
            return _enqueue(args.ids)
        case "retry-failed":
            return _retry_failed()
        case "reindex":
            _write(reindex_all(get_es()))
            return 0
        case _:
            return _status()


if __name__ == "__main__":
    raise SystemExit(main())
