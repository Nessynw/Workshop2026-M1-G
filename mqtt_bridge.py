"""Bridge local MQTTS : mesures, commandes et confirmations du firmware."""
import getpass
import json
import math
import os
import queue
import ssl
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
import joblib
import paho.mqtt.client as mqtt

BASE_DIR = Path(__file__).resolve().parent
CA_FILE = BASE_DIR / "mosquitto" / "certs" / "ca.crt"
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "8883"))
MQTT_USER = "bridge"
MQTT_TOPIC = "sentinel/sensors"
COMMAND_TOPIC = "sentinel/commands"
STATE_TOPIC = "sentinel/device/state"
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
MODEL_FILE = BASE_DIR / "models" / "anomaly_model.joblib"
MODEL = None
FEATURES = []
measurements = queue.Queue(maxsize=500)
states = queue.Queue(maxsize=200)
stop = threading.Event()
connected = threading.Event()


def api_request(path, payload=None):
    request = urllib.request.Request(
        API_URL + path,
        data=None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.status, json.load(response)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print("Connexion MQTT refusée :", reason_code)
        return
    connected.set()
    client.subscribe([(MQTT_TOPIC, 0), (STATE_TOPIC, 1)])
    print("MQTTS connecté — réception des mesures et des états ESP.")


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    connected.clear()
    print("MQTT déconnecté ; reconnexion automatique en cours.")


def on_subscribe(client, userdata, mid, reason_codes, properties):
    if any(code.is_failure for code in reason_codes):
        connected.clear()
        print("Abonnement refusé : vérifier les ACL Mosquitto.")


def on_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Objet JSON attendu.")
        destination = states if message.topic == STATE_TOPIC else measurements
        destination.put_nowait(data)
    except (ValueError, UnicodeDecodeError, queue.Full) as error:
        print("Message MQTT ignoré :", error)


def measurement_worker():
    while not stop.is_set():
        try:
            data = measurements.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            if not isinstance(data["presence"], bool):
                raise ValueError("presence doit être un booléen.")
            mode = data.get("data_mode", "generated")
            source = data.get("source", "esp32_wokwi")
            reading = {"source": source, "pir": data["presence"], "data_mode": mode}
            for name in ("temperature", "humidity", "gas_raw"):
                value = float(data[name])
                if not math.isfinite(value):
                    raise ValueError("Mesure non finie.")
                reading[name] = value
            for name in ("sample", "delta_temp", "delta_humidity", "delta_gas", "presence_change"):
                if name in data:
                    reading[name] = data[name]
            # Ancien modèle conservé. Aucun nouvel entraînement ici.
            # Il a été entraîné sur le générateur, pas sur des capteurs réels.
            if MODEL is not None and mode == "generated":
                sample = [[reading[name] for name in FEATURES]]
                score = float(MODEL.decision_function(sample)[0])
                reading.update(anomaly=score < 0, anomaly_score=score)
            status, _ = api_request("/api/v1/readings", reading)
            print(f"Mesure transmise à l'API : {status}", reading)
        except (ValueError, KeyError, TypeError, OSError) as error:
            print("Mesure non transmise :", error)
        finally:
            measurements.task_done()


def command_worker(client):
    while not stop.is_set():
        try:
            # Les confirmations matérielles ne bloquent jamais la boucle MQTT.
            for _ in range(30):
                try:
                    data = states.get_nowait()
                except queue.Empty:
                    break
                try:
                    if data.get("kind") == "ack":
                        api_request("/api/v1/commands/" + str(data["id"]) + "/result", {
                            "status": data["status"], "detail": data.get("detail", "")
                        })
                    if "led" in data and "buzzer" in data:
                        api_request("/api/v1/device/state", {
                            "led": data["led"], "buzzer": data["buzzer"],
                            "mqtt_connected": True, "actuators_supported": True,
                            "data_mode": data.get("data_mode", "generated"),
                            "oled": data.get("oled", False),
                        })
                except OSError:
                    # Conserver une confirmation si l'API redémarre momentanément.
                    try:
                        states.put_nowait(data)
                    except queue.Full:
                        print("File d'états pleine : confirmation non conservée.")
                    raise
                finally:
                    states.task_done()
            if connected.is_set():
                _, pending = api_request("/api/v1/commands/pending")
                for command in pending:
                    remaining_ms = int((command["expires_at"] - time.time()) * 1000)
                    if remaining_ms <= 0:
                        continue
                    # Le PC et le simulateur peuvent avoir des dates différentes.
                    # L'API et le bridge contrôlent l'expiration sur le PC.
                    command = {**command, "ttl_ms": min(remaining_ms, 30000)}
                    result = client.publish(
                        COMMAND_TOPIC, json.dumps(command), qos=1, retain=False
                    )
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        api_request("/api/v1/commands/" + command["id"] + "/result", {
                            "status": "sent", "detail": "Publiée en MQTTS ; confirmation ESP attendue."
                        })
        except (ValueError, KeyError, TypeError, OSError) as error:
            print("Commandes/état :", error)
        stop.wait(0.25)


def main():
    global MODEL, FEATURES
    if not CA_FILE.is_file():
        raise SystemExit("Certificat CA absent : " + str(CA_FILE))
    if MODEL_FILE.is_file():
        try:
            bundle = joblib.load(MODEL_FILE)
            MODEL, FEATURES = bundle["model"], bundle["features"]
        except Exception as error:
            print("Ancien modèle indisponible ; transmission sans analyse :", error)
    password = getpass.getpass("Mot de passe MQTT du compte bridge : ")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sentinel-api-bridge")
    client.username_pw_set(MQTT_USER, password)
    client.tls_set_context(ssl.create_default_context(cafile=str(CA_FILE)))
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    workers = [threading.Thread(target=measurement_worker, daemon=True),
               threading.Thread(target=command_worker, args=(client,), daemon=True)]
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
        for worker in workers:
            worker.start()
        print("Bridge démarré — Ctrl + C pour arrêter.")
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nBridge arrêté.")
    finally:
        stop.set()
        client.disconnect()
        for worker in workers:
            if worker.is_alive():
                worker.join(timeout=4)


if __name__ == "__main__":
    main()
