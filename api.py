import json
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Sentinel-X")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE = DATA_DIR / "alerts.db"

latest_frame = None

# Crée la table au premier démarrage.
with closing(sqlite3.connect(DATABASE)) as db:
    db.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL
        )
    """)
    db.commit()


class Alert(BaseModel):
    timestamp: str
    source: str
    type: str
    model: str


@app.get("/")
def dashboard():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/alerts", status_code=201)
def receive_alert(alert: Alert):
    payload = json.dumps(alert.model_dump())

    with closing(sqlite3.connect(DATABASE)) as db:
        db.execute(
            "INSERT INTO alerts (payload) VALUES (?)",
            (payload,),
        )
        db.commit()

    return {"status": "received"}


@app.get("/api/v1/alerts")
def get_alerts():
    with closing(sqlite3.connect(DATABASE)) as db:
        rows = db.execute(
            "SELECT payload FROM alerts ORDER BY id DESC LIMIT 50"
        ).fetchall()

    return [json.loads(row[0]) for row in rows]


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
        headers={"Cache-Control": "no-store"},
    )

from datetime import datetime, timezone
from typing import Literal
from pydantic import Field


class SensorReading(BaseModel):
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source: Literal["simulation", "esp8266", "esp32_wokwi"]
    temperature: float
    humidity: float = Field(ge=0, le=100)
    gas_raw: float = Field(ge=0)
    pir: bool
    anomaly: bool | None = None
    anomaly_score: float | None = Field(
        default=None,
        allow_inf_nan=False,
    )


with closing(sqlite3.connect(DATABASE)) as db:
    db.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL
        )
    """)
    db.commit()


@app.post("/api/v1/readings", status_code=201)
def receive_reading(reading: SensorReading):
    payload = json.dumps(reading.model_dump(mode="json"))

    with closing(sqlite3.connect(DATABASE)) as db:
        db.execute("BEGIN IMMEDIATE")

        previous_row = db.execute(
            """
            SELECT payload
            FROM readings
            WHERE json_extract(payload, '$.source') = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (reading.source,),
        ).fetchone()

        previous_anomaly = False

        if previous_row:
            previous = json.loads(previous_row[0])
            previous_anomaly = previous.get("anomaly") is True

        db.execute(
            "INSERT INTO readings (payload) VALUES (?)",
            (payload,),
        )

        # Une alerte au début d'un épisode atypique.
        if reading.anomaly is True and not previous_anomaly:
            alert = {
                "timestamp": reading.timestamp.isoformat(),
                "source": reading.source,
                "type": "sensor_anomaly",
                "model": "IsolationForest",
                "temperature": reading.temperature,
                "humidity": reading.humidity,
                "gas_raw": reading.gas_raw,
                "anomaly_score": reading.anomaly_score,
            }

            db.execute(
                "INSERT INTO alerts (payload) VALUES (?)",
                (json.dumps(alert),),
            )

        db.commit()

    return {"status": "received"}


@app.get("/api/v1/readings")
def get_readings():
    with closing(sqlite3.connect(DATABASE)) as db:
        rows = db.execute(
            "SELECT payload FROM readings ORDER BY id DESC LIMIT 200"
        ).fetchall()

    return [json.loads(row[0]) for row in reversed(rows)]