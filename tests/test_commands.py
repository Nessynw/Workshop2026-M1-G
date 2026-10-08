"""Tests API isolés : aucune écriture dans la base du projet."""
import importlib.util
import shutil
import sqlite3
import tempfile
import unittest
import json
import threading
import time
from types import SimpleNamespace
from contextlib import closing
from pathlib import Path
from fastapi.testclient import TestClient


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        source = Path(__file__).resolve().parents[1] / "api.py"
        target = Path(self.tmp.name) / "api.py"
        shutil.copyfile(source, target)
        spec = importlib.util.spec_from_file_location("isolated_api", target)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)
        self.client = TestClient(self.api.app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def online(self):
        response = self.client.post("/api/v1/device/state", json={
            "led": False, "buzzer": False, "data_mode": "sensors", "oled": True
        })
        self.assertEqual(response.status_code, 200)

    def command(self):
        self.online()
        response = self.client.post("/api/v1/commands", json={"action": "led_on"})
        self.assertEqual(response.status_code, 202)
        return response.json()["id"]

    def test_offline_device_refuses_command(self):
        self.assertEqual(self.client.post("/api/v1/commands", json={"action": "led_on"}).status_code, 503)

    def test_queue_then_confirmation(self):
        identifier = self.command()
        self.assertEqual(self.client.get("/api/v1/commands/pending").json()[0]["id"], identifier)
        endpoint = f"/api/v1/commands/{identifier}/result"
        self.client.post(endpoint, json={"status": "sent"})
        self.assertEqual(self.client.get("/api/v1/commands/pending").json(), [])
        self.client.post(endpoint, json={"status": "executed"})
        self.assertEqual(self.client.get("/api/v1/commands").json()[0]["status"], "executed")

    def test_confirmation_cannot_be_downgraded(self):
        identifier = self.command()
        endpoint = f"/api/v1/commands/{identifier}/result"
        self.client.post(endpoint, json={"status": "executed"})
        self.client.post(endpoint, json={"status": "sent"})
        self.assertEqual(self.client.get("/api/v1/commands").json()[0]["status"], "executed")

    def test_expired_command_not_published(self):
        identifier = self.command()
        with closing(sqlite3.connect(self.api.DATABASE)) as db:
            db.execute("UPDATE commands SET expires_at=0 WHERE id=?", (identifier,))
            db.commit()
        self.assertEqual(self.client.get("/api/v1/commands/pending").json(), [])
        self.assertEqual(self.client.get("/api/v1/commands").json()[0]["status"], "expired")

    def test_stale_heartbeat_disables_commands(self):
        self.online()
        with closing(sqlite3.connect(self.api.DATABASE)) as db:
            db.execute("UPDATE device_state SET received_at=0")
            db.commit()
        self.assertFalse(self.client.get("/api/v1/device/state").json()["online"])
        self.assertEqual(self.client.post("/api/v1/commands", json={"action": "led_on"}).status_code, 503)

    def test_unknown_action_and_missing_command(self):
        self.online()
        self.assertEqual(self.client.post("/api/v1/commands", json={"action": "invalid"}).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/commands/missing/result", json={"status": "sent"}).status_code, 404)

    def test_pending_queue_bounded(self):
        self.online()
        for _ in range(10):
            self.assertEqual(self.client.post("/api/v1/commands", json={"action": "buzzer_on"}).status_code, 202)
        self.assertEqual(self.client.post("/api/v1/commands", json={"action": "buzzer_on"}).status_code, 429)

    def test_reading_metadata_and_anomaly_episode_preserved(self):
        reading = {"source": "esp32_wokwi", "temperature": 25, "humidity": 50,
                   "gas_raw": 1200, "pir": False, "sample": 4,
                   "data_mode": "generated", "anomaly": True, "anomaly_score": -0.1}
        for _ in range(2):
            self.assertEqual(self.client.post("/api/v1/readings", json=reading).status_code, 201)
        self.assertEqual(self.client.get("/api/v1/readings").json()[-1]["sample"], 4)
        self.assertEqual(len(self.client.get("/api/v1/alerts").json()), 1)

    def test_bridge_publishes_and_transfers_esp_confirmation(self):
        identifier = self.command()
        path = Path(__file__).resolve().parents[1] / "mqtt_bridge.py"
        spec = importlib.util.spec_from_file_location("isolated_bridge", path)
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        def request(endpoint, payload=None):
            response = self.client.get(endpoint) if payload is None else self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.status_code, response.json()
        bridge.api_request = request
        published = []
        def publish(topic, payload, qos, retain):
            command = json.loads(payload)
            self.assertGreater(command["ttl_ms"], 0)
            self.assertLessEqual(command["ttl_ms"], 30000)
            published.append((topic, qos, retain))
            bridge.states.put({"kind": "ack", "id": command["id"], "status": "executed",
                               "led": True, "buzzer": False, "data_mode": "sensors"})
            return SimpleNamespace(rc=bridge.mqtt.MQTT_ERR_SUCCESS)
        bridge.connected.set()
        worker = threading.Thread(target=bridge.command_worker, args=(SimpleNamespace(publish=publish),))
        worker.start()
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                history = self.client.get("/api/v1/commands").json()
                if history[0]["status"] == "executed":
                    break
                time.sleep(0.05)
            self.assertEqual(history[0]["id"], identifier)
            self.assertEqual(history[0]["status"], "executed")
            self.assertEqual(published, [("sentinel/commands", 1, False)])
            self.assertTrue(self.client.get("/api/v1/device/state").json()["led"])
        finally:
            bridge.stop.set()
            worker.join(timeout=4)


if __name__ == "__main__":
    unittest.main()
