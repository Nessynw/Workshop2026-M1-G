#pour transmettre les mesures de l’ESP32, reçues par MQTT, à l API et au dashboard
import getpass
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt


BASE_DIR = Path(__file__).resolve().parent
CA_FILE = BASE_DIR / "mosquitto" / "certs" / "ca.crt"

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 8883
MQTT_TOPIC = "sentinel/sensors"
MQTT_USER = "bridge"

API_URL = "http://127.0.0.1:8000/api/v1/readings"


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print("Connexion MQTT refusée :", reason_code)
        return

    print("Connecté au serveur MQTT sécurisé.")
    client.subscribe(MQTT_TOPIC)


def on_subscribe(client, userdata, mid, reason_codes, properties):
    if any(code.is_failure for code in reason_codes):
        print("Abonnement refusé : vérifier les droits du compte bridge.")
        return

    print("En attente des mesures de l'ESP32...")


def on_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode("utf-8"))

        if not isinstance(data["presence"], bool):
            raise ValueError("Le champ presence doit être true ou false.")

        reading = {
            "source": "esp32_wokwi",
            "temperature": data["temperature"],
            "humidity": data["humidity"],
            "gas_raw": data["gas_raw"],
            "pir": data["presence"],
        }

        request = urllib.request.Request(
            API_URL,
            data=json.dumps(reading, allow_nan=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=3) as response:
            print(
                f"Mesure transmise à l'API : {response.status}",
                reading,
            )

    except urllib.error.HTTPError as error:
        print("API : erreur", error.code)
        print(error.read().decode("utf-8", errors="replace"))

    except (ValueError, KeyError, TypeError) as error:
        print("Mesure invalide :", error)

    except urllib.error.URLError as error:
        print("API inaccessible :", error.reason)


def main():
    if not CA_FILE.is_file():
        print("Certificat introuvable :", CA_FILE)
        return

    password = getpass.getpass("Mot de passe MQTT du compte bridge : ")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="sentinel-api-bridge",
    )

    client.username_pw_set(MQTT_USER, password)
    client.tls_set_context(
        ssl.create_default_context(cafile=str(CA_FILE))
    )

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        print("Bridge démarré — Ctrl + C pour arrêter.")
        client.loop_forever()

    except KeyboardInterrupt:
        print("\nBridge arrêté.")

    except OSError as error:
        print("Connexion impossible :", error)

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()