from django.db import models


class Product(models.Model):
    sku = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    price_cents = models.PositiveIntegerField()
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "products"
        ordering = ["sku"]

    def __str__(self):
        return f"{self.sku}"


class Order(models.Model):
    order_ref = models.CharField(max_length=128, unique=True, db_index=True)
    customer_id = models.CharField(max_length=128)
    total_cents = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=32, default="accepted")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "orders"
        ordering = ["-id"]

    def __str__(self):
        return f"Order {self.order_ref} ({self.status}) - {self.total_cents}c"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    sku = models.CharField(max_length=64)
    qty = models.PositiveIntegerField()
    unit_price_cents = models.PositiveIntegerField()

    class Meta:
        db_table = "order_items"
        indexes = [
            models.Index(fields=["order"]),
        ]

    def __str__(self):
        return f"{self.sku} x {self.qty} @ {self.unit_price_cents}c"


class Outbox(models.Model):
    """
    Outbox table for event-driven architecture.
    Used to store events that need to be processed.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=64, default="order_accepted")
    payload = models.JSONField()
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "outbox"
        ordering = ["id"]
        indexes = [
            models.Index(fields=["id", "processed_at"]),
        ]

    def __str__(self):
        status = "processed" if self.processed_at else "pending"
        return f"Outbox #{self.id} [{self.event_type}] ({status})"


class StockMovement(models.Model):
    """
    Audit log and idempotency guard for stock decrements.
    This table is used to track stock movements for orders.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    sku = models.CharField(max_length=64)
    qty = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movements"
        constraints = [
            # Prevent duplicate stock movements for the same order and SKU
            models.UniqueConstraint(
                fields=["order", "sku"], name="uq_django_stock_movements_order_sku"
            ),
        ]

    def __str__(self):
        return f"Movement: Order {self.order_id} - {self.sku} -{self.qty}"
