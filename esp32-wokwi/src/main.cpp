#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include "DHTesp.h"

// --------------------
// Configuration Wi-Fi
// --------------------
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// --------------------
// Configuration MQTT
// --------------------
const char* MQTT_SERVER = "host.wokwi.internal";
const int MQTT_PORT = 1883;
const char* MQTT_TOPIC = "sentinel/sensors";

// Client réseau + client MQTT
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// --------------------
// Broches des capteurs
// --------------------
const int DHT_PIN = 15;
const int MQ2_PIN = 34;
const int PIR_PIN = 27;

// Capteur DHT22
DHTesp dhtSensor;

void setup() {

  // --------------------
  // Communication série
  // --------------------
  Serial.begin(115200);

  // --------------------
  // Initialisation capteurs
  // --------------------

  // DHT22
  dhtSensor.setup(DHT_PIN, DHTesp::DHT22);

  // PIR
  pinMode(PIR_PIN, INPUT);

  // --------------------
  // Connexion au Wi-Fi
  // --------------------
  Serial.println("Connexion au Wi-Fi...");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("Wi-Fi connecté !");

  Serial.print("Adresse IP : ");
  Serial.println(WiFi.localIP());

  // --------------------
  // Configuration MQTT
  // --------------------
  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);

  Serial.println("Connexion au broker MQTT...");

  while (!mqttClient.connected()) {

    if (mqttClient.connect("sentinel-esp32")) {

      Serial.println("MQTT connecté !");

    } else {

      Serial.print("Échec MQTT, code : ");
      Serial.println(mqttClient.state());

      delay(1000);
    }
  }
}

void loop() {

  // --------------------
  // Maintenir MQTT actif
  // --------------------
  mqttClient.loop();

  // --------------------
  // 1. Lecture DHT22
  // --------------------
  TempAndHumidity data = dhtSensor.getTempAndHumidity();

  // --------------------
  // 2. Lecture MQ-2
  // --------------------
  int gasValue = analogRead(MQ2_PIN);

  // --------------------
  // 3. Lecture PIR
  // --------------------
  int pirValue = digitalRead(PIR_PIN);

  bool presence = (pirValue == HIGH);

  // --------------------
  // 4. Construction JSON
  // --------------------
  String json = "{";

  json += "\"temperature\":";
  json += String(data.temperature, 2);

  json += ",\"humidity\":";
  json += String(data.humidity, 2);

  json += ",\"gas\":";
  json += String(gasValue);

  json += ",\"presence\":";

  if (presence) {
    json += "true";
  } else {
    json += "false";
  }

  json += "}";

  // --------------------
  // 5. Affichage JSON
  // --------------------
  Serial.println(json);

  // --------------------
  // 6. Publication MQTT
  // --------------------
  mqttClient.publish(MQTT_TOPIC, json.c_str());

  // Attendre 2 secondes
  delay(2000);
}