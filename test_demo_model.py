import csv
from pathlib import Path

import joblib

from temporal_features import WINDOW_SIZE, compute_features

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"

bundle = joblib.load(MODEL_DIR / "demo_calibrated_model.joblib")
model = bundle["model"]
threshold = bundle["decision_threshold"]

with (BASE_DIR / "datasets" / "nominal_validation.csv").open(
    encoding="utf-8-sig", newline=""
) as file:
    rows = list(csv.DictReader(file))

# Dix séquences espacées, issues du test nominal.
references = [
    rows[end - WINDOW_SIZE:end]
    for end in range(100, len(rows) + 1, 100)
]


def make_scenario(reference, scenario):
    window = []

    for index, original in enumerate(reference):
        row = dict(original)
        progress = index / (WINDOW_SIZE - 1)

        for sensor in ["temperature", "humidity", "gas_raw"]:
            row[sensor] = float(row[sensor])

        if scenario in ["hausse_temperature", "derive_combinee"]:
            row["temperature"] += 0.6 * progress

        if scenario in ["hausse_gaz", "derive_combinee"]:
            row["gas_raw"] += 20 * progress

        if scenario == "pic_ponctuel":
            if index == WINDOW_SIZE // 2:
                row["temperature"] += 3
                row["gas_raw"] += 100

        window.append(row)

    return window


scenarios = [
    "normal",
    "hausse_temperature",
    "hausse_gaz",
    "derive_combinee",
    "pic_ponctuel",
]

results = []

for scenario in scenarios:
    alerts = 0
    scores = []

    for number, reference in enumerate(references, start=1):
        window = make_scenario(reference, scenario)
        features = compute_features(window)
        score = float(model.decision_function([features])[0])
        anomaly = score < threshold
        
        alerts += int(anomaly)
        scores.append(score)

        results.append({
            "scenario": scenario,
            "sequence": number,
            "score": score,
            "anomaly": anomaly,
        })

    print(f"\nScénario : {scenario}")
    print(f"Séquences signalées : {alerts}/{len(references)}")
    print(f"Score moyen : {sum(scores) / len(scores):.4f}")

report = MODEL_DIR / "demo_fresh_validation_report.csv"
with report.open("w", encoding="utf-8", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=["scenario", "sequence", "score", "anomaly"],
    )
    writer.writeheader()
    writer.writerows(results)

print("\nTests artificiels à la cadence de 0,2 seconde.")
print("Gaz exprimé en valeur brute, pas en ppm.")
print("Un signalement ne prouve pas la prédiction d'un incident réel.")
print(f"Rapport sauvegardé : {report}")