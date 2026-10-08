"""Contrat temporel, modèle exporté et intégration API du Random Forest."""
from pathlib import Path
import unittest
import numpy as np
from sensor_classifier import SensorClassifier
import test_commands


ROOT = Path(__file__).resolve().parents[1]


def reading(sample, temperature=24, gas=1000, source="esp32_wokwi"):
    return {"sample": sample, "source": source, "data_mode": "sensors",
            "temperature": temperature, "humidity": 50, "gas_raw": gas, "pir": False}


class FeatureTests(unittest.TestCase):
    def setUp(self):
        class RecordingModel:
            classes_ = ["FUITE_GAZ", "INCIDENT_COMBINE", "NORMAL", "PRE_ALERTE", "SURCHAUFFE"]
            def predict_proba(model, frame):
                model.frame = frame
                return np.array([[0, 0, .9, .1, 0]])
        self.classifier = SensorClassifier.__new__(SensorClassifier)
        self.classifier.model = RecordingModel()
        self.classifier.variables = ["temperature", "humidity", "gas_raw", "delta_temp", "delta_humidity", "delta_gas", "variation_temp_5", "variation_gas_5"]
        self.classifier.histories = {}

    def test_features_use_five_intervals_not_five_rows(self):
        for i in range(6):
            result = self.classifier.analyze(reading(i + 1, 25 + i, 1000 + 100 * i), i * 2)
        values = self.classifier.model.frame.iloc[0].to_dict()
        self.assertEqual(values["variation_temp_5"], 5)
        self.assertEqual(values["variation_gas_5"], 500)
        self.assertEqual(values["delta_temp"], 1)
        self.assertEqual(values["delta_gas"], 100)
        self.assertEqual(result["ai_class"], "NORMAL")
        self.assertEqual(result["ai_confidence"], .9)

    def test_restart_and_sources_reset_only_their_own_history(self):
        for i in range(5):
            self.classifier.analyze(reading(i + 1), i * 2)
        self.assertEqual(self.classifier.analyze(reading(1, source="esp8266"), 9)["ai_window_samples"], 1)
        self.assertEqual(self.classifier.analyze(reading(6), 10)["ai_status"], "ready")
        self.assertEqual(self.classifier.analyze(reading(1), 12)["ai_window_samples"], 1)
        self.assertEqual(self.classifier.analyze(reading(2), 25)["ai_window_samples"], 1)


class ClassifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifier = SensorClassifier(ROOT / "random_forest_sentinel.joblib")

    def setUp(self):
        self.classifier.histories.clear()

    def test_history_required_then_normal(self):
        for i in range(5):
            result = self.classifier.analyze(reading(i + 1), i * 2)
            self.assertEqual(result["ai_status"], "warming_up")
            self.assertNotIn("anomaly", result)
        result = self.classifier.analyze(reading(6), 10)
        self.assertEqual(result["ai_class"], "NORMAL")
        self.assertFalse(result["anomaly"])
        self.assertGreaterEqual(result["ai_confidence"], 0)
        self.assertLessEqual(result["ai_confidence"], 1)

    def test_restart_gap_and_delta_discontinuity_reset_history(self):
        for i in range(6):
            self.classifier.analyze(reading(i + 1), i * 2)
        self.assertEqual(self.classifier.analyze(reading(1), 12)["ai_window_samples"], 1)
        self.assertEqual(self.classifier.analyze(reading(2), 30)["ai_window_samples"], 1)
        changed = {**reading(3, temperature=35), "delta_temp": 0}
        self.assertEqual(self.classifier.analyze(changed, 32)["ai_window_samples"], 1)

    def test_sources_do_not_share_history(self):
        for i in range(5):
            self.classifier.analyze(reading(i + 1), i)
        result = self.classifier.analyze(reading(6, source="esp8266"), 5)
        self.assertEqual(result["ai_status"], "warming_up")

    def test_five_model_classes(self):
        for expected, temp, gas in [("NORMAL", 24, 1000), ("PRE_ALERTE", 38, 1000),
                                    ("SURCHAUFFE", 43, 1000), ("FUITE_GAZ", 24, 3400),
                                    ("INCIDENT_COMBINE", 43, 3400)]:
            self.classifier.histories.clear()
            for i in range(6):
                result = self.classifier.analyze(reading(i + 1, temp, gas), i * 2)
            self.assertEqual(result["ai_class"], expected)


class ClassifierApiTests(unittest.TestCase):
    setUp = test_commands.CommandTests.setUp
    tearDown = test_commands.CommandTests.tearDown

    def test_classes_persist_and_new_risk_produces_one_alert(self):
        current = {**reading(1), "ai_model": "RandomForest", "ai_status": "ready",
                   "ai_class": "PRE_ALERTE", "ai_confidence": .75, "ai_window_samples": 6, "anomaly": True}
        for _ in range(2):
            self.assertEqual(self.client.post("/api/v1/readings", headers=self.bridge_headers, json=current).status_code, 201)
        alerts = self.client.get("/api/v1/alerts").json()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["model"], "RandomForest")
        current["ai_class"] = "SURCHAUFFE"
        self.client.post("/api/v1/readings", headers=self.bridge_headers, json=current)
        self.assertEqual(len(self.client.get("/api/v1/alerts").json()), 2)
        latest = self.client.get("/api/v1/readings").json()[-1]
        self.assertEqual(latest["ai_confidence"], .75)
        self.assertEqual(latest["ai_class"], "SURCHAUFFE")
