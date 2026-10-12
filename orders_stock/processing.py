import logging

from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from .models import Order, Outbox, Product, StockMovement

logger = logging.getLogger(__name__)


def process_outbox_batch(batch_size: int = 20) -> int:
    """Process pending events with row locks and idempotent stock effects."""
    candidate_ids = list(
        Outbox.objects.filter(processed_at__isnull=True)
        .order_by("id")
        .values_list("id", flat=True)[:batch_size]
    )
    processed_count = 0

    for outbox_id in candidate_ids:
        with transaction.atomic():
            event = (
                Outbox.objects.select_for_update(skip_locked=True)
                .filter(id=outbox_id, processed_at__isnull=True)
                .first()
            )
            if event is None:
                continue

            for item in (event.payload or {}).get("items", []):
                movement, created = StockMovement.objects.get_or_create(
                    order_id=event.order_id,
                    sku=item["sku"],
                    defaults={"qty": item["qty"]},
                )
                if created:
                    Product.objects.filter(sku=item["sku"]).update(
                        stock=Greatest(
                            F("stock") - Value(item["qty"]),
                            Value(0),
                        )
                    )

            Order.objects.filter(id=event.order_id).update(status="stock_reserved")
            event.processed_at = timezone.now()
            event.save(update_fields=["processed_at"])

        processed_count += 1
        logger.info("Processed outbox event #%s for order_id=%s", outbox_id, event.order_id)

    return processed_count
