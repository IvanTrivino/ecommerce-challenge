import uuid

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.unitofwork import UOWTransaction

from app.models import OutboxEvent, OutboxTopic, Product, ProductCategory

PRODUCT_SEARCH_FIELDS = ("name", "description", "sku", "category_uuid", "is_deleted")
CATEGORY_SEARCH_FIELDS = ("name", "is_deleted")


def _changed(obj: object, fields: tuple[str, ...]) -> bool:
    attrs = inspect(obj, raiseerr=True).attrs
    return any(attrs[field].history.has_changes() for field in fields)


def _topic_for(obj: object, *, is_new: bool) -> OutboxTopic | None:
    if isinstance(obj, Product):
        if is_new or _changed(obj, PRODUCT_SEARCH_FIELDS):
            return OutboxTopic.SEARCH_PRODUCT
    elif isinstance(obj, ProductCategory) and (
        is_new or _changed(obj, CATEGORY_SEARCH_FIELDS)
    ):
        return OutboxTopic.SEARCH_PRODUCT_CATEGORY
    return None


@event.listens_for(Session, "before_flush")
def _emit_search_events(
    session: Session, _flush_context: UOWTransaction, _instances: object
) -> None:
    for is_new, objects in ((True, list(session.new)), (False, list(session.dirty))):
        for obj in objects:
            topic = _topic_for(obj, is_new=is_new)
            if topic is None:
                continue
            if obj.id is None:
                obj.id = uuid.uuid4()
            session.add(OutboxEvent(topic=topic.value, aggregate_id=obj.id))
