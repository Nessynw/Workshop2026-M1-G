"""Inférence du modèle de la branche data, sans réentraînement ni seuil de substitution."""
from collections import deque
import math
import joblib
import pandas as pd

FEATURES = ["temperature", "humidity", "gas_raw", "delta_temp", "delta_humidity",
            "delta_gas", "variation_temp_5", "variation_gas_5"]
CLASSES = {"NORMAL", "PRE_ALERTE", "SURCHAUFFE", "FUITE_GAZ", "INCIDENT_COMBINE"}


class SensorClassifier:
    def __init__(self, path):
        bundle = joblib.load(path)
        self.model = bundle["modele"]
        # Une mesure à la fois : limiter les threads évite la concurrence avec la caméra.
        self.model.n_jobs = 1
        self.variables = bundle["variables"]
        if self.variables != FEATURES or set(self.model.classes_) != CLASSES:
            raise ValueError("Le modèle ne correspond pas aux variables/classes du notebook randomF.")
        self.histories = {}

    def analyze(self, reading, now):
        key = (reading["source"], reading["data_mode"])
        state = self.histories.setdefault(key, {"rows": deque(maxlen=6), "time": None})
        rows = state["rows"]
        if rows:
            previous = rows[-1]
            reset = now - state["time"] > 10
            if reading.get("sample") is not None and previous.get("sample") is not None:
                reset |= reading["sample"] != previous["sample"] + 1
            for name, delta in [("temperature", "delta_temp"), ("humidity", "delta_humidity"), ("gas_raw", "delta_gas")]:
                if reading.get(delta) is not None:
                    reset |= not math.isclose(reading[name] - previous[name], reading[delta], abs_tol=0.02)
            if reset:
                rows.clear()
        values = dict(reading)
        for name, delta in [("temperature", "delta_temp"), ("humidity", "delta_humidity"), ("gas_raw", "delta_gas")]:
            if rows and values.get(delta) is not None:
                values[delta] = float(values[delta])
            elif rows:
                values[delta] = values[name] - rows[-1][name]
            else:
                values[delta] = 0.0
        rows.append(values)
        state["time"] = now
        metadata = {"ai_model": "RandomForest", "ai_status": "warming_up",
                    "ai_window_samples": len(rows)}
        if len(rows) < 6:
            return metadata
        values["variation_temp_5"] = values["temperature"] - rows[0]["temperature"]
        values["variation_gas_5"] = values["gas_raw"] - rows[0]["gas_raw"]
        frame = pd.DataFrame([[values[name] for name in self.variables]], columns=self.variables)
        probabilities = self.model.predict_proba(frame)[0]
        index = int(probabilities.argmax())
        prediction = str(self.model.classes_[index])
        confidence = float(probabilities[index])
        return {**metadata, "ai_status": "ready", "ai_class": prediction,
                "ai_confidence": confidence, "anomaly": prediction != "NORMAL"}
