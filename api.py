import json
import os
import mysql.connector
import paho.mqtt.client as mqtt

from pathlib import Path
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


app = FastAPI(title="Sentinel-X")


BASE_DIR = Path(__file__).resolve().parent


# =========================
# Configuration MQTT
# =========================

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv(
    "MQTT_TOPIC",
    "sentinel/sensors/readings"
)



# Connexion MySQL


def get_mysql_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE", "sentinel"),
        user=os.getenv("MYSQL_USER", "sentinel_app"),
        password=os.getenv("MYSQL_PASSWORD"),
    )




db = get_mysql_connection()
cursor = db.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        payload TEXT NOT NULL
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS readings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        payload TEXT NOT NULL
    )
""")

db.commit()

cursor.close()
db.close()




class Alert(BaseModel):
    timestamp: str
    source: str
    type: str
    model: str


class SensorReading(BaseModel):
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source: Literal["simulation", "esp8266"]
    temperature: float
    humidity: float = Field(ge=0, le=100)
    gas_raw: float = Field(ge=0)
    pir: bool




def save_reading(reading: SensorReading):
    payload = json.dumps(
        reading.model_dump(mode="json")
    )

    db = get_mysql_connection()
    cursor = db.cursor()

    cursor.execute(
        "INSERT INTO readings (payload) VALUES (%s)",
        (payload,),
    )

    db.commit()

    cursor.close()
    db.close()


def mqtt_message(client, userdata, message):
    try:
        data = json.loads(
            message.payload.decode("utf-8")
        )

        reading = SensorReading.model_validate(data)

        save_reading(reading)

        print("Mesure MQTT reçue :", data)

    except Exception as error:
        print("Erreur traitement MQTT :", error)


def start_mqtt():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_message = mqtt_message

    client.connect(
        MQTT_BROKER,
        MQTT_PORT,
        60
    )

    client.subscribe(MQTT_TOPIC)

    print(
        f"MQTT connecté à "
        f"{MQTT_BROKER}:{MQTT_PORT}, "
        f"topic : {MQTT_TOPIC}"
    )

    client.loop_start()

    return client


mqtt_client = start_mqtt()




latest_frame = None




@app.get("/")
def dashboard():
    return FileResponse(
        BASE_DIR / "index.html"
    )




@app.get("/health")
def health():
    return {"status": "ok"}




@app.post("/api/v1/alerts", status_code=201)
def receive_alert(alert: Alert):

    payload = json.dumps(
        alert.model_dump()
    )

    db = get_mysql_connection()
    cursor = db.cursor()

    cursor.execute(
        "INSERT INTO alerts (payload) VALUES (%s)",
        (payload,),
    )

    db.commit()

    cursor.close()
    db.close()

    return {"status": "received"}


@app.get("/api/v1/alerts")
def get_alerts():

    db = get_mysql_connection()
    cursor = db.cursor()

    cursor.execute(
        "SELECT payload "
        "FROM alerts "
        "ORDER BY id DESC "
        "LIMIT 50"
    )

    rows = cursor.fetchall()

    cursor.close()
    db.close()

    return [
        json.loads(row[0])
        for row in rows
    ]



@app.post("/api/v1/frame", status_code=204)
async def receive_frame(request: Request):

    global latest_frame

    latest_frame = await request.body()

    return Response(status_code=204)


@app.get("/api/v1/frame")
def get_frame():

    if latest_frame is None:
        return Response(status_code=404)

    return Response(
        content=latest_frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store"
        },
    )



@app.get("/api/v1/readings")
def get_readings():

    db = get_mysql_connection()
    cursor = db.cursor()

    cursor.execute(
        "SELECT payload "
        "FROM readings "
        "ORDER BY id DESC "
        "LIMIT 200"
    )

    rows = cursor.fetchall()

    cursor.close()
    db.close()

    return [
        json.loads(row[0])
        for row in reversed(rows)
    ]