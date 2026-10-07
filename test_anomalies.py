import csv
from pathlib import Path
from statistics import median

import joblib


BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"

bundle = joblib.load(MODEL_DIR / "anomaly_model.joblib")
model = bundle["model"]
features = bundle["features"]


def main():
    dataset = BASE_DIR / "datasets" / "mesures_wokwi.csv"

    with dataset.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    # Même découpage que lors de l'entraînement.
    split = int(len(rows) * 0.8)
    training_rows = rows[:split]
    test_rows = rows[split:]

    reference = {
        name: median(float(row[name]) for row in training_rows)
        for name in features
    }

    max_temperature = max(
        float(row["temperature"]) for row in training_rows
    )
    max_gas = max(
        float(row["gas_raw"]) for row in training_rows
    )

    scenarios = [
        (
            "Référence médiane",
            "reference",
            reference.copy(),
        ),
        (
            "Température inhabituelle",
            "injection",
            {
                **reference,
                "temperature": max_temperature + 30,
            },
        ),
        (
            "Gaz inhabituel",
            "injection",
            {
                **reference,
                "gas_raw": max_gas * 2,
            },
        ),
        (
            "Humidité inhabituelle",
            "injection",
            {
                **reference,
                "humidity": 100,
            },
        ),
        (
            "Plusieurs valeurs inhabituelles",
            "injection",
            {
                **reference,
                "temperature": max_temperature + 30,
                "gas_raw": max_gas * 2,
                "humidity": 100,
            },
        ),
    ]

    results = []

    for name, origin, values in scenarios:
        sample = [[values[field] for field in features]]
        score = float(model.decision_function(sample)[0])
        atypical = score < 0

        print(f"\n{name}")
        print("Valeurs :", values)
        print("Score :", round(score, 4))
        print(
            "Résultat :",
            "ATYPIQUE" if atypical else "HABITUEL",
        )

        results.append({
            "scenario": name,
            "origine": origin,
            **values,
            "score": score,
            "atypique": atypical,
        })

    report_file = MODEL_DIR / "scenario_test_report.csv"

    with report_file.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(results[0]),
        )
        writer.writeheader()
        writer.writerows(results)

    injected = [
        result for result in results
        if result["origine"] == "injection"
    ]
    detected = sum(result["atypique"] for result in injected)

    samples = [
        [float(row[field]) for field in features]
        for row in test_rows
    ]
    predictions = model.predict(samples)
    flagged = int((predictions == -1).sum())

    print(f"\nCas injectés signalés : {detected}/{len(injected)}")
    print(
        f"Mesures du jeu de test signalées : "
        f"{flagged}/{len(test_rows)}"
    )
    print("Sans étiquettes, ces signalements ne sont pas")
    print("automatiquement des vraies ou des fausses alertes.")
    print("Rapport sauvegardé :", report_file)


if __name__ == "__main__":
    main()