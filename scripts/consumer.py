#!/usr/bin/env python3

import argparse
import time

import httpx


def main(base_url: str, interval: float) -> None:
    cursor = 0
    print(f"Polling {base_url}/feed/events every {interval}s. Press Ctrl+C to stop.")
    with httpx.Client(base_url=base_url, timeout=10) as client:
        while True:
            response = client.get(
                "/feed/events",
                params={"after": cursor, "limit": 50},
            )
            response.raise_for_status()
            data = response.json()
            for event in data["events"]:
                print(
                    f"event_id={event['id']} "
                    f"order_ref={event['payload']['order_ref']} "
                    f"type={event['event_type']}"
                )
            cursor = data["next_cursor"]
            time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    main(args.base_url, args.interval)
