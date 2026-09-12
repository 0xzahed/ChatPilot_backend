"""Tests for authentication flows: register, login, session tracking."""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from .models import User, Session


class RegisterViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_user_and_session(self):
        """Registration should create a user, return tokens, and create a Session record."""
        resp = self.client.post("/api/auth/register/", {
            "email": "test@example.com",
            "username": "testuser",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "first_name": "Test",
            "last_name": "User",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertIn("access", body["data"])
        self.assertIn("refresh", body["data"])
        self.assertEqual(body["data"]["user"]["email"], "test@example.com")
        # Session should be created
        self.assertTrue(Session.objects.filter(user__email="test@example.com").exists())

    def test_register_duplicate_email_fails(self):
        User.objects.create_user(email="dup@example.com", username="dup", password="pass123")
        resp = self.client.post("/api/auth/register/", {
            "email": "dup@example.com",
            "username": "dup2",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }, format="json")
        self.assertNotEqual(resp.status_code, 201)


class LoginViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="login@example.com", username="loginuser", password="pass123"
        )

    def test_login_returns_tokens(self):
        resp = self.client.post("/api/auth/login/", {
            "email": "login@example.com",
            "password": "pass123",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertIn("access", body["data"])
        self.assertIn("refresh", body["data"])

    def test_login_wrong_password(self):
        resp = self.client.post("/api/auth/login/", {
            "email": "login@example.com",
            "password": "wrong",
        }, format="json")
        self.assertNotEqual(resp.status_code, 200)


class MeViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="me@example.com", username="meuser", password="pass123"
        )

    def test_me_requires_auth(self):
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 401)

    def test_me_returns_user(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["email"], "me@example.com")
