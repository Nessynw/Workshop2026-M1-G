import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "datasets"
INTERVAL_SECONDS = 0.2

FIELDS = [
    "timestamp", "source", "temperature",
    "humidity", "gas_raw", "pir", "scenario",
]


def generate_dataset(filename, count, seed, start):
    rng = random.Random(seed)
    path = DATASET_DIR / filename

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()

        for index in range(count):
            elapsed = index * INTERVAL_SECONDS

            # Variation progressive de charge informatique.
            # La température monte et redescend ; le gaz reste stable.
            load = (
                1 - math.cos(2 * math.pi * elapsed / 120)
            ) / 2

            temperature = (
                25 + 2 * load
                + 0.3 * math.sin(elapsed / 15)
                + rng.gauss(0, 0.04)
            )

            humidity = (
                45 + 1.5 * math.sin(elapsed / 30)
                + rng.gauss(0, 0.08)
            )

            # Valeur brute simulée, sans conversion en ppm.
            gas_raw = (
                900 + 8 * math.sin(elapsed / 20)
                + rng.gauss(0, 2)
            )

            writer.writerow({
                "timestamp": (
                    start + timedelta(seconds=elapsed)
                ).isoformat(),
                "source": "simulation_nominale",
                "temperature": round(temperature, 3),
                "humidity": round(humidity, 3),
                "gas_raw": round(gas_raw, 3),
                "pir": 0,
                "scenario": "fonctionnement_normal_simule",
            })

    print(f"{count} mesures créées : {path}")


def main():
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    generate_dataset(
        "nominal_train.csv", 3000, 42, start
    )
    generate_dataset(
        "nominal_test.csv", 1000, 123,
        start + timedelta(days=1),
    )

    print("\nEntraînement et test sont générés séparément.")
    print("Données synthétiques : validation réelle encore nécessaire.")


if __name__ == "__main__":
    main()