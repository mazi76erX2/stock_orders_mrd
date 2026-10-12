# Orders & Stock

A minimal orders and stock service built with Django and PostgreSQL. Orders are
accepted through a small HTTP API, persisted through the Django ORM except for
the atomic PostgreSQL idempotency insert, and handed to an asynchronous
transactional outbox processor. The project implements Option A from the
assessment: a cursor-based feed that another system can poll for accepted-order
events.

---

## Requirements

- Python 3.12+
- uv
- PostgreSQL 14+
- Docker and Docker Compose (optional)

The application uses Django 6.1, Django REST Framework, `psycopg`, `httpx`,
and pytest. The ORM is the default for CRUD and relationships. Raw SQL is
limited to `INSERT ... ON CONFLICT ... RETURNING`, where it makes the
concurrent duplicate decision explicit.

---

## Quick Start

### 1. Create the database

For a local PostgreSQL installation:

```bash
createdb orders_stock_django
```

Configure the usual Django database environment variables if your local
PostgreSQL credentials differ from the defaults.

### 2. Install dependencies and migrate

```bash
uv sync --extra dev
uv run python manage.py migrate
```

### 3. Start the API

```bash
uv run python manage.py runserver 8000
```

The API is available at **http://localhost:8000**.

### 4. Start the stock processor

In a second terminal:

```bash
uv run python manage.py process_outbox_loop
```

The processor polls pending outbox events. For one batch only:

```bash
uv run python manage.py process_outbox_loop --run-once
```

### Docker

Docker starts PostgreSQL and the web application. The worker remains a
separate process so the outage and catch-up behavior is visible:

```bash
docker compose up --build
docker compose run --rm web python manage.py process_outbox_loop
```

---

## Demo

Seed products and submit a burst of orders, including duplicate references:

```bash
uv run python -m scripts.seed_and_demo
```

To demonstrate catch-up, leave the worker stopped, submit orders, inspect the
pending events, then restart the worker:

```bash
uv run python -m scripts.seed_and_demo --outage
uv run python manage.py process_outbox_loop --run-once
```

The API accepts orders while the worker is unavailable. The worker later
processes the outbox backlog, decrements stock, and changes the order status
to `stock_reserved`.

The Option A consumer is a small polling example:

```bash
uv run python -m scripts.consumer
```

---

## Running the tests

```bash
uv run pytest -v
```

---

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/products/seed` | Insert or update demo products |
| GET | `/products` | List products and current stock |
| POST | `/orders` | Create an idempotent order |
| GET | `/orders/{order_ref}` | Read order details and processing status |
| GET | `/feed/events` | Poll accepted-order events with a cursor |

---

## Project Structure

```text
stock_orders_mrd/
├── config/
│   ├── settings.py                 # Django and PostgreSQL configuration
│   └── urls.py                     # Root URL configuration
├── orders_stock/
│   ├── models.py                   # Schema definitions and constraints
│   ├── views.py                    # ORM API plus atomic order insert
│   ├── processing.py               # ORM transactional-outbox processor
│   ├── serializers.py              # Request and response validation
│   ├── urls.py                     # Orders, products, and feed routes
│   ├── migrations/                 # PostgreSQL schema and indexes
│   ├── tests.py                    # Two required unhappy-path tests
│   └── management/commands/
│       └── process_outbox_loop.py  # Polling worker entry point
├── scripts/
│   ├── seed_and_demo.py            # Duplicate and outage demonstration
│   └── consumer.py                 # Option A feed consumer
├── docker-compose.yml
├── pyproject.toml
├── README.md
└── SOLUTION.md
```

## Postman

Import `stock_orders.postman_collection.json` into Postman. The collection
covers product seeding, duplicate orders, order status, stock, the Option A
feed, and the worker outage/catch-up sequence. The worker is intentionally
started separately so it can be stopped during the outage demonstration.

The system deliberately excludes authentication, payments, strict inventory
reservation, Kafka, Redis, Celery, Kubernetes, and horizontal worker
orchestration. Those are production concerns outside this focused assessment.
