import time

from django.core.management.base import BaseCommand

from orders_stock.processing import process_outbox_batch


class Command(BaseCommand):
    help = "Process pending stock outbox events in a polling loop."

    def add_arguments(self, parser):
        parser.add_argument("--poll-interval", type=float, default=1.0)
        parser.add_argument("--batch-size", type=int, default=20)
        parser.add_argument("--run-once", action="store_true")

    def handle(self, *args, **options):
        poll_interval = options["poll_interval"]
        batch_size = options["batch_size"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Processing outbox events (batch_size={batch_size}, "
                f"poll_interval={poll_interval}s)"
            )
        )

        try:
            while True:
                processed = process_outbox_batch(batch_size=batch_size)
                if processed:
                    self.stdout.write(f"Processed {processed} outbox event(s).")
                if options["run_once"]:
                    return
                if not processed:
                    time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stdout.write("\nOutbox processor stopped.")
