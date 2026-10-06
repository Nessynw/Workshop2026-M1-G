import json
import random
import time
import urllib.request

print("Simulation de capteurs — Ctrl + C pour arrêter.")

try:
    while True:
        reading = {
            "source": "simulation",
            "temperature": round(random.uniform(22, 25), 1),
            "humidity": round(random.uniform(45, 55), 1),
            "gas_raw": random.randint(100, 150),
            "pir": False,
        }

        request = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/readings",
            data=json.dumps(reading).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                print("Mesure envoyée :", response.status, reading)
        except Exception as error:
            print("Envoi impossible :", error)

        time.sleep(2)
    

except KeyboardInterrupt:
    print("\nSimulation arrêtée.")