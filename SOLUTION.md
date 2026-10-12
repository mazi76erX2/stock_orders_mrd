# Solution: Design Notes and Trade-offs

## Overview

This is a vertical slice of an orders and stock system: a Django HTTP API
stores orders in PostgreSQL, a polling worker applies stock updates, and a
cursor-based event feed provides the required Option A integration surface.
The implementation prioritises durable state, duplicate safety, and a
demonstrable outage recovery path over production-scale infrastructure.

```text
POST /orders
    |
    | one PostgreSQL transaction
    v
orders + order_items + outbox
                         |
                         | process_outbox_loop
                         v
                 stock_movements + products + order status
```

The API does not synchronously reserve stock. This keeps order intake
available while the worker is stopped; restarting the worker processes the
durable outbox backlog.

---

## Backend

### Hybrid persistence

The Django ORM is the default for CRUD, relationships, serialization, and the
worker. The one raw SQL boundary is the order insert:
`INSERT ... ON CONFLICT (order_ref) DO NOTHING RETURNING id`.

That statement makes the most important correctness property—duplicate order
handling—one visible PostgreSQL operation. It inserts a new order, does
nothing for a duplicate reference, and returns the new ID only when insertion
succeeded. The order, line items, and outbox event still share one
`transaction.atomic()` block.

The processor uses ORM equivalents of PostgreSQL concurrency features:
`select_for_update(skip_locked=True)` for event claiming and
`Greatest(F("stock") - qty, 0)` for atomic stock clamping. This preserves the
model and migration layer as the source of truth while using SQL only where it
adds a clear guarantee.

### Order intake and duplicate submissions

`order_ref` has a database uniqueness constraint. The order endpoint inserts
the order with `INSERT ... ON CONFLICT (order_ref) DO NOTHING RETURNING id`
inside one transaction. A returned row means this request created the order;
no returned row means the reference already exists.

For a newly accepted order, the same transaction writes:

1. The order and its calculated total.
2. Price-snapshotted order items.
3. One accepted-order outbox event.

A duplicate returns HTTP 200 and does not create additional line items or
outbox events. The database constraint, not a pre-check, is the correctness
boundary under concurrent submissions.

### Outbox processing and idempotency

The worker selects pending outbox IDs, then claims each still-pending event
with `select_for_update(skip_locked=True)` inside its own transaction. For every item it:

1. Creates a `(order, sku)` stock movement with ORM `get_or_create`.
2. Decrements the matching product using `GREATEST(stock - qty, 0)` only when
   the movement was newly inserted.
3. Marks the order `stock_reserved`.
4. Sets `processed_at` on the outbox event.

The unique stock-movement constraint makes retries safe. If a worker crashes
after applying a movement but before marking the event processed, a retry
finds the existing movement and does not decrement stock a second time.

### Stock policy

Orders are accepted without synchronous stock reservation. When demand
exceeds available stock, processing clamps the value to zero. Strict
inventory allocation, shortage records, cancellation, and refunds are outside
this assessment.

---

## Option A integration surface

`GET /feed/events?after=<id>&limit=50` exposes accepted-order events for a
small external consumer. The feed returns event IDs, event types, payloads,
processing timestamps, and a `next_cursor`. Consumers can persist the cursor
and poll again.

`scripts/consumer.py` demonstrates that contract by polling the feed and
printing new events. It is intentionally separate from the stock worker: the
worker applies internal stock effects, while the consumer represents another
system learning about accepted orders.

The feed is a lightweight take-home integration surface, not a claim of
exactly-once delivery. A production consumer would persist its cursor,
replay safely, and reconcile missed or reordered events.

---

## Verification

The focused test suite contains two tests for the required unhappy paths:

- Duplicate order references return one order and one outbox event.
- Orders accepted while the processor is stopped catch up when processing
  resumes, without applying stock twice.

Run it with:

```bash
uv run pytest -v
```

The test configuration includes `orders_stock/tests.py`, so this command
should report exactly two tests.

The API can be exercised from Postman or curl using the endpoint table in the
README, including stopping the worker, creating an order, observing pending
state, restarting the worker, and confirming stock catch-up.

---

## Known limitations and future improvements

- No authentication or authorization.
- No validation of a repeated `order_ref` with a different payload.
- No payments, cancellation, refunds, or strict inventory reservation.
- No exactly-once delivery guarantee for external consumers.
- No Kafka, Redis, Celery, Kubernetes, metrics, or horizontal orchestration.
- The single-process polling worker is intended for the assessment demo; a
  production deployment would use managed worker lifecycle and monitoring.

The central trade-off is operational simplicity: PostgreSQL is both the
durable source of truth and the coordination mechanism, while the management
command makes the asynchronous boundary easy to run and inspect.
