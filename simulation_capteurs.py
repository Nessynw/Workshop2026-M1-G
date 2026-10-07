import json
import random
import time
from pathlib import Path

import paho.mqtt.client as mqtt


MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 8883
MQTT_TOPIC = "sentinel/sensors/readings"

CA_CERT = (
    Path(__file__).resolve().parent
    / "mosquitto"
    / "certs"
    / "ca.crt"
)


client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2
)

client.username_pw_set(
    "sentinel",
    "massiva"
)

# =========================
# TLS
# =========================

client.tls_set(
    ca_certs=str(CA_CERT)
)

print("Connexion sécurisée à Mosquitto avec TLS...")

client.connect(
    MQTT_BROKER,
    MQTT_PORT,
    60
)

client.loop_start()

print("Simulation de capteurs — MQTT + TLS — Ctrl + C pour arrêter.")

try:
    while True:
        reading = {
            "source": "simulation",
            "temperature": round(random.uniform(22, 25), 1),
            "humidity": round(random.uniform(45, 55), 1),
            "gas_raw": random.randint(100, 150),
            "pir": False,
        }

        payload = json.dumps(reading)

        result = client.publish(
            MQTT_TOPIC,
            payload
        )

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print("Mesure envoyée par MQTT + TLS :", reading)
        else:
            print("Erreur MQTT :", result.rc)

        time.sleep(2)

except KeyboardInterrupt:
    print("\nSimulation arrêtée.")

finally:
    client.loop_stop()
    client.disconnect()