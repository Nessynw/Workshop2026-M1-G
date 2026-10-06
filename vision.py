import json
import time
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

import cv2


# Remplacer 0 par 1 si la mauvaise caméra est sélectionnée.
CAMERA_INDEX = 0

WIDTH = 640
HEIGHT = 480
ALERT_LOG = Path(__file__).resolve().parent / "events.jsonl"


def log_alert(method):
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "webcam_pc",
        "type": "human_presence",
        "model": method,
    }

    with ALERT_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event) + "\n")

    print("ALERTE : présence humaine détectée")

    try:
        request = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/alerts",
            data=json.dumps(event).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=2) as response:
            print("Alerte envoyée à l’API :", response.status)

    except Exception as error:
        print("Impossible d’envoyer l’alerte :", error)


def detect_people(frame, face_model, body_model):
    """Détecte un visage proche, sinon cherche des corps entiers."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = face_model.detectMultiScale(
        gray,
        scaleFactor=1.15,
        minNeighbors=5,
        minSize=(40, 40),
    )

    if len(faces):
        # Détection humaine avec le modèle Haar.
        return [
            (int(x), int(y), int(w), int(h), "Visage / Haar")
            for x, y, w, h in faces
        ]

    # Image réduite pour limiter le temps de calcul.
    small = cv2.resize(frame, (320, 240))

    bodies, scores = body_model.detectMultiScale(
        small,
        winStride=(8, 8),
        padding=(8, 8),
        scale=1.08,
    )

    return [
        (int(x * 2), int(y * 2), int(w * 2), int(h * 2),
         "Personne / HOG")
        for (x, y, w, h), score in zip(bodies, scores)
        if float(score) >= 0.5
    ]


last_frame_sent = 0


def send_frame(frame):
    global last_frame_sent

    now = time.monotonic()
    if now - last_frame_sent < 0.2:
        return

    last_frame_sent = now

    success, image = cv2.imencode(
        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
    )
    if not success:
        return

    try:
        request = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/frame",
            data=image.tobytes(),
            headers={"Content-Type": "image/jpeg"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=0.5):
            pass
    except Exception as error:
        print("Envoi image impossible :", error)


def main():
    cv2.setNumThreads(2)

    face_model = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    if face_model.empty():
        raise RuntimeError("Impossible de charger le modèle visage.")

    body_model = cv2.HOGDescriptor()
    body_model.setSVMDetector(
        cv2.HOGDescriptor_getDefaultPeopleDetector()
    )

    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        camera.release()
        raise RuntimeError("Webcam inaccessible.")

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)

    presence_active = False
    last_detection = float("-inf")

    print("Caméra active. Appuie sur Q dans sa fenêtre pour quitter.")

    try:
        while True:
            success, frame = camera.read()
            if not success:
                print("Impossible de lire la webcam.")
                break

            frame = cv2.resize(frame, (WIDTH, HEIGHT))

            start = time.perf_counter()
            detections = detect_people(frame, face_model, body_model)
            processing_ms = (time.perf_counter() - start) * 1000

            now = time.monotonic()
            if detections:
                last_detection = now

            presence = now - last_detection < 1.5

            if presence and not presence_active and detections:
                log_alert(detections[0][4])

            presence_active = presence

            for x, y, w, h, label in detections:
                cv2.rectangle(
                    frame, (x, y), (x + w, y + h), (0, 220, 0), 2
                )
                cv2.putText(
                    frame, label, (x, max(20, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1
                )

            status = "PRESENCE DETECTEE" if presence else "Aucune presence"
            color = (0, 0, 255) if presence else (0, 220, 0)

            cv2.putText(
                frame, status, (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
            )
            cv2.putText(
                frame, f"Traitement IA : {processing_ms:.1f} ms",
                (15, 60), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (255, 255, 255), 1
            )

            send_frame(frame)
           # cv2.imshow("SENTINEL-X - Detection de presence", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
