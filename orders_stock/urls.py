from django.urls import path

from .views import (
    CreateOrderView,
    EventFeedView,
    OrderDetailView,
    ProductListView,
    ProductSeedView,
)

urlpatterns = [
    path("products", ProductListView.as_view(), name="product-list"),
    path("products/seed", ProductSeedView.as_view(), name="product-seed"),
    path("orders", CreateOrderView.as_view(), name="order-create"),
    path("orders/<str:order_ref>", OrderDetailView.as_view(), name="order-detail"),
    path("feed/events", EventFeedView.as_view(), name="feed-events"),
]
