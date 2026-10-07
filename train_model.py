import csv
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest


BASE_DIR = Path(__file__).resolve().parent
DATASET = BASE_DIR / "datasets" / "mesures_wokwi.csv"
MODEL_DIR = BASE_DIR / "models"

FEATURES = ["temperature", "humidity", "gas_raw"]


def main():
    with DATASET.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    if len(rows) < 200:
        raise ValueError("Il faut au moins 200 mesures.")

    values = np.array(
        [
            [float(row[name]) for name in FEATURES]
            for row in rows
        ],
        dtype=float,
    )

    if not np.isfinite(values).all():
        raise ValueError("Le dataset contient des valeurs invalides.")

    # Respecte l'ordre chronologique :
    # premières 80 % pour apprendre, dernières 20 % pour tester.
    split = int(len(values) * 0.8)
    train_values = values[:split]
    test_values = values[split:]

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

    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "sklearn_version": sklearn.__version__,
        },
        MODEL_DIR / "anomaly_model.joblib",
    )

    report = {
        "model": "IsolationForest",
        "features": FEATURES,
        "data_origin": "generateur_cpp_wokwi",
        "dataset_sha256": hashlib.sha256(
            DATASET.read_bytes()
        ).hexdigest(),
        "training_samples": len(train_values),
        "test_samples": len(test_values),
        "atypical_test_samples": atypical_count,
        "accuracy": None,
        "note": "Données sans étiquettes : précision non mesurée.",
    }

    (MODEL_DIR / "training_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with (MODEL_DIR / "test_predictions.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.writer(file)
        writer.writerow(
            FEATURES + ["score", "prediction"]
        )

        for sample, score, prediction in zip(
            test_values, scores, predictions
        ):
            writer.writerow(
                sample.tolist()
                + [
                    float(score),
                    "atypique" if prediction == -1 else "habituel",
                ]
            )

    print("Entraînement terminé.")
    print(f"Mesures d'entraînement : {len(train_values)}")
    print(f"Mesures de test : {len(test_values)}")
    print(f"Mesures de test jugées atypiques : {atypical_count}")
    print(f"Modèle sauvegardé : {MODEL_DIR / 'anomaly_model.joblib'}")
    print("Ce nombre d'atypiques n'est pas un taux de précision.")


if __name__ == "__main__":
    main()