import csv
import json
from pathlib import Path

import joblib
import sklearn
from sklearn.ensemble import IsolationForest

from temporal_features import (
    WINDOW_SIZE,
    FEATURE_NAMES,
    compute_features,
)

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "datasets"
MODEL_DIR = BASE_DIR / "models"


def load_windows(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    if len(rows) < WINDOW_SIZE:
        raise ValueError(f"Pas assez de mesures dans {path}")

    if any(
        row["source"] != "simulation_nominale"
        or row["scenario"] != "fonctionnement_normal_simule"
        for row in rows
    ):
        raise ValueError("Le fichier contient un scénario inattendu.")

    windows = []
    timestamps = []

    for end in range(WINDOW_SIZE - 1, len(rows)):
        window = rows[end - WINDOW_SIZE + 1:end + 1]
        windows.append(compute_features(window))
        timestamps.append(rows[end]["timestamp"])

    return windows, timestamps


def main():
    training, _ = load_windows(
        DATASET_DIR / "nominal_train.csv"
    )
    testing, timestamps = load_windows(
        DATASET_DIR / "nominal_test.csv"
    )

    model = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(training)

    predictions = model.predict(testing)
    scores = model.decision_function(testing)
    alerts = int((predictions == -1).sum())
    alert_rate = 100 * alerts / len(testing)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "demo_temporal_model.joblib"

    joblib.dump({
        "model": model,
        "features": FEATURE_NAMES,
        "window_size": WINDOW_SIZE,
        "feature_version": "temporal_v1",
        "sklearn_version": sklearn.__version__,
        "data_origin": "simulation_nominale",
        "sample_interval_seconds": 0.2,
    }, model_path)

    report = {
        "data_origin": "simulation_nominale",
        "training_windows": len(training),
        "test_windows": len(testing),
        "false_alerts_on_simulated_normal": alerts,
        "false_alert_rate_percent": alert_rate,
        "note": (
            "Test sur fonctionnement normal synthétique uniquement. "
            "Détection des incidents et validation réelle à effectuer. "
            "Les fenêtres successives se chevauchent."
        ),
    }

    (MODEL_DIR / "demo_temporal_training_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with (MODEL_DIR / "demo_nominal_predictions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["timestamp", "score", "prediction"],
        )
        writer.writeheader()

        for timestamp, score, prediction in zip(
            timestamps, scores, predictions
        ):
            writer.writerow({
                "timestamp": timestamp,
                "score": float(score),
                "prediction": (
                    "atypique" if prediction == -1 else "habituel"
                ),
            })

    print("Entraînement terminé.")
    print(f"Fenêtres d'entraînement : {len(training)}")
    print(f"Fenêtres de test nominal : {len(testing)}")
    print(f"Fausses alertes sur le normal simulé : {alerts}")
    print(f"Taux de fausses alertes simulées : {alert_rate:.2f} %")
    print(f"Modèle sauvegardé : {model_path}")
    print("Le bridge utilise encore le modèle précédent.")


if __name__ == "__main__":
    main()