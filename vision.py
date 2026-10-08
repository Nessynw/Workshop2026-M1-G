import json
import time
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

import cv2
from api_access import service_headers


# Remplacer 0 par 1 si la mauvaise caméra est sélectionnée.
CAMERA_INDEX = 0

WIDTH = 640
HEIGHT = 480
ALERT_LOG = Path(__file__).resolve().parent / "events.jsonl"


def log_alert(method, event_type="human_presence", face_count=None):
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "webcam_pc",
        "type": event_type,
        "model": method,
    }
    if face_count is not None:
        event["face_count"] = face_count

    with ALERT_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event) + "\n")

    print(f"ALERTE : {face_count} visages détectés" if event_type == "multiple_faces"
          else "ALERTE : présence humaine détectée")

    try:
        request = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/alerts",
            data=json.dumps(event).encode("utf-8"),
            headers={"Content-Type": "application/json", **service_headers("vision")},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=2) as response:
            print("Alerte envoyée à l’API :", response.status)

    except Exception as error:
        print("Impossible d’envoyer l’alerte :", error)


def detect_faces(frame, face_model):
    """YuNet fournit les visages et supprime les rectangles en double."""
    face_model.setInputSize((frame.shape[1], frame.shape[0]))
    _, rows = face_model.detect(frame)
    if rows is None:
        return []
    return [
        (int(row[0]), int(row[1]), int(row[2]), int(row[3]), "Visage / YuNet")
        for row in rows
        if row[2] >= 30 and row[3] >= 30
    ]


def detect_people(frame, face_model, body_model):
    """Compte les visages avec YuNet ; HOG conserve la détection des corps."""
    faces = detect_faces(frame, face_model)
    if len(faces):
        return faces

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
            headers={"Content-Type": "image/jpeg", **service_headers("vision")},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=0.5):
            pass
    except Exception as error:
        print("Envoi image impossible :", error)


def main():
    service_headers("vision")
    cv2.setNumThreads(2)

    model_file = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"
    if not model_file.is_file():
        raise RuntimeError("Modèle YuNet absent : " + str(model_file))
    face_model = cv2.FaceDetectorYN.create(
        str(model_file), "", (WIDTH, HEIGHT),
        score_threshold=0.85, nms_threshold=0.3, top_k=5000
    )

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
    multiple_faces_active = False
    last_multiple_faces = float("-inf")
    multiple_candidate_since = None

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
            face_count = sum(label == "Visage / YuNet" for *_, label in detections)
            if detections:
                last_detection = now

            presence = now - last_detection < 1.5

            if presence and not presence_active and detections:
                log_alert(detections[0][4], face_count=face_count)

            # Nouvelle alerte même si la première personne était déjà présente.
            # La temporisation évite de répéter l'alerte à chaque image.
            if face_count >= 2:
                if multiple_candidate_since is None:
                    multiple_candidate_since = now
                if now - multiple_candidate_since >= 0.5:
                    last_multiple_faces = now
                    if not multiple_faces_active:
                        log_alert("Visage / YuNet", "multiple_faces", face_count)
            else:
                multiple_candidate_since = None
            multiple_faces_active = now - last_multiple_faces < 1.5

            presence_active = presence

            for index, (x, y, w, h, label) in enumerate(detections, start=1):
                cv2.rectangle(
                    frame, (x, y), (x + w, y + h), (0, 220, 0), 2
                )
                cv2.putText(
                    frame, f"Visage {index}" if label == "Visage / YuNet" else label,
                    (x, max(20, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1
                )

            status = (f"ALERTE : {face_count} VISAGES DETECTES" if face_count >= 2
                      else "1 VISAGE DETECTE" if face_count == 1
                      else "PRESENCE DETECTEE" if presence else "Aucune presence")
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
            cv2.putText(
                frame, f"Visages visibles : {face_count}", (15, 86),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1
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
