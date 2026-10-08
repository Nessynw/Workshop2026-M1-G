"""Rejoue le modèle livré, sans modifier l'entraînement de la collègue."""
import hashlib
import json
import math
from pathlib import Path
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sensor_classifier import SensorClassifier

ROOT = Path(__file__).resolve().parent


def main():
    model_path = ROOT / "random_forest_sentinel.joblib"
    classifier = SensorClassifier(model_path)
    rows = [json.loads(line) for line in (ROOT / "data/sentinel_1425.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    group = 1
    truth, predicted = [], []
    previous = None
    analyzed = 0
    for index, row in enumerate(rows):
        if previous and any(not math.isclose(row[name] - previous[name], row[delta], abs_tol=.02)
                            for name, delta in [("temperature", "delta_temp"), ("humidity", "delta_humidity"), ("gas_raw", "delta_gas")]):
            group += 1
        result = classifier.analyze({**row, "source": "esp32_wokwi", "data_mode": "generated"}, index * .2)
        previous = row
        if result["ai_status"] != "ready":
            continue
        analyzed += 1
        if group not in [5, 8, 9, 12, 13, 17]:
            continue
        prior = rows[index - 5]
        # Reconstitution des étiquettes du notebook pour comparaison, jamais utilisée en direct.
        temperature, gas = row["temperature"] >= 40, row["gas_raw"] >= 3000
        label = ("INCIDENT_COMBINE" if temperature and gas else "SURCHAUFFE" if temperature
                 else "FUITE_GAZ" if gas else "PRE_ALERTE" if row["temperature"] >= 35
                 or row["gas_raw"] >= 2500 or row["temperature"] - prior["temperature"] >= 3.5
                 or row["gas_raw"] - prior["gas_raw"] >= 700 else "NORMAL")
        truth.append(label)
        predicted.append(result["ai_class"])
    labels = list(classifier.model.classes_)
    report = {"model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
              "total_rows": len(rows), "sequences": group, "analyzed_rows": analyzed,
              "test_rows": len(truth), "accuracy": accuracy_score(truth, predicted),
              "labels": labels, "confusion_matrix": confusion_matrix(truth, predicted, labels=labels).tolist(),
              "classification_report": classification_report(truth, predicted, output_dict=True, zero_division=0),
              "limits": "Rejeu du test déjà consulté, étiquettes définies par règles. Ne mesure pas la précision sur incidents réels."}
    destination = ROOT / "models/random_forest_integration_report.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Mesures : {len(rows)} ; séquences : {group} ; mesures analysées : {analyzed}")
    print(f"Rejeu du test du notebook : {len(truth)} mesures ; accord : {report['accuracy']:.2%}")
    print("Ce résultat concerne le test étiqueté du notebook, pas des incidents physiques indépendants.")
    print("Rapport :", destination)


if __name__ == "__main__":
    main()
