from rest_framework import serializers


class ProductSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    price_cents = serializers.IntegerField()
    stock = serializers.IntegerField()


class OrderItemInputSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=64)
    qty = serializers.IntegerField(min_value=1)


class CreateOrderRequestSerializer(serializers.Serializer):
    order_ref = serializers.CharField(max_length=128)
    customer_id = serializers.CharField(max_length=128)
    items = OrderItemInputSerializer(many=True, allow_empty=False)


class OrderItemDetailSerializer(serializers.Serializer):
    sku = serializers.CharField()
    qty = serializers.IntegerField()
    unit_price_cents = serializers.IntegerField()


class OrderDetailSerializer(serializers.Serializer):
    order_ref = serializers.CharField()
    customer_id = serializers.CharField()
    total_cents = serializers.IntegerField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    items = OrderItemDetailSerializer(many=True)


class OutboxEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    order_id = serializers.IntegerField()
    event_type = serializers.CharField()
    payload = serializers.JSONField()
    processed_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
