import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np

from temporal_features import WINDOW_SIZE, compute_features

BASE_DIR = Path(__file__).resolve().parent
bundle = joblib.load(
    BASE_DIR / "models" / "temporal_anomaly_model.joblib"
)
model = bundle["model"]

with (BASE_DIR / "datasets" / "mesures_wokwi.csv").open(
    encoding="utf-8-sig", newline=""
) as file:
    rows = list(csv.DictReader(file))

# Référence calculée uniquement sur la partie d'entraînement.
training_rows = rows[:int(len(rows) * 0.8)]
sensors = ["temperature", "humidity", "gas_raw"]
reference = {
    sensor: float(np.median([
        float(row[sensor]) for row in training_rows
    ]))
    for sensor in sensors
}


def make_window(duration, temperature_rise=0, gas_rise=0):
    start = datetime.now(timezone.utc)
    window = []

    for index in range(WINDOW_SIZE):
        progress = index / (WINDOW_SIZE - 1)
        window.append({
            "timestamp": (
                start + timedelta(seconds=duration * progress)
            ).isoformat(),
            "temperature": (
                reference["temperature"]
                - temperature_rise * (1 - progress)
            ),
            "humidity": reference["humidity"],
            "gas_raw": (
                reference["gas_raw"]
                - gas_rise * (1 - progress)
            ),
        })

    return window


scenarios = [
    ("Valeurs constantes", make_window(4)),
    ("Hausse de température sur 4 secondes",
     make_window(4, temperature_rise=8)),
    ("Hausse de gaz sur 4 secondes",
     make_window(4, gas_rise=1000)),
    ("Hausse combinée sur 4 secondes",
     make_window(4, temperature_rise=8, gas_rise=1000)),
    ("Hausse combinée sur 60 secondes",
     make_window(60, temperature_rise=8, gas_rise=1000)),
]

results = []

for name, window in scenarios:
    features = compute_features(window)
    score = float(model.decision_function([features])[0])
    prediction = "ATYPIQUE" if score < 0 else "HABITUEL"

    print(f"\n{name}")
    print(f"Score : {score:.4f}")
    print(f"Résultat : {prediction}")

    results.append({
        "scenario": name,
        "score": score,
        "prediction": prediction,
    })

report = BASE_DIR / "models" / "temporal_scenario_report.csv"

with report.open("w", encoding="utf-8", newline="") as file:
    writer = csv.DictWriter(
        file, fieldnames=["scenario", "score", "prediction"]
    )
    writer.writeheader()
    writer.writerows(results)

print("\nToutes les séquences ont les mêmes valeurs finales.")
print("Ces scénarios sont artificiels : ils ne mesurent pas la précision.")
print("Le scénario de 60 secondes explore une cadence différente.")
print(f"Rapport sauvegardé : {report}")