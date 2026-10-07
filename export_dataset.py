import csv
import json
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "datasets" / "mesures_wokwi.csv"

# Ce code sera exécuté dans le conteneur de l'API.
DATABASE_SCRIPT = """
import json
import sqlite3

with sqlite3.connect("/app/data/alerts.db") as db:
    rows = db.execute(
        '''
        SELECT payload
        FROM readings
        WHERE json_extract(payload, '$.source') = ?
        ORDER BY id DESC
        LIMIT 500
        ''',
        ("esp32_wokwi",),
    ).fetchall()

# Remet les mesures de la plus ancienne à la plus récente.
readings = [json.loads(row[0]) for row in reversed(rows)]
print(json.dumps(readings))
"""


def main():
    result = subprocess.run(
        [
            "docker", "compose", "exec", "-T",
            "sentinel", "python", "-c", DATABASE_SCRIPT,
        ],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    if result.returncode != 0:
        print("Export impossible :")
        print(result.stderr)
        return

    readings = json.loads(result.stdout)

    if not readings:
        print("Aucune mesure Wokwi enregistrée dans la base.")
        return

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "timestamp",
        "source",
        "temperature",
        "humidity",
        "gas_raw",
        "pir",
    ]

    with OUTPUT_FILE.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()

        for reading in readings:
            row = {column: reading[column] for column in columns}
            row["pir"] = int(row["pir"])
            writer.writerow(row)

    print(f"{len(readings)} mesures exportées.")
    print(f"Fichier : {OUTPUT_FILE}")

    if len(readings) < 500:
        print("La base contient moins de 500 mesures Wokwi.")


if __name__ == "__main__":
    main()