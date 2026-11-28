from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Category, Order, Product


class ShopAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Electronics", slug="electronics")
        cls.other_category = Category.objects.create(name="Books", slug="books")
        cls.cable = Product.objects.create(
            category=cls.category, name="USB-C Cable", slug="usb-cable",
            price=Decimal("9.99"), stock=50,
        )
        cls.headphones = Product.objects.create(
            category=cls.category, name="Headphones", slug="headphones",
            price=Decimal("59.00"), stock=5,
        )
        cls.webcam = Product.objects.create(
            category=cls.category, name="Webcam", slug="webcam",
            price=Decimal("45.50"), stock=0,
        )
        cls.novel = Product.objects.create(
            category=cls.other_category, name="Novel", slug="novel",
            price=Decimal("12.00"), stock=10,
        )
        cls.hidden = Product.objects.create(
            category=cls.category, name="Hidden", slug="hidden",
            price=Decimal("5.00"), stock=10, is_active=False,
        )

    def order_payload(self, items):
        return {
            "customer_name": "Test",
            "customer_email": "t@example.com",
            "items": items,
        }


class HealthTests(ShopAPITestCase):
    def test_health_ok(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")


class ProductTests(ShopAPITestCase):
    def slugs(self, **params):
        response = self.client.get(reverse("product-list"), params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {p["slug"] for p in response.data["results"]}

    def test_inactive_products_are_hidden(self):
        self.assertNotIn("hidden", self.slugs())

    def test_filter_by_category(self):
        self.assertEqual(self.slugs(category="books"), {"novel"})

    def test_filter_by_price_range(self):
        self.assertEqual(
            self.slugs(min_price="10", max_price="50"), {"webcam", "novel"}
        )

    def test_filter_in_stock(self):
        self.assertNotIn("webcam", self.slugs(in_stock="true"))

    def test_search(self):
        self.assertEqual(self.slugs(search="head"), {"headphones"})

    def test_detail(self):
        response = self.client.get(reverse("product-detail", args=[self.cable.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["category"], "electronics")

    def test_products_are_read_only(self):
        response = self.client.post(reverse("product-list"), {"name": "x"})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class OrderTests(ShopAPITestCase):
    def post_order(self, items):
        return self.client.post(
            reverse("order-list"), self.order_payload(items), format="json"
        )

    def test_create_order_snapshots_price_and_reduces_stock(self):
        response = self.post_order([{"product": self.cable.pk, "quantity": 2}])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total"], "19.98")
        self.assertEqual(response.data["status"], "pending")
        self.cable.refresh_from_db()
        self.assertEqual(self.cable.stock, 48)

    def test_client_cannot_set_price(self):
        response = self.post_order(
            [{"product": self.cable.pk, "quantity": 1, "unit_price": "0.01"}]
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["items"][0]["unit_price"], "9.99")

    def test_later_price_change_does_not_alter_old_order(self):
        self.post_order([{"product": self.cable.pk, "quantity": 1}])
        self.cable.price = Decimal("99.00")
        self.cable.save()
        self.assertEqual(Order.objects.get().total, Decimal("9.99"))

    def test_insufficient_stock_is_rejected_and_rolled_back(self):
        response = self.post_order([{"product": self.headphones.pk, "quantity": 99}])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)
        self.headphones.refresh_from_db()
        self.assertEqual(self.headphones.stock, 5)

    def test_one_bad_item_rolls_back_the_whole_order(self):
        response = self.post_order([
            {"product": self.cable.pk, "quantity": 1},
            {"product": self.headphones.pk, "quantity": 99},
        ])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)
        self.cable.refresh_from_db()
        self.assertEqual(self.cable.stock, 50)

    def test_empty_order_rejected(self):
        self.assertEqual(self.post_order([]).status_code, 400)

    def test_duplicate_product_rejected(self):
        response = self.post_order([
            {"product": self.cable.pk, "quantity": 1},
            {"product": self.cable.pk, "quantity": 1},
        ])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_quantity_rejected(self):
        response = self.post_order([{"product": self.cable.pk, "quantity": 0}])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_product_rejected(self):
        response = self.post_order([{"product": self.hidden.pk, "quantity": 1}])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_orders_cannot_be_listed(self):
        response = self.client.get(reverse("order-list"))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
