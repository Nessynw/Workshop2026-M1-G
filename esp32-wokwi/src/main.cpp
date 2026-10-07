#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <esp_system.h>

#include "ca_cert.h"

// ======================================================
// Wi-Fi
// ======================================================

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// ======================================================
// MQTT sécurisé
// ======================================================

const char* MQTT_SERVER = "host.wokwi.internal";
const int MQTT_PORT = 8883;
const char* MQTT_TOPIC = "sentinel/sensors";

WiFiClientSecure espClient;
PubSubClient mqttClient(espClient);

// ======================================================
// Configuration de la génération
// ======================================================

// Nombre total de lignes
const int MAX_SAMPLES = 500;

// Une nouvelle mesure toutes les 200 ms
const unsigned long PUBLISH_INTERVAL = 200;

// ======================================================
// Plages absolues
// ======================================================

// Température : 20 à 45 °C
const float TEMP_MIN = 20.0;
const float TEMP_MAX = 45.0;

// Humidité : 30 à 70 %
const float HUM_MIN = 30.0;
const float HUM_MAX = 70.0;

// Gaz brut : 500 à 4000
const int GAS_MIN = 500;
const int GAS_MAX = 4000;

// ======================================================
// Variations maximales entre deux mesures
// ======================================================

// Température : maximum +/- 1.2 °C
const float TEMP_DELTA_MAX = 1.2;

// Humidité : maximum +/- 2 %
const float HUM_DELTA_MAX = 2.0;

// Gaz : maximum +/- 250
const int GAS_DELTA_MAX = 250;

// ======================================================
// Structure d'une mesure
// ======================================================

struct Measurement {
  float temperature;
  float humidity;
  int gasRaw;
  bool presence;
};

// ======================================================
// Variables du générateur
// ======================================================

Measurement currentMeasurement;
Measurement previousMeasurement;

bool firstMeasurement = true;

// Cibles temporaires
float targetTemperature;
float targetHumidity;
int targetGas;

// Nombre de mesures pendant lesquelles
// une direction est conservée
int temperatureTargetRemaining = 0;
int humidityTargetRemaining = 0;
int gasTargetRemaining = 0;

// Gestion des événements de présence
int presenceRemaining = 0;

// Nombre de lignes générées
int sampleCount = 0;

// Fin de génération
bool generationFinished = false;

// ======================================================
// Génération d'un float aléatoire
// ======================================================

float randomFloat(float minimum, float maximum) {

  float value =
      (float)random(0, 10001) / 10000.0;

  return minimum +
         value * (maximum - minimum);
}

// ======================================================
// Limiter un float à une plage
// ======================================================

float clampFloat(
    float value,
    float minimum,
    float maximum
) {

  if (value < minimum) {
    return minimum;
  }

  if (value > maximum) {
    return maximum;
  }

  return value;
}

// ======================================================
// Limiter un entier à une plage
// ======================================================

int clampInt(
    int value,
    int minimum,
    int maximum
) {

  if (value < minimum) {
    return minimum;
  }

  if (value > maximum) {
    return maximum;
  }

  return value;
}

// ======================================================
// Déplacer progressivement un float vers une cible
// ======================================================

float moveFloatToward(
    float current,
    float target,
    float maxStep
) {

  float difference =
      target - current;

  // Cible pratiquement atteinte
  if (abs(difference) < 0.05) {
    return target;
  }

  // Petite variation aléatoire
  float step =
      randomFloat(
          0.05,
          maxStep
      );

  // Éviter de dépasser la cible
  if (abs(difference) < step) {
    step = abs(difference);
  }

  if (difference > 0) {
    return current + step;
  }

  return current - step;
}

// ======================================================
// Déplacer progressivement un entier vers une cible
// ======================================================

int moveIntToward(
    int current,
    int target,
    int maxStep
) {

  int difference =
      target - current;

  if (difference == 0) {
    return current;
  }

  // Variation entre 10 et 250 maximum
  int step =
      random(
          10,
          maxStep + 1
      );

  if (abs(difference) < step) {
    step = abs(difference);
  }

  if (difference > 0) {
    return current + step;
  }

  return current - step;
}

// ======================================================
// Choisir une nouvelle cible température
// ======================================================

void chooseTemperatureTarget() {

  targetTemperature =
      randomFloat(
          TEMP_MIN,
          TEMP_MAX
      );

  // Une tendance reste active
  // pendant 4 à 8 mesures maximum
  temperatureTargetRemaining =
      random(4, 9);
}

// ======================================================
// Choisir une nouvelle cible humidité
// ======================================================

void chooseHumidityTarget() {

  targetHumidity =
      randomFloat(
          HUM_MIN,
          HUM_MAX
      );

  humidityTargetRemaining =
      random(4, 9);
}

// ======================================================
// Choisir une nouvelle cible gaz
// ======================================================

void chooseGasTarget() {

  targetGas =
      random(
          GAS_MIN,
          GAS_MAX + 1
      );

  gasTargetRemaining =
      random(4, 9);
}

