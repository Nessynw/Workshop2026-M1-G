import json
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, Request, Response, HTTPException
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
    face_count: int | None = None


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
    sample: int | None = None
    delta_temp: float | None = None
    delta_humidity: float | None = None
    delta_gas: float | None = None
    presence_change: int | None = None
    data_mode: str | None = None
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

# Commandes persistantes. L'API reste accessible seulement sur le PC local.
import time
from uuid import uuid4

with closing(sqlite3.connect(DATABASE)) as db:
    db.execute("""CREATE TABLE IF NOT EXISTS commands (
        id TEXT PRIMARY KEY, payload TEXT NOT NULL,
        status TEXT NOT NULL, created_at REAL NOT NULL,
        expires_at REAL NOT NULL, result TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS device_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        payload TEXT NOT NULL, received_at REAL NOT NULL
    )""")
    db.commit()


class DeviceState(BaseModel):
    led: bool
    buzzer: bool
    mqtt_connected: bool = True
    actuators_supported: bool = True
    data_mode: Literal["generated", "sensors"] = "generated"
    oled: bool = False


class DeviceCommand(BaseModel):
    action: Literal["led_on", "led_off", "buzzer_on", "buzzer_off"]


class CommandResult(BaseModel):
    status: Literal["sent", "executed", "rejected", "failed"]
    detail: str = Field(default="", max_length=300)


def expire_commands(db):
    db.execute(
        "UPDATE commands SET status='expired' "
        "WHERE status IN ('queued', 'sent') AND expires_at < ?",
        (time.time(),),
    )


@app.post("/api/v1/device/state")
def update_device_state(state: DeviceState):
    with closing(sqlite3.connect(DATABASE)) as db:
        db.execute(
            "INSERT OR REPLACE INTO device_state VALUES (1, ?, ?)",
            (state.model_dump_json(), time.time()),
        )
        db.commit()
    return {"status": "received"}


@app.get("/api/v1/device/state")
def get_device_state():
    with closing(sqlite3.connect(DATABASE)) as db:
        row = db.execute(
            "SELECT payload, received_at FROM device_state WHERE id=1"
        ).fetchone()
    if not row:
        return {"online": False, "actuators_supported": False}
    state = json.loads(row[0])
    state["online"] = time.time() - row[1] < 10 and state["mqtt_connected"]
    state["received_at"] = datetime.fromtimestamp(row[1], timezone.utc).isoformat()
    return state


@app.post("/api/v1/commands", status_code=202)
def create_command(command: DeviceCommand):
    state = get_device_state()
    if not state.get("online") or not state.get("actuators_supported"):
        raise HTTPException(503, "ESP ou bridge déconnecté : commande non envoyée.")
    now = time.time()
    identifier = str(uuid4())
    payload = {
        "id": identifier, "action": command.action,
        "expires_at": int(now + 30), "duration_ms": 2000,
    }
    with closing(sqlite3.connect(DATABASE)) as db:
        expire_commands(db)
        pending = db.execute(
            "SELECT COUNT(*) FROM commands WHERE status IN ('queued', 'sent')"
        ).fetchone()[0]
        if pending >= 10:
            raise HTTPException(429, "Trop de commandes en attente.")
        db.execute(
            "INSERT INTO commands VALUES (?, ?, 'queued', ?, ?, NULL)",
            (identifier, json.dumps(payload), now, payload["expires_at"]),
        )
        db.commit()
    return {**payload, "status": "queued"}


@app.get("/api/v1/commands/pending")
def pending_commands():
    with closing(sqlite3.connect(DATABASE)) as db:
        expire_commands(db)
        rows = db.execute(
            "SELECT payload FROM commands WHERE status='queued' "
            "ORDER BY created_at LIMIT 10"
        ).fetchall()
        db.commit()
    return [json.loads(row[0]) for row in rows]


@app.get("/api/v1/commands")
def command_history():
    with closing(sqlite3.connect(DATABASE)) as db:
        expire_commands(db)
        rows = db.execute(
            "SELECT payload, status, result FROM commands "
            "ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        db.commit()
    return [{**json.loads(row[0]), "status": row[1], "detail": row[2]} for row in rows]


@app.post("/api/v1/commands/{identifier}/result")
def update_command_result(identifier: str, result: CommandResult):
    with closing(sqlite3.connect(DATABASE)) as db:
        expire_commands(db)
        row = db.execute("SELECT status FROM commands WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise HTTPException(404, "Commande inconnue.")
        # Une confirmation matérielle peut arriver avant le statut 'sent'.
        if row[0] not in ("executed", "rejected", "failed", "expired"):
            db.execute(
                "UPDATE commands SET status=?, result=? WHERE id=?",
                (result.status, result.detail, identifier),
            )
        db.commit()
    return {"status": "received"}
