"""API views using Django ORM with one PostgreSQL-specific insert."""

from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order, OrderItem, Outbox, Product
from .serializers import (
    CreateOrderRequestSerializer,
    OrderDetailSerializer,
    OutboxEventSerializer,
    ProductSerializer,
)


class ProductListView(APIView):
    def get(self, request):
        products = Product.objects.all().order_by("sku")
        return Response(ProductSerializer(products, many=True).data)


class ProductSeedView(APIView):
    """Bulk upsert products for seeding/demo."""

    def post(self, request):
        data = request.data
        if not isinstance(data, list):
            return Response(
                {"error": "Expected a list of products"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            for item in data:
                Product.objects.update_or_create(
                    sku=item["sku"],
                    defaults={
                        "name": item["name"],
                        "price_cents": item["price_cents"],
                        "stock": item.get("stock", 0),
                    },
                )
        return Response({"upserted": len(data)})


class CreateOrderView(APIView):
    """Create an order and its outbox event in one transaction."""

    def post(self, request):
        serializer = CreateOrderRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        data = serializer.validated_data
        order_ref = data["order_ref"]
        customer_id = data["customer_id"]
        merged_items: dict[str, int] = {}
        for item in data["items"]:
            merged_items[item["sku"]] = merged_items.get(item["sku"], 0) + item["qty"]
        normalized_items = [{"sku": sku, "qty": qty} for sku, qty in merged_items.items()]

        existing = Order.objects.filter(order_ref=order_ref).first()
        if existing:
            return Response(
                {
                    "order_ref": existing.order_ref,
                    "status": existing.status,
                    "total_cents": existing.total_cents,
                    "duplicate": True,
                }
            )

        products = {
            product.sku: product for product in Product.objects.filter(sku__in=merged_items)
        }
        missing = sorted(set(merged_items) - set(products))
        if missing:
            return Response(
                {"detail": f"Unknown SKU(s): {', '.join(missing)}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        total_cents = sum(
            products[item["sku"]].price_cents * item["qty"] for item in normalized_items
        )

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO orders
                        (order_ref, customer_id, total_cents, status, created_at)
                    VALUES (%s, %s, %s, 'accepted', NOW())
                    ON CONFLICT (order_ref) DO NOTHING
                    RETURNING id
                    """,
                    [order_ref, customer_id, total_cents],
                )
                inserted = cursor.fetchone()

            if inserted is None:
                existing = Order.objects.get(order_ref=order_ref)
                return Response(
                    {
                        "order_ref": existing.order_ref,
                        "status": existing.status,
                        "total_cents": existing.total_cents,
                        "duplicate": True,
                    }
                )

            order_id = inserted[0]
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order_id=order_id,
                        sku=item["sku"],
                        qty=item["qty"],
                        unit_price_cents=products[item["sku"]].price_cents,
                    )
                    for item in normalized_items
                ]
            )
            Outbox.objects.create(
                order_id=order_id,
                event_type="order_accepted",
                payload={
                    "order_ref": order_ref,
                    "customer_id": customer_id,
                    "items": [
                        {
                            **item,
                            "unit_price_cents": products[item["sku"]].price_cents,
                        }
                        for item in normalized_items
                    ],
                    "total_cents": total_cents,
                },
            )

        return Response(
            {
                "order_ref": order_ref,
                "status": "accepted",
                "total_cents": total_cents,
                "duplicate": False,
            },
            status=status.HTTP_201_CREATED,
        )


class OrderDetailView(APIView):
    def get(self, request, order_ref):
        order = get_object_or_404(
            Order.objects.prefetch_related("items"), order_ref=order_ref
        )
        return Response(OrderDetailSerializer(order).data)


class EventFeedView(APIView):
    """Option A integration surface: cursor-based event feed."""

    def get(self, request):
        try:
            after_id = int(request.query_params.get("after", 0))
            limit = min(int(request.query_params.get("limit", 50)), 500)
        except (TypeError, ValueError):
            return Response(
                {"detail": "after and limit must be integers"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if after_id < 0 or limit < 1:
            return Response(
                {"detail": "after must be non-negative and limit must be positive"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        events = list(Outbox.objects.filter(id__gt=after_id).order_by("id")[:limit])
        return Response(
            {
                "events": OutboxEventSerializer(events, many=True).data,
                "next_cursor": events[-1].id if events else after_id,
            }
        )