// ======================================================
// Initialisation du générateur
// ======================================================

void initializeGenerator() {

  // Première température aléatoire
  currentMeasurement.temperature =
      randomFloat(
          TEMP_MIN,
          TEMP_MAX
      );

  // Première humidité aléatoire
  currentMeasurement.humidity =
      randomFloat(
          HUM_MIN,
          HUM_MAX
      );

  // Première valeur gaz aléatoire
  currentMeasurement.gasRaw =
      random(
          GAS_MIN,
          GAS_MAX + 1
      );

  // On commence sans présence
  currentMeasurement.presence =
      false;

  // Premières cibles
  chooseTemperatureTarget();
  chooseHumidityTarget();
  chooseGasTarget();

  previousMeasurement =
      currentMeasurement;
}

// ======================================================
// Mise à jour température
// ======================================================

void updateTemperature() {

  // Vérifier si la cible est atteinte
  bool targetReached =
      abs(
          currentMeasurement.temperature -
          targetTemperature
      ) < 0.05;

  // Nouvelle cible immédiatement
  // si l'ancienne est atteinte
  if (
      temperatureTargetRemaining <= 0 ||
      targetReached
  ) {

    chooseTemperatureTarget();
  }

  currentMeasurement.temperature =
      moveFloatToward(
          currentMeasurement.temperature,
          targetTemperature,
          TEMP_DELTA_MAX
      );

  currentMeasurement.temperature =
      clampFloat(
          currentMeasurement.temperature,
          TEMP_MIN,
          TEMP_MAX
      );

  temperatureTargetRemaining--;
}

// ======================================================
// Mise à jour humidité
// ======================================================

void updateHumidity() {

  bool targetReached =
      abs(
          currentMeasurement.humidity -
          targetHumidity
      ) < 0.05;

  if (
      humidityTargetRemaining <= 0 ||
      targetReached
  ) {

    chooseHumidityTarget();
  }

  currentMeasurement.humidity =
      moveFloatToward(
          currentMeasurement.humidity,
          targetHumidity,
          HUM_DELTA_MAX
      );

  currentMeasurement.humidity =
      clampFloat(
          currentMeasurement.humidity,
          HUM_MIN,
          HUM_MAX
      );

  humidityTargetRemaining--;
}

// ======================================================
// Mise à jour gaz
// ======================================================

void updateGas() {

  bool targetReached =
      currentMeasurement.gasRaw ==
      targetGas;

  if (
      gasTargetRemaining <= 0 ||
      targetReached
  ) {

    chooseGasTarget();
  }

  currentMeasurement.gasRaw =
      moveIntToward(
          currentMeasurement.gasRaw,
          targetGas,
          GAS_DELTA_MAX
      );

  currentMeasurement.gasRaw =
      clampInt(
          currentMeasurement.gasRaw,
          GAS_MIN,
          GAS_MAX
      );

  gasTargetRemaining--;
}

// ======================================================
// Mise à jour présence
// ======================================================

void updatePresence() {

  // Une présence est déjà active
  if (presenceRemaining > 0) {

    currentMeasurement.presence =
        true;

    presenceRemaining--;

    return;
  }

  // Sinon aucune présence
  currentMeasurement.presence =
      false;

  // 10 % de chance qu'un nouvel événement
  // de présence commence
  int chance =
      random(0, 100);

  if (chance < 10) {

    // Présence pendant 3 à 8 mesures
    presenceRemaining =
        random(3, 9);

    currentMeasurement.presence =
        true;

    // La mesure actuelle compte déjà
    presenceRemaining--;
  }
}

// ======================================================
// Générer la prochaine mesure
// ======================================================

void generateNextMeasurement() {

  updateTemperature();
  updateHumidity();
  updateGas();
  updatePresence();
}

// ======================================================
// Reconnexion MQTT
// ======================================================

void reconnectMQTT() {

  while (!mqttClient.connected()) {

    Serial.println(
        "Tentative de connexion MQTTS..."
    );

    if (
        mqttClient.connect(
            "sentinel-esp32"
        )
    ) {

      Serial.println(
          "MQTTS connecté !"
      );

    } else {

      Serial.print(
          "Échec MQTTS, code : "
      );

      Serial.println(
          mqttClient.state()
      );

      Serial.println(
          "Nouvelle tentative dans 2 secondes..."
      );

      delay(2000);
    }
  }
}

// ======================================================
// Création et publication du JSON
// ======================================================

