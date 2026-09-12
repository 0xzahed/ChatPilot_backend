"""Tests for workspace isolation and authorization."""
from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.workspaces.models import Workspace, WorkspaceMembership


class WorkspaceIsolationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Two users, two workspaces
        self.user_a = User.objects.create_user(
            email="a@example.com", username="usera", password="pass123"
        )
        self.user_b = User.objects.create_user(
            email="b@example.com", username="userb", password="pass123"
        )
        self.ws_a = Workspace.objects.create(name="Workspace A", slug="ws-a", owner=self.user_a)
        self.ws_b = Workspace.objects.create(name="Workspace B", slug="ws-b", owner=self.user_b)
        WorkspaceMembership.objects.create(user=self.user_a, workspace=self.ws_a, role="owner")
        WorkspaceMembership.objects.create(user=self.user_b, workspace=self.ws_b, role="owner")

    def test_user_a_cannot_access_ws_b_conversations(self):
        """User A should not see conversations from Workspace B."""
        from apps.inbox.models import Conversation
        from apps.customers.models import Customer

        customer_b = Customer.objects.create(workspace=self.ws_b, name="Customer B")
        Conversation.objects.create(
            workspace=self.ws_b, customer=customer_b, channel="website", status="open"
        )

        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get(f"/api/conversations/?workspace_id={self.ws_b.id}")
        # The view filters by get_user_workspaces, so ws_b should not be included
        body = resp.json()
        if body.get("success"):
            # If it returns data, it should not contain ws_b's conversation
            data = body.get("data", [])
            if isinstance(data, list):
                for conv in data:
                    self.assertNotEqual(conv.get("workspace"), str(self.ws_b.id))

    def test_user_a_cannot_access_ws_b_customers(self):
        """User A should not see customers from Workspace B."""
        from apps.customers.models import Customer

        Customer.objects.create(workspace=self.ws_b, name="Secret Customer")

        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get("/api/customers/")
        body = resp.json()
        if body.get("success") and isinstance(body.get("data"), list):
            for cust in body["data"]:
                self.assertNotEqual(cust.get("name"), "Secret Customer")


class TeamAuthorizationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            email="owner@example.com", username="owner", password="pass123"
        )
        self.agent = User.objects.create_user(
            email="agent@example.com", username="agent", password="pass123"
        )
        self.workspace = Workspace.objects.create(name="Test WS", slug="test-ws", owner=self.owner)
        WorkspaceMembership.objects.create(user=self.owner, workspace=self.workspace, role="owner")
        WorkspaceMembership.objects.create(user=self.agent, workspace=self.workspace, role="agent")

    def test_agent_cannot_invite_members(self):
        """Non-admin/owner should be forbidden from inviting members."""
        self.client.force_authenticate(user=self.agent)
        resp = self.client.post("/api/team/invite/", {
            "workspace_id": str(self.workspace.id),
            "email": "new@example.com",
            "role": "agent",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_invite_members(self):
        """Owner should be able to invite members."""
        # Create the target user first
        User.objects.create_user(email="new@example.com", username="new", password="pass123")
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post("/api/team/invite/", {
            "workspace_id": str(self.workspace.id),
            "email": "new@example.com",
            "role": "agent",
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))

    def test_agent_cannot_change_roles(self):
        """Non-admin should be forbidden from changing member roles."""
        membership = WorkspaceMembership.objects.get(user=self.agent, workspace=self.workspace)
        self.client.force_authenticate(user=self.agent)
        resp = self.client.patch(f"/api/team/{membership.id}/", {"role": "admin"}, format="json")
        self.assertEqual(resp.status_code, 403)
