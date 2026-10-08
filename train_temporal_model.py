import csv
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest

from temporal_features import (
    WINDOW_SIZE,
    FEATURE_NAMES,
    compute_features,
)


BASE_DIR = Path(__file__).resolve().parent
DATASET = BASE_DIR / "datasets" / "mesures_wokwi.csv"
MODEL_DIR = BASE_DIR / "models"


def main():
    with DATASET.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    if len(rows) < WINDOW_SIZE * 5:
        raise ValueError("Pas assez de mesures pour l'entraînement.")

    if any(row["source"] != "esp32_wokwi" for row in rows):
        raise ValueError("Le dataset doit contenir uniquement Wokwi.")

    # Découpage chronologique des mesures.
    split = int(len(rows) * 0.8)

    training_features = []
    testing_features = []
    testing_timestamps = []

    for end in range(WINDOW_SIZE - 1, len(rows)):
        window = rows[end - WINDOW_SIZE + 1:end + 1]
        features = compute_features(window)

        if end < split:
            training_features.append(features)
        else:
            testing_features.append(features)
            testing_timestamps.append(rows[end]["timestamp"])

    train_values = np.array(training_features, dtype=float)
    test_values = np.array(testing_features, dtype=float)

    model = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=42,
        n_jobs=-1,
    )

    model.fit(train_values)

    predictions = model.predict(test_values)
    scores = model.decision_function(test_values)
    atypical_count = int(np.sum(predictions == -1))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODEL_DIR / "temporal_anomaly_model.joblib"

    joblib.dump(
        {
            "model": model,
            "features": FEATURE_NAMES,
            "window_size": WINDOW_SIZE,
            "feature_version": "temporal_v1",
            "sklearn_version": sklearn.__version__,
        },
        model_path,
    )

    report = {
        "model": "IsolationForest",
        "feature_version": "temporal_v1",
        "features": FEATURE_NAMES,
        "window_size": WINDOW_SIZE,
        "data_origin": "generateur_cpp_wokwi",
        "dataset_sha256": hashlib.sha256(
            DATASET.read_bytes()
        ).hexdigest(),
        "training_windows": len(train_values),
        "test_windows": len(test_values),
        "atypical_test_windows": atypical_count,
        "accuracy": None,
        "note": (
            "Fenêtres successives avec historique uniquement. "
            "Données sans étiquettes : précision non mesurée."
        ),
    }

    (MODEL_DIR / "temporal_training_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with (MODEL_DIR / "temporal_test_predictions.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.writer(file)
        writer.writerow(
            ["timestamp"] + FEATURE_NAMES + ["score", "prediction"]
        )

        for timestamp, values, score, prediction in zip(
            testing_timestamps,
            test_values,
            scores,
            predictions,
        ):
            writer.writerow(
                [timestamp]
                + values.tolist()
                + [
                    float(score),
                    "atypique" if prediction == -1 else "habituel",
                ]
            )

    print("Entraînement temporel terminé.")
    print(f"Mesures par fenêtre : {WINDOW_SIZE}")
    print(f"Variables analysées : {len(FEATURE_NAMES)}")
    print(f"Fenêtres d'entraînement : {len(train_values)}")
    print(f"Fenêtres de test : {len(test_values)}")
    print(f"Fenêtres de test atypiques : {atypical_count}")
    print("Modèle sauvegardé :", model_path)
    print("La précision reste à mesurer avec des scénarios étiquetés.")


if __name__ == "__main__":
    main()