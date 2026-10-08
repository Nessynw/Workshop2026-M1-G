import csv
import json
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import joblib

from temporal_features import (
    WINDOW_SIZE,
    FEATURE_NAMES,
    compute_features,
)

BASE_DIR = Path(__file__).resolve().parent
API_URL = "http://127.0.0.1:8000/api/v1/readings"

bundle = joblib.load(
    BASE_DIR / "models" / "demo_calibrated_model.joblib"
)
model = bundle["model"]
threshold = bundle["decision_threshold"]

if (
    bundle["features"] != FEATURE_NAMES
    or bundle["window_size"] != WINDOW_SIZE
):
    raise ValueError("Configuration du modèle incompatible.")

with (BASE_DIR / "datasets" / "nominal_validation.csv").open(
    encoding="utf-8-sig", newline=""
) as file:
    rows = list(csv.DictReader(file))

history = deque(maxlen=WINDOW_SIZE)

print("Démonstration temporelle — données synthétiques.")
print("20 secondes normales, puis une dérive combinée.")
print("Ctrl + C pour arrêter.")

try:
    for index, original in enumerate(rows[:160]):
        started = time.monotonic()
        row = dict(original)

        for sensor in ["temperature", "humidity", "gas_raw"]:
            row[sensor] = float(row[sensor])

        phase = "NORMAL SIMULÉ"

        if index >= 100:
            progression = (index - 99) / 19
            row["temperature"] += 0.6 * progression
            row["gas_raw"] += 20 * progression
            phase = "DÉRIVE COMBINÉE SIMULÉE"

        # Les dates du CSV définissent la cadence simulée de 0,2 s.
        history.append(row)

        reading = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "simulation",
            "temperature": row["temperature"],
            "humidity": row["humidity"],
            "gas_raw": row["gas_raw"],
            "pir": False,
            "anomaly": None,
            "anomaly_score": None,
        }

        if len(history) == WINDOW_SIZE:
            features = compute_features(list(history))
            raw_score = float(
                model.decision_function([features])[0]
            )

            # Score recentré : négatif signifie atypique,
            # conformément à l'affichage du dashboard.
            reading["anomaly_score"] = raw_score - threshold
            reading["anomaly"] = raw_score < threshold

        request = urllib.request.Request(
            API_URL,
            data=json.dumps(
                reading, allow_nan=False
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=3) as response:
            print(
                phase,
                "| API :", response.status,
                "| Anomalie :", reading["anomaly"],
            )

        remaining = 0.2 - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)

    print("Démonstration terminée.")

except KeyboardInterrupt:
    print("\nDémonstration arrêtée.")