from datetime import datetime

import numpy as np


WINDOW_SIZE = 20
SENSORS = ["temperature", "humidity", "gas_raw"]

FEATURE_NAMES = [
    f"{sensor}_{statistic}"
    for sensor in SENSORS
    for statistic in [
        "current",
        "mean",
        "change",
        "slope_per_second",
    ]
]


def parse_timestamp(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).timestamp()


def compute_features(readings):
    if len(readings) < WINDOW_SIZE:
        raise ValueError(
            f"Il faut {WINDOW_SIZE} mesures pour analyser une tendance."
        )

    window = list(readings)[-WINDOW_SIZE:]

    timestamps = np.array(
        [parse_timestamp(row["timestamp"]) for row in window],
        dtype=float,
    )

    if not np.isfinite(timestamps).all():
        raise ValueError("Horodatages invalides.")

    if np.any(np.diff(timestamps) <= 0):
        raise ValueError(
            "Les mesures doivent avoir des dates strictement croissantes."
        )

    # Temps écoulé depuis le début de la fenêtre.
    elapsed = timestamps - timestamps[0]
    centered_time = elapsed - elapsed.mean()
    denominator = float(np.sum(centered_time ** 2))

    features = []

    for sensor in SENSORS:
        values = np.array(
            [float(row[sensor]) for row in window],
            dtype=float,
        )

        if not np.isfinite(values).all():
            raise ValueError(f"Valeurs invalides pour {sensor}.")

        current = float(values[-1])
        mean = float(values.mean())
        change = float(values[-1] - values[0])

        # Pente calculée sur toute la fenêtre :
        # positive = hausse ; négative = baisse.
        slope = float(
            np.sum(centered_time * (values - mean))
            / denominator
        )

        features.extend([
            current,
            mean,
            change,
            slope,
        ])

    return features