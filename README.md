# Sentinel-X — Workshop 2026 - M1 DATA & IA

Projet de supervision d’un parc informatique réalisé pour AetherCorp dans le cadre du Workshop BAC+4.

## 1. Présentation

Sentinel-X centralise les mesures environnementales d’un boîtier connecté et les détections d’une webcam.

Le dashboard permet de :

- consulter la température, l’humidité et la valeur brute du capteur de gaz ;
- visualiser les dernières mesures sous forme de graphiques ;
- consulter l’état du capteur de mouvement PIR ;
- commander une LED rouge et un buzzer ;
- afficher le flux caméra avec les détections de visages ;
- signaler la présence simultanée de plusieurs visages ;
- consulter les alertes et les résultats d’analyse disponibles dans l'historique.

## 2. Architecture

```text
DHT22 / Gaz / PIR
       |
       v
ESP32 dans Wokwi
       |
       | MQTTS — port 8883
       v
Mosquitto dans Docker
       |
       v
Bridge Python sur le PC
       |
       | HTTP local — port 8000
       v
API FastAPI dans Docker ----> SQLite
       |
       v
Dashboard web

Webcam ---> vision.py ---> images et alertes ---> API

Dashboard ---> API ---> Bridge ---> MQTTS ---> LED / Buzzer
                                             |
                              Confirmation de l’ESP
```

## 3. Technologies

| Partie | Technologies |
|---|---|
| Firmware | C++, Arduino, PlatformIO |
| Simulation | Wokwi |
| Communication IoT | MQTT sécurisé par TLS |
| Broker | Eclipse Mosquitto |
| API | Python, FastAPI, Uvicorn |
| Stockage | SQLite |
| Interface | HTML, CSS, JavaScript |
| Vision | OpenCV, YuNet et HOG |
| Infrastructure | Docker et Docker Compose |

## 4. Organisation du dépôt

```text
Sentinel-X/
├── api.py                    # API, mesures, alertes et commandes
├── index.html                # Dashboard local
├── mqtt_bridge.py            # Liaison entre MQTT et l’API
├── vision.py                 # Webcam et détection de visages
├── simulation_capteurs.py    # Simulation Python des mesures
├── export_dataset.py         # Export des mesures
├── train_model.py            # Entraînement du modèle initial
├── test_anomalies.py         # Tests du modèle initial
├── requirements.txt          # Dépendances Python
├── Dockerfile
├── compose.yaml
├── container_entrypoint.py
├── esp32-wokwi/
│   ├── diagram.json          # Circuit simulé
│   ├── platformio.ini
│   ├── wokwi.toml
│   └── src/
│       ├── main.cpp
│       ├── device_io.h
│       ├── ca_cert.h
│       └── mqtt_secrets.example.h
├── mosquitto/
│   ├── config/
│   └── certs/
├── datasets/                 # Jeux de données
├── models/                   # Modèles et résultats
└── tests/                    # Tests API et bridge
```

## 5. Prérequis

- Windows avec Python 3.12 ou 3.13.
- Docker Desktop démarré.
- Visual Studio Code.
- Extensions PlatformIO et Wokwi.
- Licence Wokwi active pour la simulation dans VS Code. 
- Passerelle réseau Wokwi permettant l’accès au broker local.
- Webcam disponible.
- Certificats TLS et comptes Mosquitto configurés.

## 6. Installation

Cloner le dépôt :

```powershell
git clone https://github.com/Nessynw/Workshop2026-M1-G.git
cd Workshop2026-M1-G
```

Créer l’environnement Python et installer les dépendances :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Configuration privée

Les fichiers suivants doivent être présents localement :

- `mosquitto/certs/ca.crt` : certificat public de l’autorité locale ;
- `mosquitto/certs/server.crt` : certificat du broker ;
- `mosquitto/certs/server.key` : clé privée du broker ;
- `mosquitto/config/passwords` : comptes Mosquitto ;
- `esp32-wokwi/src/mqtt_secrets.h` : identifiants du compte ESP.

Copier `mqtt_secrets.example.h` en `mqtt_secrets.h`, puis renseigner les
identifiants du compte `esp32`.

Le certificat présent dans `ca_cert.h` doit correspondre à l’autorité ayant
signé le certificat du broker.

Le certificat serveur doit couvrir les noms et adresses utilisés :
`host.wokwi.internal`, `localhost`, `mosquitto` et `127.0.0.1`.

Les comptes Mosquitto utilisés sont :

- `esp32` : envoi des mesures et réception des commandes ;
- `bridge` : réception des mesures et envoi des commandes.


## Configuration des accès à l’API et au dashboard

Avant le premier lancement, exécuter depuis la racine du projet :

```powershell
.\.venv\Scripts\python.exe setup_security.py
```

Choisir un mot de passe de 12 caractères minimum, puis le confirmer.

