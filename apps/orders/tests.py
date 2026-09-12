"""Tests for order creation flow (UUID vs str comparison fix)."""
from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.customers.models import Customer
from apps.products.models import Product


class OrderCreationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="orders@example.com", username="orders", password="pass123"
        )
        self.workspace = Workspace.objects.create(name="Order WS", slug="order-ws", owner=self.user)
        WorkspaceMembership.objects.create(user=self.user, workspace=self.workspace, role="owner")
        self.customer = Customer.objects.create(workspace=self.workspace, name="Order Customer")
        self.product = Product.objects.create(
            workspace=self.workspace, name="Test Product", sku="TEST001", price="1500.00"
        )

    def test_create_order_with_valid_workspace(self):
        """Order creation should succeed when workspace_id matches user's workspace."""
        self.client.force_authenticate(user=self.user)
        resp = self.client.post("/api/orders/", {
            "workspace_id": str(self.workspace.id),
            "customer_id": str(self.customer.id),
            "items": [
                {"product_id": str(self.product.id), "quantity": 2}
            ],
            "payment_method": "cod",
        }, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_create_order_with_invalid_workspace(self):
        """Order creation should fail when workspace_id doesn't match user's workspace."""
        from uuid import uuid4
        self.client.force_authenticate(user=self.user)
        resp = self.client.post("/api/orders/", {
            "workspace_id": str(uuid4()),  # Random UUID not in user's workspaces
            "customer_id": str(self.customer.id),
            "items": [{"product_id": str(self.product.id), "quantity": 1}],
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_create_order_nonexistent_customer(self):
        """Order creation should fail with 404 for nonexistent customer."""
        from uuid import uuid4
        self.client.force_authenticate(user=self.user)
        resp = self.client.post("/api/orders/", {
            "workspace_id": str(self.workspace.id),
            "customer_id": str(uuid4()),  # Nonexistent customer
            "items": [{"product_id": str(self.product.id), "quantity": 1}],
        }, format="json")
        self.assertEqual(resp.status_code, 404)
