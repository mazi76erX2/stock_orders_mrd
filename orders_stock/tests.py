# Create your tests here.
"""Django test suite using pytest and Django test client."""

import pytest
from django.db import connection
from rest_framework.test import APIClient

from orders_stock.processing import process_outbox_batch


def _count(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


@pytest.fixture(autouse=True)
def clean_database():
    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE stock_movements, order_items, outbox, orders, products RESTART IDENTITY CASCADE"
        )
    yield
    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE stock_movements, order_items, outbox, orders, products RESTART IDENTITY CASCADE"
        )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_products():
    return [
        {"sku": "BAN-001", "name": "Bananas 1kg", "price_cents": 200, "stock": 50},
        {"sku": "APL-003", "name": "Apples 1kg", "price_cents": 350, "stock": 30},
        {"sku": "MLK-010", "name": "Milk 1L", "price_cents": 2200, "stock": 10},
    ]


@pytest.mark.django_db(transaction=True)
def test_duplicate_order_idempotency(api_client, sample_products):
    """Unhappy Path 1: Duplicate order submission returns existing order with HTTP 200."""
    api_client.post("/products/seed", sample_products, format="json")

    order_payload = {
        "order_ref": "dup-order-100",
        "customer_id": "cust-123",
        "items": [{"sku": "BAN-001", "qty": 3}],
    }

    resp1 = api_client.post("/orders", order_payload, format="json")
    assert resp1.status_code == 201
    assert resp1.data["duplicate"] is False

    resp2 = api_client.post("/orders", order_payload, format="json")
    assert resp2.status_code == 200
    assert resp2.data["duplicate"] is True
    assert resp2.data["order_ref"] == "dup-order-100"
    assert resp2.data["total_cents"] == 600

    assert _count("SELECT COUNT(*) FROM orders WHERE order_ref = %s", ("dup-order-100",)) == 1
    assert (
        _count(
            "SELECT COUNT(*) FROM outbox o JOIN orders r ON r.id = o.order_id WHERE r.order_ref = %s",
            ("dup-order-100",),
        )
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_outbox_catchup_after_processor_outage(api_client, sample_products):
    """Orders remain accepted while the separately run processor is stopped."""
    api_client.post("/products/seed", sample_products, format="json")
    response = api_client.post(
        "/orders",
        {
            "order_ref": "outage-order",
            "customer_id": "cust-outage",
            "items": [{"sku": "MLK-010", "qty": 4}],
        },
        format="json",
    )
    assert response.status_code == 201

    before = next(
        product for product in api_client.get("/products").data if product["sku"] == "MLK-010"
    )
    assert before["stock"] == 10
    assert _count("SELECT COUNT(*) FROM outbox WHERE processed_at IS NULL") == 1

    assert process_outbox_batch() == 1

    after = next(
        product for product in api_client.get("/products").data if product["sku"] == "MLK-010"
    )
    assert after["stock"] == 6
    order = api_client.get("/orders/outage-order")
    assert order.data["status"] == "stock_reserved"
    assert process_outbox_batch() == 0
