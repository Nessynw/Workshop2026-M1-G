import csv
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
MODEL_DIR = BASE_DIR / "models"


def read_rows(filename):
    path = BASE_DIR / "datasets" / filename
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def make_windows(rows):
    return [
        compute_features(rows[end - WINDOW_SIZE:end])
        for end in range(WINDOW_SIZE, len(rows) + 1)
    ]


rows = read_rows("nominal_train.csv")

# Trois usages distincts :
# apprentissage, calibration, puis évaluation.
training = make_windows(rows[:2000])
calibration = make_windows(rows[2000:])
testing = make_windows(read_rows("nominal_test.csv"))

model = IsolationForest(
    n_estimators=200,
    contamination="auto",
    random_state=42,
    n_jobs=-1,
)
model.fit(training)

calibration_scores = model.decision_function(calibration)

# Objectif exploratoire : environ 1 % d'alertes
# sur les fenêtres normales de calibration.
threshold = float(np.quantile(calibration_scores, 0.01))

test_scores = model.decision_function(testing)
alerts = int((test_scores < threshold).sum())

MODEL_DIR.mkdir(parents=True, exist_ok=True)
model_path = MODEL_DIR / "demo_calibrated_model.joblib"

joblib.dump({
    "model": model,
    "features": FEATURE_NAMES,
    "window_size": WINDOW_SIZE,
    "feature_version": "temporal_v1",
    "sklearn_version": sklearn.__version__,
    "data_origin": "simulation_nominale",
    "sample_interval_seconds": 0.2,
    "decision_threshold": threshold,
}, model_path)

print("Calibration terminée.")
print(f"Fenêtres d'apprentissage : {len(training)}")
print(f"Fenêtres de calibration : {len(calibration)}")
print(f"Seuil du score : {threshold:.4f}")
print(f"Fenêtres de test nominal : {len(testing)}")
print(f"Fausses alertes simulées : {alerts}")
print(f"Taux : {100 * alerts / len(testing):.2f} %")
print(f"Modèle sauvegardé : {model_path}")
print("Le test nominal a déjà été consulté : résultat exploratoire.")
print("Les incidents doivent être retestés avec ce nouveau seuil.")
print("Le bridge reste inchangé.")