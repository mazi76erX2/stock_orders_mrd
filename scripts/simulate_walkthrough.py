#!/usr/bin/env python3

import argparse
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PRODUCTS = [
    {"sku": "SIM-BAN", "name": "Simulation Bananas", "price_cents": 199, "stock": 20},
    {"sku": "SIM-MILK", "name": "Simulation Milk", "price_cents": 299, "stock": 20},
]


def log(started: float, message: str) -> None:
    print(f"[{time.monotonic() - started:6.2f}s] {message}", flush=True)


def product_stock(client: httpx.Client, sku: str) -> int:
    response = client.get("/products")
    response.raise_for_status()
    for product in response.json():
        if product["sku"] == sku:
            return product["stock"]
    raise RuntimeError(f"Product {sku} was not returned by /products")


def order_status(client: httpx.Client, order_ref: str) -> str:
    response = client.get(f"/orders/{order_ref}")
    response.raise_for_status()
    return response.json()["status"]


def wait_for_status(
    client: httpx.Client,
    order_ref: str,
    expected: str,
    timeout: float,
    started: float,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = order_status(client, order_ref)
        if current == expected:
            log(started, f"{order_ref}: status is {expected}")
            return
        time.sleep(0.2)
    raise TimeoutError(
        f"{order_ref} did not reach {expected!r} within {timeout:.1f}s "
        f"(last status: {current!r})"
    )


def create_order(client: httpx.Client, order_ref: str, qty: int) -> httpx.Response:
    response = client.post(
        "/orders",
        json={
            "order_ref": order_ref,
            "customer_id": "walkthrough-simulator",
            "items": [{"sku": "SIM-MILK", "qty": qty}],
        },
    )
    response.raise_for_status()
    return response


@contextmanager
def worker(started: float):
    process = subprocess.Popen(
        [
            sys.executable,
            "manage.py",
            "process_outbox_loop",
            "--poll-interval",
            "0.2",
        ],
        cwd=ROOT,
    )
    log(started, "Worker started")
    try:
        yield process
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        log(started, "Worker stopped")


def pause(seconds: float) -> None:
    if seconds:
        time.sleep(seconds)


def main(base_url: str, pause_seconds: float, timeout: float) -> None:
    started = time.monotonic()
    suffix = str(int(time.time()))
    normal_ref = f"walkthrough-normal-{suffix}"
    outage_ref = f"walkthrough-outage-{suffix}"

    with httpx.Client(base_url=base_url, timeout=10) as client:
        client.get("/products").raise_for_status()
        log(started, f"API reachable at {base_url}")

        response = client.post("/products/seed", json=PRODUCTS)
        response.raise_for_status()
        log(started, "Seeded two simulation products")
        pause(pause_seconds)

        feed = client.get("/feed/events", params={"after": 0, "limit": 500})
        feed.raise_for_status()
        cursor = feed.json()["next_cursor"]

        with worker(started):
            normal_before = product_stock(client, "SIM-MILK")
            response = create_order(client, normal_ref, 2)
            if response.status_code != 201 or response.json()["duplicate"]:
                raise RuntimeError("Expected the first normal order to return 201")
            log(started, f"Created {normal_ref}: accepted")

            duplicate = create_order(client, normal_ref, 2)
            if duplicate.status_code != 200 or not duplicate.json()["duplicate"]:
                raise RuntimeError("Expected the repeated order reference to be a duplicate")
            log(started, f"Repeated {normal_ref}: duplicate returned without a new order")
            wait_for_status(client, normal_ref, "stock_reserved", timeout, started)

            normal_after = product_stock(client, "SIM-MILK")
            if normal_after != normal_before - 2:
                raise RuntimeError(
                    f"Normal order changed stock from {normal_before} to {normal_after}"
                )
            log(started, f"Normal processing changed SIM-MILK stock to {normal_after}")
            pause(pause_seconds)

        with worker(started) as running_worker:
            running_worker.send_signal(signal.SIGINT)
            running_worker.wait(timeout=5)
            outage_before = product_stock(client, "SIM-MILK")
            response = create_order(client, outage_ref, 3)
            if response.status_code != 201:
                raise RuntimeError("Expected the outage order to return 201")
            if order_status(client, outage_ref) != "accepted":
                raise RuntimeError("Outage order was processed before the worker stopped")
            if product_stock(client, "SIM-MILK") != outage_before:
                raise RuntimeError("Stock changed while the worker was stopped")
            log(started, f"Worker stopped; {outage_ref} is accepted and stock is unchanged")

            pending = client.get("/feed/events", params={"after": cursor, "limit": 500})
            pending.raise_for_status()
            outage_events = [
                event
                for event in pending.json()["events"]
                if event["payload"]["order_ref"] == outage_ref
            ]
            if len(outage_events) != 1 or outage_events[0]["processed_at"] is not None:
                raise RuntimeError("Outage event was not pending in the feed")
            log(started, "Outage event is visible as pending in the feed")

        with worker(started):
            wait_for_status(client, outage_ref, "stock_reserved", timeout, started)
            outage_after = product_stock(client, "SIM-MILK")
            if outage_after != outage_before - 3:
                raise RuntimeError(
                    f"Catch-up changed stock from {outage_before} to {outage_after}"
                )
            log(started, f"Worker catch-up changed SIM-MILK stock to {outage_after}")

    log(started, "Walkthrough simulation passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate the manual project walkthrough.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--pause", type=float, default=0.5, help="Seconds between visible steps.")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    main(args.base_url, args.pause, args.timeout)