Le script crée un fichier `.env` contenant :
- le mot de passe du dashboard sous forme de hash PBKDF2 ;
- le secret utilisé pour signer les sessions ;
- une clé API pour le bridge MQTT ;
- une clé API distincte pour la caméra.
- 
## 7. Lancement

Exécuter les commandes suivantes depuis la racine du projet.

### Étape 1 — Infrastructure Docker

```powershell
docker compose up -d --build
docker compose ps
docker compose logs --tail 20 sentinel mosquitto
```

### Étape 2 — Bridge MQTT

Dans un terminal :

```powershell
.\.venv\Scripts\python.exe mqtt_bridge.py
```

Saisir le mot de passe du compte `bridge`.

Laisser ce terminal ouvert. Une seule instance du bridge doit fonctionner.

### Étape 3 — Firmware et simulation

Compiler le firmware :

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -d esp32-wokwi
```

Dans VS Code, ouvrir le dossier `esp32-wokwi`, puis :

1. appuyer sur `Ctrl + Shift + P` ;
2. choisir `Wokwi: Start Simulator` ;
3. vérifier la connexion Wi-Fi et MQTT.

### Étape 4 — Caméra

Dans un autre terminal :

```powershell
.\.venv\Scripts\python.exe vision.py
```

### Étape 5 — Dashboard

Ouvrir :

http://127.0.0.1:8000/

Après une modification du dashboard :

```powershell
docker compose up -d --build sentinel
```

Puis actualiser le navigateur avec `Ctrl + F5`.

## 8. Utilisation

### Capteurs

La température est affichée en degrés Celsius et l’humidité en pourcentage.

Le gaz est affiché en **valeur brute ADC**, pas en ppm.

Dans `main.cpp` :

- `USE_GENERATED_DATA = false` : lecture continue des capteurs Wokwi ;
- `USE_GENERATED_DATA = true` : génération de 1425 mesures synthétiques.

### PIR et caméra

Le PIR et la caméra sont deux sources de détection différentes.

Dans Wokwi, cliquer sur le PIR puis sur `Simulate Motion` pour simuler
un mouvement. Le PIR simulé ne réagit pas à la webcam du PC.

La caméra détecte les visages visibles avec YuNet. Chaque visage est
encadré et le nombre de visages est affiché.

Une détection continue d’au moins deux visages pendant 0,5 seconde
déclenche une alerte spécifique.

### LED et buzzer

- LED verte : connexion MQTT.
- LED rouge : commandée depuis le dashboard.
- Buzzer : signal sonore de deux secondes (déclenché manuellement).

Le dashboard distingue une commande enregistrée, envoyée, exécutée,
refusée ou expirée. 
--> L’exécution est confirmée par l’ESP.

## 9. Stockage et sécurité

Les mesures, alertes et commandes sont stockées dans SQLite.

Le volume Docker `alerts-data` conserve les données après le redémarrage
des conteneurs.

Les protections configurées comprennent :

- TLS pour les échanges MQTT ;
- authentification Mosquitto ;
- ACL séparant les permissions de l’ESP et du bridge ;
- ports Docker publiés uniquement sur `127.0.0.1` ;
- configurations et certificats montés en lecture seule ;
- limitation des ressources des conteneurs ;
- rotation des journaux Docker ;
- contrôle de santé de l’API ;
- exécution de l’API sans privilèges root après initialisation du volume.

## 11. Vérifications

### Tests automatisés

```powershell
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Les tests utilisent une base temporaire et vérifient notamment :

- le refus des commandes lorsque le boîtier est hors ligne ;
- la file d’attente des commandes ;
- l’expiration ;
- la confirmation d’exécution ;
- la transmission simulée par le bridge ;
- la conservation des mesures et des alertes.

### Recette de démonstration

1. Vérifier que l’API et Mosquitto démarrent.
2. Vérifier la réception des mesures dans le dashboard.
3. Modifier une valeur de capteur dans Wokwi.
4. Simuler un mouvement avec le PIR.
5. Allumer et éteindre la LED rouge.
6. Déclencher le buzzer et vérifier son arrêt.
7. Vérifier l’affichage de l’adresse IP et des états sur l’OLED.
8. Vérifier la détection d’un visage puis de plusieurs visages.
9. Consulter les alertes.
10. Vérifier la conservation de l’historique après redémarrage.

## 12. Arrêt

Arrêter les scripts Python avec `Ctrl + C`, puis arrêter la simulation Wokwi.

Arrêter les conteneurs :

```powershell
docker compose down
```

!! Ne pas ajouter `-v` si les données du volume doivent être conservées !!

## 13. Sources et licences

- OpenCV : https://opencv.org/
- YuNet : https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
- Wokwi : https://docs.wokwi.com/
- PlatformIO : https://docs.platformio.org/
- Mosquitto : https://mosquitto.org/documentation/
- FastAPI : https://fastapi.tiangolo.com/

Le modèle YuNet est fourni avec sa licence MIT dans
`models/YuNet-LICENSE.txt`.
