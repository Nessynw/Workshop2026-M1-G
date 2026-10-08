# Sentinel-X — Workshop 2026

Prototype de supervision : capteurs ESP, MQTTS, API FastAPI/SQLite,
dashboard web, commandes LED/buzzer et détection humaine par webcam.

## Architecture actuelle

```text
DHT22 / MQ-2 / PIR -> ESP32 Wokwi -> MQTTS :8883 -> Mosquitto
                                                 |
                                      bridge Python sur le PC
                                                 |
                                      HTTP local :8000 -> API -> SQLite
                                                          |
Webcam USB -> vision.py -> image + alertes -----------------+ -> dashboard

Dashboard -> API (file persistante) -> bridge -> MQTTS -> LED / buzzer
                                        <- confirmation de l'ESP <-
```

Le PC et le simulateur constituent le montage actuellement livré. Le sujet
mentionne un ESP8266 physique : le firmware ESP32 ne doit pas être présenté
comme un firmware ESP8266 validé. La connexion physique et le point d'accès
Wi-Fi dédié restent à valider avec le matériel de l'équipe.

## Installation sur Windows

Prérequis : Python 3.12/3.13, Docker Desktop démarré, VS Code, extensions
PlatformIO et Wokwi avec licence active, accès aux bibliothèques PlatformIO.

Depuis la racine du projet :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Secrets et certificats

Ne pas publier : `mosquitto/certs/*.key`, `mosquitto/config/passwords`,
`esp32-wokwi/src/mqtt_secrets.h`, `.env`, données SQLite locales.
Ces fichiers sont exclus de Git et du contexte de construction Docker.

1. Créer une CA locale et un certificat serveur avec les SAN
   `host.wokwi.internal`, `localhost`, `mosquitto`, `127.0.0.1`.
2. Placer le certificat public CA dans `mosquitto/certs/ca.crt` et son
   contenu PEM dans `esp32-wokwi/src/ca_cert.h` (`CA_CERT`).
3. Placer `server.crt` et `server.key` dans `mosquitto/certs/`.
4. Créer les comptes Mosquitto `esp32` et `bridge`, chacun avec son mot de passe.
5. Copier `mqtt_secrets.example.h` en `mqtt_secrets.h`, puis renseigner le
   mot de passe du compte esp32. Le bridge demande son mot de passe au lancement.

Si les certificats locaux existent déjà, ne pas les remplacer pour relancer.
Le fichier de mots de passe est monté en lecture seule dans le broker : le
modifier dans un conteneur temporaire avec un montage en écriture. Ne pas
utiliser `-c` sur un fichier existant car cela supprimerait les autres comptes.

```powershell
docker run --rm -it -v "${PWD}/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2 mosquitto_passwd /mosquitto/config/passwords bridge
```

Les permissions déjà mises en place doivent autoriser l'UID 1883 du broker à
lire `passwords`, `acl` et `server.key`, sans exposer les clés aux autres comptes.

## Lancement

```powershell
docker compose up -d --build
docker compose logs --tail 20 sentinel mosquitto
```

L'API démarre sans privilèges root après initialisation du volume SQLite.
Le volume `alerts-data` garde les mesures, alertes et commandes après redémarrage.
Ne pas utiliser `docker compose down -v` si l'historique doit être conservé.

Dans un premier terminal, lancer le bridge et saisir le mot de passe bridge :

```powershell
.\.venv\Scripts\python.exe mqtt_bridge.py
```

