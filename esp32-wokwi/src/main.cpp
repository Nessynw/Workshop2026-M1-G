
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include "DHTesp.h"
#include "ca_cert.h"

    // --------------------
    // Configuration Wi-Fi
    // --------------------
    const char *WIFI_SSID = "Wokwi-GUEST";
const char *WIFI_PASSWORD = "";

// --------------------
// Configuration MQTT sécurisé
// --------------------
const char *MQTT_SERVER = "host.wokwi.internal";
const int MQTT_PORT = 8883;

const char *MQTT_TOPIC = "sentinel/sensors/readings";

// --------------------
// Authentification MQTT
// --------------------
const char *MQTT_USERNAME = "sentinel";
const char *MQTT_PASSWORD = "massiva";

// --------------------
// Client TLS
// --------------------
WiFiClientSecure espClient;

// --------------------
// Client MQTT
// --------------------
PubSubClient mqttClient(espClient);

// --------------------
// Broches des capteurs
// --------------------
const int DHT_PIN = 15;
const int MQ2_PIN = 34;
const int PIR_PIN = 27;

DHTesp dhtSensor;

// ==================================================
// Fonction de connexion / reconnexion MQTT
// ==================================================
void reconnectMQTT()
{
  while (!mqttClient.connected())
  {
    Serial.println("Tentative de connexion MQTTS...");

    if (mqttClient.connect(
            "sentinel-esp32",
            MQTT_USERNAME,
            MQTT_PASSWORD))
    {
      Serial.println("MQTTS connecté avec authentification !");
    }
    else
    {
      Serial.print("Échec MQTTS, code : ");
      Serial.println(mqttClient.state());

      Serial.println("Nouvelle tentative dans 2 secondes...");

      delay(2000);
    }
  }
}

// ==================================================
// SETUP
// ==================================================
void setup()
{
  Serial.begin(115200);

  // --------------------
  // Configuration capteurs
  // --------------------
  dhtSensor.setup(DHT_PIN, DHTesp::DHT22);
  pinMode(PIR_PIN, INPUT);

  // --------------------
  // Connexion Wi-Fi
  // --------------------
  Serial.println("Connexion au Wi-Fi...");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);

  while (WiFi.status() != WL_CONNECTED)
  {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("Wi-Fi connecté !");
  Serial.print("Adresse IP : ");
  Serial.println(WiFi.localIP());

  // --------------------
  // Configuration TLS
  // --------------------
  espClient.setCACert(CA_CERT);

  // --------------------
  // Configuration MQTT
  // --------------------
  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);

  // --------------------
  // Première connexion MQTT
  // --------------------
  reconnectMQTT();
}

// ==================================================
// LOOP
// ==================================================
void loop()
{
  // --------------------
  // Vérification connexion MQTT
  // --------------------
  if (!mqttClient.connected())
  {
    Serial.println("Connexion MQTTS perdue !");
    reconnectMQTT();
  }

  mqttClient.loop();

  // --------------------
  // Lecture des capteurs
  // --------------------
  TempAndHumidity data = dhtSensor.getTempAndHumidity();

  int gasValue = analogRead(MQ2_PIN);

  int pirValue = digitalRead(PIR_PIN);
  bool presence = (pirValue == HIGH);

  // --------------------
  // Création du JSON
  // --------------------
  String json = "{";

  json += "\"temperature\":";
  json += String(data.temperature, 2);

  json += ",\"humidity\":";
  json += String(data.humidity, 2);

  json += ",\"gas_raw\":";
  json += String(gasValue);

  json += ",\"pir\":";

  if (presence)
  {
    json += "true";
  }
  else
  {
    json += "false";
  }

  json += "}";

  // --------------------
  // Affichage local
  // --------------------
  Serial.println(json);

  // --------------------
  // Publication MQTT + TLS
  // --------------------
  bool published = mqttClient.publish(
      MQTT_TOPIC,
      json.c_str());

  if (published)
  {
    Serial.println(
        "Mesure envoyée en MQTT + TLS + authentification.");
  }
  else
  {
    Serial.println("Échec de publication MQTT.");
  }

  // --------------------
  // Attente avant prochaine mesure
  // --------------------
  delay(2000);
}

