#!/usr/bin/env python3

import argparse
import time

import httpx

BASE = "http://localhost:8000"

PRODUCTS = [
    {"sku": "BAN-001", "name": "Bananas 1kg", "price_cents": 199, "stock": 50},
    {"sku": "APL-003", "name": "Apples 1kg", "price_cents": 349, "stock": 30},
    {"sku": "MLK-010", "name": "Full Cream Milk 1L", "price_cents": 2199, "stock": 100},
    {"sku": "BRD-007", "name": "Brown Bread Loaf", "price_cents": 1499, "stock": 40},
    {"sku": "EGG-006", "name": "Free Range Eggs 6s", "price_cents": 4599, "stock": 25},
]

ORDERS = [
    {
        "order_ref": "web-100045",
        "customer_id": "cust-42",
        "items": [{"sku": "BAN-001", "qty": 2}, {"sku": "APL-003", "qty": 1}],
    },
    {
        "order_ref": "web-100046",
        "customer_id": "cust-17",
        "items": [{"sku": "MLK-010", "qty": 3}],
    },
    {
        "order_ref": "web-100047",
        "customer_id": "cust-42",
        "items": [{"sku": "BRD-007", "qty": 1}, {"sku": "EGG-006", "qty": 2}],
    },
    {
        "order_ref": "web-100045",
        "customer_id": "cust-42",
        "items": [{"sku": "BAN-001", "qty": 2}, {"sku": "APL-003", "qty": 1}],
    },
    {
        "order_ref": "web-100048",
        "customer_id": "cust-55",
        "items": [{"sku": "BAN-001", "qty": 5}],
    },
    {
        "order_ref": "web-100047",
        "customer_id": "cust-42",
        "items": [{"sku": "BRD-007", "qty": 1}, {"sku": "EGG-006", "qty": 2}],
    },
]


def _header(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def main(base_url: str):
    with httpx.Client(base_url=base_url, timeout=10) as client:
        _header("Seeding products")
        r = client.post("/products/seed", json=PRODUCTS)
        print(f"Seed response: {r.status_code} {r.json()}")

        r = client.get("/products")
        for p in r.json():
            print(f"  {p['sku']:10s}  {p['name']:25s}  stock={p['stock']}")

        _header("Submitting orders (including duplicates)")
        duplicate_results = []
        first_created = False
        for o in ORDERS:
            r = client.post("/orders", json=o)
            data = r.json()
            duplicate_results.append(data.get("duplicate", False))
            if not data.get("duplicate") and not first_created:
                first_created = r.status_code == 201
            duplicate = " (duplicate)" if data.get("duplicate") else ""
            print(
                f"  [{r.status_code}] order_ref={data['order_ref']} "
                f"status={data['status']} total={data['total_cents']}c{duplicate}"
            )

        assert first_created
        print("  First submission returned 201.")
        assert duplicate_results.count(True) == 2
        print("  Two repeated references returned the existing orders.")

        time.sleep(2)

        _header("Stock after normal orders")
        r = client.get("/products")
        for p in r.json():
            print(f"  {p['sku']:10s}  stock={p['stock']}")
        print("  Stock was read after the order submissions.")

        _header("Event feed (Option A)")
        r = client.get("/feed/events", params={"after": 0, "limit": 20})
        feed = r.json()
        for ev in feed["events"]:
            state = "processed" if ev["processed_at"] else "pending"
            print(
                f"  event_id={ev['id']} type={ev['event_type']} "
                f"order_ref={ev['payload']['order_ref']} state={state}"
            )
        print(f"\n  next_cursor={feed['next_cursor']}")
        pending = [ev for ev in feed["events"] if ev["processed_at"] is None]
        print(f"  pending_outbox_events={len(pending)}")
        print(f"  Feed returned {len(feed['events'])} event(s); {len(pending)} remain pending.")

        order = client.get("/orders/web-100045")
        order.raise_for_status()
        print(f"  final_order_status={order.json()['status']}")

        _header("Demo complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE)
    parser.add_argument(
        "--outage",
        action="store_true",
        help="Submit orders without running the processor and show pending events.",
    )
    args = parser.parse_args()
    if args.outage:
        print("Running outage mode: submit orders before starting the processor.")
    main(args.base_url)