Compiler le firmware :

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -d esp32-wokwi
```

Dans VS Code, ouvrir `esp32-wokwi` et lancer `Wokwi: Start Simulator` par
`Ctrl+Shift+P`. L'accès MQTTS au PC utilise `host.wokwi.internal` ; vérifier
la passerelle réseau Wokwi et garder Docker démarré.

Dans un second terminal, lancer la vision :

```powershell
.\.venv\Scripts\python.exe vision.py
```

Ouvrir http://127.0.0.1:8000. Les commandes sont activées seulement après un
état ESP reçu récemment. Une commande expire après 30 s sans confirmation.
Le buzzer s'arrête automatiquement après 2 s ; un bouton permet aussi de l'arrêter.
Le dashboard distingue « enregistrée », « envoyée » et « exécutée par l'ESP ».
La confirmation signifie que le firmware a appliqué la sortie, pas qu'un capteur
indépendant a vérifié la LED ou le son.

## Câblage ESP32 Wokwi

| Composant | Signal |
|---|---|
| DHT22 | GPIO15, alimentation 3,3 V |
| Gaz MQ-2 | AOUT GPIO34, alimentation 5 V dans le simulateur |
| PIR | OUT GPIO27 |
| LED commandée rouge | GPIO25, résistance 220 ohms, cathode GND |
| LED de connexion verte | GPIO33, résistance 220 ohms, cathode GND |
| Buzzer piézo | positif GPIO26, négatif GND |
| OLED SSD1306 I2C | SDA GPIO21, SCL GPIO22, 3,3 V, GND, adresse 0x3C |

Ces broches sont proposées pour l'ESP32 simulé. Elles ne correspondent pas
directement à l'ESP8266. Pour du matériel réel, vérifier les tensions de sortie
du module MQ-2 et l'adaptation à l'entrée ADC avant le câblage.

## Capteurs et générateur conservé

`USE_GENERATED_DATA = false` dans `main.cpp` lit les composants du circuit Wokwi
en continu (DHT22 toutes les 2 s, gaz, PIR). Les messages portent
`data_mode: "sensors"`. L'OLED affiche IP, Wi-Fi, MQTTS et états des actionneurs.

`USE_GENERATED_DATA = true` utilise le générateur C++ original, limité à 500
mesures à environ 200 ms d'intervalle. Les commandes MQTT restent disponibles
après les 500 mesures. Les messages portent `data_mode: "generated"`.

## Analyse IA et travail de l'équipe

La vision locale utilise Haar/HOG, redimensionne à 640x480, affiche le temps
d'inférence et envoie les images et alertes à l'API. La latence dépend du PC ;
elle doit être mesurée sur la machine de démonstration.

L'ancien Isolation Forest point par point est conservé pour les données du
générateur. Il n'est pas appliqué automatiquement aux capteurs Wokwi : il n'a
pas été entraîné sur leur fonctionnement nominal. `anomaly` reste alors vide.
L'analyse temporelle est prise en charge par la coéquipière. Les essais
temporels précédents ont été retirés à la demande de l'équipe. Ils ne font pas
partie du fonctionnement livré. `export_dataset.py` exporte les mesures en CSV.

Pour raccorder le modèle final, adapter uniquement l'analyse dans
`measurement_worker()` du bridge. Conserver la transmission des données,
les confirmations et la boucle MQTT indépendante. Documenter l'ordre des
variables, les fenêtres, les étiquettes, le découpage entraînement/test et les
limites ; ne pas assimiler un nombre d'anomalies à un taux de précision.

## Sécurité et exploitation

- MQTTS avec validation du certificat CA et du nom du serveur, pas de mode insecure.
- Pas d'accès anonyme au broker ; comptes et ACL séparés.
- ESP : écrit mesures/états, lit commandes. Bridge : droits inverses.
- Commandes non retenues, identifiants uniques, durée limitée et date d'expiration.
- Ports API et MQTT liés à 127.0.0.1 pour ce montage local Wokwi.
- Conteneurs en lecture seule hors volume SQLite, limites CPU/RAM/PID,
  redémarrage automatique, logs limités, privilèges réduits.
- L'API locale n'a pas d'authentification utilisateur. Ne pas exposer son port
  au réseau sans ajouter authentification et règles de pare-feu adaptées.
- Le pare-feu du PC, SSH et les preuves du pentest restent à contrôler sur le
  serveur réellement utilisé ; aucun audit de sécurité complet n'est revendiqué.

```powershell
docker compose ps
docker stats --no-stream
docker compose logs --tail 50 sentinel mosquitto
```

## Recette avant soutenance

1. Vérifier `/health`, les logs et la réception des températures/gaz/PIR.
2. Modifier un capteur dans Wokwi et observer sa courbe et son état PIR.
3. Allumer puis éteindre la LED depuis le dashboard ; vérifier le circuit et
   la mention « exécutée par l'ESP ».
4. Déclencher le buzzer, constater l'arrêt après 2 s, puis tester l'arrêt manuel.
5. Vérifier IP/Wi-Fi/MQTTS sur l'OLED.
6. Arrêter Wokwi : après 10 s les boutons doivent être désactivés.
7. Redémarrer : vérifier la reconnexion, l'historique SQLite et la caméra.
8. Valider le modèle final avec la coéquipière et les preuves du pentest.

## Rendu

Créer le ZIP du code après revue et commit. Ajouter le README, les fichiers
d'exemple, le travail IA de la coéquipière et ses instructions. Exclure tous
les secrets, environnements Python, caches et binaires de compilation.
Le dossier PDF, poster A3, PPTX, vidéo, boîtier Fusion/physique et audit sont
des livrables distincts ; ce dépôt seul ne les remplace pas.

## Vérification du code

Compilation ESP32 réussie et neuf tests API/bridge passés le 8 octobre 2026.
Le test bridge simule le client MQTT ; le clic réel dans Wokwi reste à tester.
Docker n’était pas disponible dans l’environnement de vérification : exécuter
`docker compose config`, puis la recette de lancement sur le poste de démonstration.

Pour rejouer les tests API sans modifier la base locale :

```powershell
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
