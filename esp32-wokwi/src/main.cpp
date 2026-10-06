#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include "DHTesp.h"
#include "ca_cert.h"

// --------------------
// Configuration Wi-Fi
// --------------------
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// --------------------
// Configuration MQTT sécurisé
// --------------------
const char* MQTT_SERVER = "host.wokwi.internal";
const int MQTT_PORT = 8883;
const char* MQTT_TOPIC = "sentinel/sensors";

WiFiClientSecure espClient;
PubSubClient mqttClient(espClient);

// --------------------
// Broches des capteurs
// --------------------
const int DHT_PIN = 15;
const int MQ2_PIN = 34;
const int PIR_PIN = 27;

DHTesp dhtSensor;

void setup() {
  Serial.begin(115200);

  dhtSensor.setup(DHT_PIN, DHTesp::DHT22);
  pinMode(PIR_PIN, INPUT);

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

  // Le certificat public du CA sert à vérifier Mosquitto
  espClient.setCACert(CA_CERT);

  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);

  Serial.println("Connexion sécurisée au broker MQTT...");

  while (!mqttClient.connected()) {
    if (mqttClient.connect("sentinel-esp32")) {
      Serial.println("MQTTS connecté !");
    } else {
      Serial.print("Échec MQTTS, code : ");
      Serial.println(mqttClient.state());
      delay(1000);
    }
  }
}

void loop() {
  mqttClient.loop();

  TempAndHumidity data = dhtSensor.getTempAndHumidity();
  int gasValue = analogRead(MQ2_PIN);

  int pirValue = digitalRead(PIR_PIN);
  bool presence = (pirValue == HIGH);

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

  Serial.println(json);

  mqttClient.publish(MQTT_TOPIC, json.c_str());

  delay(2000);
}
