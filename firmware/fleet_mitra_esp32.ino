/* FleetMitra: FUTURE HARDWARE EXAMPLE — NOT PHYSICALLY TESTED.
 * Arduino IDE: ESP32 board support + TinyGPSPlus library are required.
 * GPS TX -> GPIO16 (ESP32 RX2); GPS RX -> GPIO17 (ESP32 TX2, optional).
 * Shared GND. Power the breakout per its own datasheet. ESP32 UART is 3.3V.
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <TinyGPSPlus.h>

const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
// Set your LAPTOP'S LAN IP here. localhost would refer to the ESP32 itself.
const char* LOCATION_URL = "http://192.168.1.100:5000/api/locations";

HardwareSerial gpsSerial(2);
TinyGPSPlus gps;
unsigned long lastSend = 0;
unsigned long lastReconnect = 0;
String lastAcceptedTimestamp;

void setup() {
  Serial.begin(115200);
  gpsSerial.setRxBufferSize(2048);
  gpsSerial.begin(9600, SERIAL_8N1, 16, 17);  // RX, TX; adapt pins to your board.
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println("FleetMitra FM01 | HARDWARE | Firmware physically untested");
}

void loop() {
  while (gpsSerial.available()) gps.encode(gpsSerial.read());
  unsigned long now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if (now - lastReconnect >= 10000) {
      lastReconnect = now;
      WiFi.reconnect();
      Serial.println("Waiting for Wi-Fi...");
    }
    return;
  }
  if (now - lastSend < 3000) return;
  lastSend = now;
  if (!gps.location.isValid() || gps.location.age() > 5000 ||
      !gps.date.isValid() || !gps.time.isValid() || gps.time.age() > 5000 ||
      gps.date.year() < 2020) {
    Serial.println("Waiting for a fresh GPS fix and UTC date/time...");
    return;
  }
  char timestamp[25];
  snprintf(timestamp, sizeof(timestamp), "%04d-%02d-%02dT%02d:%02d:%02dZ",
           gps.date.year(), gps.date.month(), gps.date.day(),
           gps.time.hour(), gps.time.minute(), gps.time.second());
  if (lastAcceptedTimestamp == timestamp) return;
  String speed = gps.speed.isValid() && gps.speed.age() < 5000 ? String(gps.speed.kmph(), 2) : "null";
  String payload = "{\"vehicle_id\":\"FM01\",\"lat\":" + String(gps.location.lat(), 7) +
                   ",\"lon\":" + String(gps.location.lng(), 7) +
                   ",\"timestamp\":\"" + String(timestamp) + "\",\"speed_kmh\":" + speed +
                   ",\"gps_valid\":true,\"source\":\"HARDWARE\"}";
  HTTPClient http;
  http.setConnectTimeout(1500);
  http.setTimeout(2500);
  if (http.begin(LOCATION_URL)) {
    http.addHeader("Content-Type", "application/json");
    int status = http.POST(payload);
    Serial.printf("POST /api/locations -> %d\n", status);
    Serial.println(http.getString());
    if (status == 200 || status == 201) lastAcceptedTimestamp = timestamp;
    http.end();
  }
}
