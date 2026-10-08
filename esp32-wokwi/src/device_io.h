#pragma once
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHTesp.h>

// Broches de la simulation ESP32 fournie dans diagram.json.
constexpr int LED_PIN = 25;
constexpr int LINK_LED_PIN = 33;
constexpr int BUZZER_PIN = 26;
constexpr int DHT_PIN = 15;
constexpr int GAS_PIN = 34;
constexpr int PIR_PIN = 27;
const char* COMMAND_TOPIC = "sentinel/commands";
const char* STATE_TOPIC = "sentinel/device/state";
Adafruit_SSD1306 display(128, 64, &Wire, -1);
DHTesp dht;
bool oledReady = false;
bool ledEnabled = false;
bool buzzerEnabled = false;
unsigned long buzzerUntil = 0;
unsigned long lastHeartbeat = 0;
unsigned long lastDisplay = 0;
String recentCommandIds[8];
unsigned int recentCommandIndex = 0;

void publishDeviceState(const String& id = "", const char* status = "executed",
                        const char* detail = "") {
  if (!mqttClient.connected()) return;
  JsonDocument doc;
  doc["kind"] = id.length() ? "ack" : "state";
  if (id.length()) {
    doc["id"] = id;
    doc["status"] = status;
    doc["detail"] = detail;
  }
  doc["led"] = ledEnabled;
  doc["buzzer"] = buzzerEnabled;
  doc["data_mode"] = USE_GENERATED_DATA ? "generated" : "sensors";
  doc["oled"] = oledReady;
  String payload;
  serializeJson(doc, payload);
  mqttClient.publish(STATE_TOPIC, payload.c_str(), false);
}

void commandCallback(char* topic, byte* payload, unsigned int length) {
  if (strcmp(topic, COMMAND_TOPIC) != 0 || length > 512) return;
  JsonDocument doc;
  if (deserializeJson(doc, payload, length)) return;
  String id = doc["id"] | "";
  String action = doc["action"] | "";
  if (id.length() != 36) return;
  for (const auto& seen : recentCommandIds) {
    if (seen == id) {
      publishDeviceState(id, "executed", "Commande deja traitee.");
      return;
    }
  }
  // Expiration vérifiée par le bridge avant publication non retenue.
  // Ne pas comparer l'heure NTP de Wokwi à la date du PC.
  long ttl = doc["ttl_ms"] | 0L;
  if (ttl <= 0 || ttl > 30000) {
    publishDeviceState(id, "rejected", "Validite de commande invalide.");
    return;
  }
  if (action == "led_on" || action == "led_off") {
    ledEnabled = action == "led_on";
    digitalWrite(LED_PIN, ledEnabled ? HIGH : LOW);
  } else if (action == "buzzer_on") {
    unsigned int duration = doc["duration_ms"] | 2000;
    if (duration < 100 || duration > 2000) {
      publishDeviceState(id, "rejected", "Duree buzzer invalide.");
      return;
    }
    tone(BUZZER_PIN, 2000, duration);
    buzzerEnabled = true;
    buzzerUntil = millis() + duration;
  } else if (action == "buzzer_off") {
    noTone(BUZZER_PIN);
    buzzerEnabled = false;
  } else {
    publishDeviceState(id, "rejected", "Action inconnue.");
    return;
  }
  recentCommandIds[recentCommandIndex++ % 8] = id;
  Serial.println("Commande executee : " + action);
  publishDeviceState(id);
}

void initializeDeviceIO() {
  pinMode(LED_PIN, OUTPUT);
  pinMode(LINK_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(PIR_PIN, INPUT);
  digitalWrite(LED_PIN, LOW);
  digitalWrite(LINK_LED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);
  dht.setup(DHT_PIN, DHTesp::DHT22);
  analogReadResolution(12);
  Wire.begin(21, 22);
  oledReady = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (!oledReady) Serial.println("OLED absent : verifier le cablage I2C.");
}

void serviceDeviceIO() {
  digitalWrite(LINK_LED_PIN, mqttClient.connected() ? HIGH : LOW);
  if (buzzerEnabled && (long)(millis() - buzzerUntil) >= 0) {
    noTone(BUZZER_PIN);
    buzzerEnabled = false;
    publishDeviceState();
  }
  if (oledReady && millis() - lastDisplay >= 500) {
    lastDisplay = millis();
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println("SENTINEL-X");
    display.println(WiFi.status() == WL_CONNECTED ? "WiFi : OK" : "WiFi : attente");
    display.println(WiFi.localIP());
    display.println(mqttClient.connected() ? "MQTTS : OK" : "MQTTS : attente");
    display.println(USE_GENERATED_DATA ? "Donnees generees" : "Capteurs Wokwi");
    display.print("LED:"); display.print(ledEnabled ? "ON" : "OFF");
    display.print(" BUZ:"); display.println(buzzerEnabled ? "ON" : "OFF");
    display.display();
  }
  if (millis() - lastHeartbeat >= 2000) {
    lastHeartbeat = millis();
    publishDeviceState();
  }
}

void waitWithIO(unsigned long duration) {
  unsigned long start = millis();
  while (millis() - start < duration) {
    mqttClient.loop();
    serviceDeviceIO();
    delay(5);
  }
}
