"""Vérifie les refus d'accès, rôles, sessions et commandes après authentification."""
import os
import time
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_commands
from security import install_security


class SecurityTests(unittest.TestCase):
    setUp = test_commands.CommandTests.setUp
    tearDown = test_commands.CommandTests.tearDown

    def test_anonymous_cannot_read_or_control(self):
        with TestClient(self.api.app) as anonymous:
            for endpoint in ("readings", "alerts", "frame", "device/state", "commands", "commands/pending"):
                self.assertEqual(anonymous.get("/api/v1/" + endpoint).status_code, 401)
            self.assertEqual(anonymous.post("/api/v1/commands", json={"action": "led_on"}).status_code, 401)
            self.assertEqual(anonymous.get("/", follow_redirects=False).status_code, 303)
            self.assertEqual(anonymous.get("/health").status_code, 200)

    def test_services_have_separate_roles(self):
        for headers in (self.bridge_headers, self.vision_headers):
            self.assertEqual(self.client.post("/api/v1/commands", headers=headers, json={"action": "led_on"}).status_code, 403)
            self.assertEqual(self.client.get("/api/v1/frame", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/commands/pending", headers=self.vision_headers).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/device/state", headers=self.vision_headers, json={"led": True, "buzzer": False}).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/frame", headers=self.bridge_headers, content=b"fake").status_code, 403)
        self.assertEqual(self.client.post("/api/v1/device/state", json={"led": True, "buzzer": False}).status_code, 403)

    def test_camera_can_send_jpeg_and_alert(self):
        headers = {**self.vision_headers, "Content-Type": "image/jpeg"}
        image = b"\xff\xd8test-image\xff\xd9"
        self.assertEqual(self.client.post("/api/v1/frame", content=image, headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/frame").content, image)
        alert = {"timestamp": "2026-10-08T10:00:00Z", "source": "webcam_pc", "type": "multiple_faces", "model": "YuNet", "face_count": 2}
        self.assertEqual(self.client.post("/api/v1/alerts", json=alert, headers=self.vision_headers).status_code, 201)
        self.assertEqual(self.client.get("/api/v1/alerts").json()[0]["face_count"], 2)
        self.assertEqual(self.client.post("/api/v1/frame", content=b"x" * (2 * 1024 * 1024 + 1), headers=headers).status_code, 413)

    def test_login_cookie_logout_revocation_and_forgery(self):
        cookie = self.client.cookies.get("sentinel_session")
        self.assertEqual(self.client.get("/api/v1/readings").status_code, 200)
        self.assertEqual(self.client.post("/auth/logout").status_code, 200)
        self.client.cookies.set("sentinel_session", cookie)
        self.assertEqual(self.client.get("/api/v1/readings").status_code, 401)
        self.client.cookies.set("sentinel_session", "forged.signature")
        self.assertEqual(self.client.get("/api/v1/readings").status_code, 401)

    def test_wrong_password_rate_limit_and_cookie_flags(self):
        response = self.client.post("/auth/login", json={"password": "test-password-123"})
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)
        for _ in range(5):
            self.assertEqual(self.client.post("/auth/login", json={"password": "incorrect"}).status_code, 401)
        self.assertEqual(self.client.post("/auth/login", json={"password": "test-password-123"}).status_code, 429)

    def test_cross_origin_requests_refused(self):
        foreign = {"Origin": "http://untrusted.example"}
        self.assertEqual(self.client.post("/auth/login", json={"password": "test-password-123"}, headers=foreign).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/commands", json={"action": "led_on"}, headers=foreign).status_code, 403)
        self.assertEqual(self.client.post("/auth/logout", headers=foreign).status_code, 403)

    def test_expired_session_and_bad_key_refused(self):
        with patch("security.time.time", return_value=time.time() + 9 * 3600):
            self.assertEqual(self.client.get("/api/v1/readings").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/readings", headers={"Authorization": "Bearer incorrect"}).status_code, 401)

    def test_no_configuration_fails_closed(self):
        with patch.dict(os.environ, {"SENTINEL_SESSION_SECRET": ""}), patch("security.load_environment"):
            with self.assertRaisesRegex(RuntimeError, "Sécurité non configurée"):
                install_security(FastAPI(), self.api.BASE_DIR)

    def test_setup_preserves_existing_settings_and_never_stores_password(self):
        import setup_security
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("MQTT_HOST=localhost\n", encoding="utf-8")
            with patch.object(setup_security, "__file__", str(Path(folder) / "setup_security.py")), \
                 patch("setup_security.getpass.getpass", side_effect=["test-password-123", "test-password-123"]), \
                 patch("builtins.print"):
                setup_security.main()
            content = path.read_text(encoding="utf-8")
            self.assertIn("MQTT_HOST=localhost", content)
            self.assertNotIn("test-password-123", content)
            values = dict(line.split("=", 1) for line in content.splitlines())
            self.assertNotEqual(values["SENTINEL_BRIDGE_KEY"], values["SENTINEL_VISION_KEY"])
            self.assertGreaterEqual(len(values["SENTINEL_SESSION_SECRET"]), 32)


if __name__ == "__main__":
    unittest.main()
