import logging
import signal
import threading
from datetime import timedelta
from pathlib import Path
from typing import Final

from elasticsearch import Elasticsearch
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import engine
from app.core.search import get_es
from app.models.base import get_datetime_utc
from app.repositories import OutboxRepository
from app.search.indexer import BatchResult, process_once
from app.search.products_index import ensure_index

logger = logging.getLogger(__name__)

HEARTBEAT_PATH: Final = Path("/tmp/indexer-heartbeat")  # noqa: S108
PURGE_INTERVAL: Final = timedelta(minutes=10)


class Worker:
    def __init__(self, es: Elasticsearch) -> None:
        self.es = es
        self._stop = threading.Event()
        self._last_purge = get_datetime_utc()

    def request_stop(self, *_: object) -> None:
        self._stop.set()

    def _purge_if_due(self) -> None:
        now = get_datetime_utc()
        if now - self._last_purge < PURGE_INTERVAL:
            return
        self._last_purge = now
        cutoff = now - timedelta(days=settings.SEARCH_OUTBOX_RETENTION_DAYS)
        with Session(engine) as session:
            purged = OutboxRepository(session).purge_done(cutoff)
            session.commit()
        logger.info("purged %d done outbox events", purged)

    def run_iteration(self) -> BatchResult:
        with Session(engine) as session:
            result = process_once(session, self.es)
        HEARTBEAT_PATH.touch()
        self._purge_if_due()
        return result

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                result = self.run_iteration()
            except Exception:
                logger.exception("indexer iteration failed")
                self._stop.wait(settings.SEARCH_OUTBOX_POLL_SECONDS)
                continue
            if result.claimed < settings.SEARCH_OUTBOX_BATCH_SIZE:
                self._stop.wait(settings.SEARCH_OUTBOX_POLL_SECONDS)


def run() -> None:
    es = get_es()
    worker = Worker(es)
    signal.signal(signal.SIGTERM, worker.request_stop)
    signal.signal(signal.SIGINT, worker.request_stop)
    ensure_index(es)
    worker.run()
