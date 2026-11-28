from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("products", views.ProductViewSet, basename="product")
router.register("categories", views.CategoryViewSet, basename="category")
router.register("orders", views.OrderViewSet, basename="order")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", include(router.urls)),
]
