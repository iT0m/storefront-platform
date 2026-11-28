from django.db import transaction
from rest_framework import serializers

from .models import Category, Order, OrderItem, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "description", "price",
            "stock", "image", "category", "created_at",
        ]


class OrderItemSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )

    class Meta:
        model = OrderItem
        fields = ["product", "quantity", "unit_price"]
        read_only_fields = ["unit_price"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "customer_name", "customer_email",
            "status", "items", "total", "created_at",
        ]
        read_only_fields = ["status", "created_at"]

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("An order needs at least one item.")
        ids = [item["product"].id for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each product may appear only once.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")
        products = Product.objects.select_for_update().in_bulk(
            [item["product"].id for item in items_data]
        )
        order = Order.objects.create(**validated_data)
        for item in items_data:
            product = products[item["product"].id]
            quantity = item["quantity"]
            if product.stock < quantity:
                raise serializers.ValidationError(
                    {"items": f"Not enough stock for '{product.name}' "
                              f"(available: {product.stock})."}
                )
            product.stock -= quantity
            product.save(update_fields=["stock", "updated_at"])
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                unit_price=product.price,
            )
        return order