void publishMeasurement() {

  float deltaTemperature = 0.0;
  float deltaHumidity = 0.0;
  int deltaGas = 0;
  int presenceChange = 0;

  // ------------------------------------------------------
  // Calcul des variations
  // ------------------------------------------------------

  if (!firstMeasurement) {

    deltaTemperature =
        currentMeasurement.temperature -
        previousMeasurement.temperature;

    deltaHumidity =
        currentMeasurement.humidity -
        previousMeasurement.humidity;

    deltaGas =
        currentMeasurement.gasRaw -
        previousMeasurement.gasRaw;

    if (
        currentMeasurement.presence !=
        previousMeasurement.presence
    ) {

      presenceChange = 1;
    }
  }

  // IMPORTANT :
  // on prépare le prochain numéro,
  // mais on ne valide pas encore sampleCount.
  int nextSample =
      sampleCount + 1;

  // ------------------------------------------------------
  // Construction du JSON
  // ------------------------------------------------------

  String json = "{";

  json += "\"sample\":";
  json += String(nextSample);

  json += ",\"temperature\":";
  json += String(
      currentMeasurement.temperature,
      2
  );

  json += ",\"humidity\":";
  json += String(
      currentMeasurement.humidity,
      2
  );

  json += ",\"gas_raw\":";
  json += String(
      currentMeasurement.gasRaw
  );

  json += ",\"presence\":";

  if (currentMeasurement.presence) {

    json += "true";

  } else {

    json += "false";
  }

  json += ",\"delta_temp\":";
  json += String(
      deltaTemperature,
      2
  );

  json += ",\"delta_humidity\":";
  json += String(
      deltaHumidity,
      2
  );

  json += ",\"delta_gas\":";
  json += String(
      deltaGas
  );

  json += ",\"presence_change\":";
  json += String(
      presenceChange
  );

  json += "}";

  // ------------------------------------------------------
  // Publication MQTT robuste
  // ------------------------------------------------------

  bool published = false;

  while (!published) {

    // Vérifier la connexion avant chaque tentative
    if (!mqttClient.connected()) {

      Serial.println(
          "Connexion MQTTS perdue !"
      );

      reconnectMQTT();
    }

    // Tentative d'envoi
    published =
        mqttClient.publish(
            MQTT_TOPIC,
            json.c_str()
        );

    // Si la publication a échoué,
    // on garde EXACTEMENT le même JSON
    if (!published) {

      Serial.print(
          "Échec envoi sample "
      );

      Serial.println(
          nextSample
      );

      Serial.println(
          "Nouvelle tentative..."
      );

      delay(500);
    }
  }

  // ------------------------------------------------------
  // L'envoi a réussi
  // ------------------------------------------------------

  sampleCount =
      nextSample;

  Serial.println(json);

  // Seulement maintenant,
  // la mesure actuelle devient la précédente
  previousMeasurement =
      currentMeasurement;

  firstMeasurement =
      false;

  // ------------------------------------------------------
  // Fin après 500 mesures envoyées
  // ------------------------------------------------------

  if (sampleCount >= MAX_SAMPLES) {

    generationFinished =
        true;

    Serial.println();

    Serial.println(
        "=============================="
    );

    Serial.println(
        "500 mesures envoyées."
    );

    Serial.println(
        "Génération terminée."
    );

    Serial.println(
        "=============================="
    );
  }
}

// ======================================================
// SETUP
// ======================================================

void setup() {

  Serial.begin(115200);

  // Initialisation du hasard
  randomSeed(
      esp_random()
  );

  // ====================================================
  // Wi-Fi
  // ====================================================

  Serial.println(
      "Connexion au Wi-Fi..."
  );

  WiFi.begin(
      WIFI_SSID,
      WIFI_PASSWORD,
      6
  );

  while (
      WiFi.status() != WL_CONNECTED
  ) {

    delay(500);
    Serial.print(".");
  }

  Serial.println();

  Serial.println(
      "Wi-Fi connecté !"
  );

  Serial.print(
      "Adresse IP : "
  );

  Serial.println(
      WiFi.localIP()
  );

  // ====================================================
  // TLS
  // ====================================================

  espClient.setCACert(
      CA_CERT
  );

  // ====================================================
  // MQTT
  // ====================================================

  mqttClient.setServer(
      MQTT_SERVER,
      MQTT_PORT
  );

  // Taille suffisante pour le JSON
  mqttClient.setBufferSize(
      512
  );

  reconnectMQTT();

  // ====================================================
  // Générateur
  // ====================================================

  initializeGenerator();

  Serial.println();

  Serial.println(
      "Début de génération des 500 mesures..."
  );

  Serial.println(
      "Une mesure toutes les 200 ms."
  );

  Serial.println();
}

// ======================================================
// LOOP
// ======================================================

void loop() {

  // Maintenir la connexion MQTT
  if (!mqttClient.connected()) {

    Serial.println(
        "Connexion MQTTS perdue !"
    );

    reconnectMQTT();
  }

  mqttClient.loop();

  // Une fois les 500 lignes générées,
  // on ne génère plus rien
  if (generationFinished) {

    delay(1000);

    return;
  }

  // Première ligne
  if (firstMeasurement) {

    publishMeasurement();

  } else {

    generateNextMeasurement();

    publishMeasurement();
  }

  // 200 ms entre deux lignes
  delay(PUBLISH_INTERVAL);
}