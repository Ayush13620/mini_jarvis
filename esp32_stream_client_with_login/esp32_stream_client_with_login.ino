/*
  ESP32 -> Mini Jarvis Audio Stream Client (with Wi-Fi Login/Setup Page)

  What it adds:
  - If saved Wi-Fi is missing/invalid, ESP32 starts AP mode.
  - Open 192.168.4.1 to see a login page.
  - After login, configure Wi-Fi + server settings and save.
  - Settings are stored in NVS (Preferences) and used on next boot.

  Default setup portal credentials:
    username: admin
    password: jarvis123
*/

#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>

// ===== Audio stream settings =====
const int MIC_PIN = 34;
const int SAMPLE_DELAY_US = 47;    // ~16 kHz (analogRead ~15µs + delay ~47µs ≈ 62µs period)
const int FRAME_SAMPLES = 256;
// ================================

// Setup portal credentials (change if you want)
const char* SETUP_USER = "admin";
const char* SETUP_PASS_DEFAULT = "jarvis123";

// AP details for setup mode
const char* AP_SSID = "Jarvis-Setup";
const char* AP_PASS = "jarvissetup";
const char* PREF_NAMESPACE = "jarvis";
const uint32_t CONFIG_VERSION = 1;
const char* DEFAULT_SERVER_IP = "";
const uint16_t DEFAULT_SERVER_PORT = 5000;

Preferences prefs;
WebServer server(80);
WiFiClient client;

String wifiSsid;
String wifiPass;
String serverIp;
uint16_t serverPort = 5000;
String authToken;
String setupPass;

bool setupAuthed = false;
bool setupMode = false;

int32_t frameBuf[FRAME_SAMPLES];
unsigned long lastLevelLogMs = 0;
float micDc = 2048.0f;
unsigned long nextConnectAttemptMs = 0;
unsigned long reconnectDelayMs = 1000;

String htmlEscape(const String& s) {
  String out = s;
  out.replace("&", "&amp;");
  out.replace("<", "&lt;");
  out.replace(">", "&gt;");
  out.replace("\"", "&quot;");
  out.replace("'", "&#39;");
  return out;
}

String generateSetupPass() {
  uint64_t mac = ESP.getEfuseMac();
  uint32_t mix = (uint32_t)(mac ^ (mac >> 32) ^ 0xA5A5A5A5u);
  char buf[20];
  snprintf(buf, sizeof(buf), "jarv%08X", (unsigned int)mix);
  return String(buf);
}

String loginPage() {
  return String(
    "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Jarvis Setup Login</title>"
    "<style>body{font-family:Arial;padding:24px;max-width:420px;margin:auto;background:#f4f7fb}"
    ".card{background:#fff;padding:18px;border-radius:12px;box-shadow:0 4px 14px rgba(0,0,0,.08)}"
    "input{width:100%;padding:10px;margin:8px 0;border:1px solid #ccc;border-radius:8px}"
    "button{width:100%;padding:10px;border:0;border-radius:8px;background:#0b67ff;color:#fff;font-weight:700}"
    "</style></head><body><div class='card'><h2>Jarvis Setup Login</h2>"
    "<form method='POST' action='/login'>"
    "<input name='username' placeholder='Username' required>"
    "<input name='password' type='password' placeholder='Password' required>"
    "<button type='submit'>Login</button></form>"
    "<p style='font-size:12px;color:#555'>User is admin. Password shown on Serial at boot.</p>"
    "</div></body></html>"
  );
}

String configPage(const String& msg = "") {
  String safeSsid = htmlEscape(wifiSsid);
  String safePass = htmlEscape(wifiPass);
  String safeIp = htmlEscape(serverIp);
  String safeToken = htmlEscape(authToken);
  String safePort = String(serverPort);

  String html =
    "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Jarvis Config</title>"
    "<style>body{font-family:Arial;padding:20px;max-width:560px;margin:auto;background:#eef3ff}"
    ".card{background:#fff;padding:18px;border-radius:12px;box-shadow:0 4px 14px rgba(0,0,0,.08)}"
    "input{width:100%;padding:10px;margin:8px 0;border:1px solid #ccc;border-radius:8px}"
    "button{padding:10px 14px;border:0;border-radius:8px;background:#0b67ff;color:#fff;font-weight:700}"
    ".msg{color:#0a7a24;font-weight:700}</style></head><body><div class='card'>"
    "<h2>Mini Jarvis ESP32 Config</h2>";
  if (msg.length()) {
    html += "<p class='msg'>" + htmlEscape(msg) + "</p>";
  }
  html +=
    "<form method='POST' action='/save'>"
    "<label>Wi-Fi SSID</label><input name='wifi_ssid' value='" + safeSsid + "' required>"
    "<label>Wi-Fi Password</label><input name='wifi_pass' type='password' value='" + safePass + "' required>"
    "<label>Server IP</label><input name='server_ip' value='" + safeIp + "' required>"
    "<label>Server Port</label><input name='server_port' type='number' value='" + safePort + "' required>"
    "<label>AUTH Token (optional)</label><input name='auth_token' value='" + safeToken + "'>"
    "<button type='submit'>Save & Reboot</button></form>"
    "<form method='POST' action='/reset' style='margin-top:10px'>"
    "<button type='submit' style='background:#b91c1c'>Factory Reset Config</button></form>"
    "<p style='font-size:12px;color:#555'>After save, ESP32 restarts and connects automatically.</p>"
    "</div></body></html>";
  return html;
}

void applyDefaultConfig() {
  wifiSsid = "";
  wifiPass = "";
  serverIp = DEFAULT_SERVER_IP;
  serverPort = DEFAULT_SERVER_PORT;
  authToken = "";
  setupPass = SETUP_PASS_DEFAULT;
}

void printConfigToSerial() {
  Serial.println("----- Current Config -----");
  Serial.printf("wifi_ssid: %s\n", wifiSsid.c_str());
  Serial.printf("server_ip: %s\n", serverIp.c_str());
  Serial.printf("server_port: %u\n", serverPort);
  Serial.printf("auth_token_set: %s\n", authToken.length() ? "yes" : "no");
  Serial.printf("wifi_connected: %s\n", WiFi.status() == WL_CONNECTED ? "yes" : "no");
  Serial.printf("server_connected: %s\n", client.connected() ? "yes" : "no");
  Serial.printf("reconnect_delay_ms: %lu\n", reconnectDelayMs);
  Serial.println("--------------------------");
}

void factoryResetConfig() {
  prefs.begin(PREF_NAMESPACE, false);
  prefs.clear();
  prefs.end();
}

void loadConfig() {
  applyDefaultConfig();

  prefs.begin(PREF_NAMESPACE, false);
  uint32_t storedVersion = prefs.getUInt("cfg_ver", 0);
  if (storedVersion != CONFIG_VERSION) {
    // Schema/version mismatch: reset persisted config to avoid stale values.
    prefs.clear();
    prefs.putUInt("cfg_ver", CONFIG_VERSION);
    prefs.putString("setup_pass", generateSetupPass());
    prefs.end();
    return;
  }

  wifiSsid = prefs.getString("wifi_ssid", wifiSsid);
  wifiPass = prefs.getString("wifi_pass", wifiPass);
  serverIp = prefs.getString("server_ip", serverIp);
  serverPort = (uint16_t)prefs.getUInt("server_port", serverPort);
  authToken = prefs.getString("auth_token", authToken);
  setupPass = prefs.getString("setup_pass", setupPass);
  if (setupPass.length() < 8) {
    setupPass = generateSetupPass();
    prefs.putString("setup_pass", setupPass);
  }
  prefs.end();
}

void saveConfig(const String& ssid, const String& pass, const String& ip, uint16_t port, const String& token) {
  prefs.begin(PREF_NAMESPACE, false);
  prefs.putUInt("cfg_ver", CONFIG_VERSION);
  prefs.putString("wifi_ssid", ssid);
  prefs.putString("wifi_pass", pass);
  prefs.putString("server_ip", ip);
  prefs.putUInt("server_port", port);
  prefs.putString("auth_token", token);
  prefs.end();
}

void handleRoot() {
  if (!setupAuthed) {
    server.send(200, "text/html", loginPage());
    return;
  }
  server.send(200, "text/html", configPage());
}

void handleLogin() {
  String user = server.arg("username");
  String pass = server.arg("password");
  if (user == SETUP_USER && pass == setupPass) {
    setupAuthed = true;
    server.send(200, "text/html", configPage("Login successful"));
    return;
  }
  server.send(401, "text/html", loginPage());
}

void handleSave() {
  if (!setupAuthed) {
    server.send(403, "text/plain", "Forbidden");
    return;
  }

  String ssid = server.arg("wifi_ssid");
  String pass = server.arg("wifi_pass");
  String ip = server.arg("server_ip");
  String token = server.arg("auth_token");
  uint16_t port = (uint16_t)server.arg("server_port").toInt();
  if (ssid.length() == 0 || pass.length() == 0 || ip.length() == 0 || port == 0) {
    server.send(400, "text/html", configPage("Please fill all required fields"));
    return;
  }

  saveConfig(ssid, pass, ip, port, token);
  server.send(200, "text/html",
    "<html><body style='font-family:Arial;padding:20px'>Saved. Rebooting...</body></html>");
  delay(700);
  ESP.restart();
}

void handleReset() {
  if (!setupAuthed) {
    server.send(403, "text/plain", "Forbidden");
    return;
  }
  factoryResetConfig();
  server.send(200, "text/html",
    "<html><body style='font-family:Arial;padding:20px'>Config reset. Rebooting...</body></html>");
  delay(700);
  ESP.restart();
}

void startSetupPortal() {
  setupMode = true;
  setupAuthed = false;

  WiFi.mode(WIFI_AP);
  bool apOk = WiFi.softAP(AP_SSID, AP_PASS);
  if (!apOk) {
    Serial.println("Failed to start AP mode");
    return;
  }

  IPAddress ip = WiFi.softAPIP();
  Serial.printf("Setup AP started: %s\n", AP_SSID);
  Serial.printf("Connect and open: http://%s\n", ip.toString().c_str());
  Serial.printf("Setup login: %s / %s\n", SETUP_USER, setupPass.c_str());

  server.on("/", HTTP_GET, handleRoot);
  server.on("/login", HTTP_POST, handleLogin);
  server.on("/save", HTTP_POST, handleSave);
  server.on("/reset", HTTP_POST, handleReset);
  server.onNotFound([]() {
    if (!setupAuthed) {
      server.send(200, "text/html", loginPage());
    } else {
      server.send(200, "text/html", configPage());
    }
  });
  server.begin();
}

bool connectWiFiStation() {
  if (wifiSsid.length() == 0 || wifiPass.length() == 0) {
    return false;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  Serial.printf("Connecting Wi-Fi: %s\n", wifiSsid.c_str());
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("Wi-Fi connected, IP: %s\n", WiFi.localIP().toString().c_str());
    return true;
  }
  Serial.println("Wi-Fi connect failed");
  return false;
}

void connectServer() {
  if (client.connected()) return;
  if (serverIp.length() == 0 || serverPort == 0) return;
  unsigned long now = millis();
  if (now < nextConnectAttemptMs) return;

  Serial.printf("Connecting server %s:%u ...\n", serverIp.c_str(), serverPort);
  if (!client.connect(serverIp.c_str(), serverPort)) {
    Serial.println("Server connect failed");
    nextConnectAttemptMs = now + reconnectDelayMs;
    reconnectDelayMs = min(reconnectDelayMs * 2, 10000UL);
    Serial.printf("Retrying in %lu ms\n", reconnectDelayMs);
    return;
  }

  if (authToken.length() > 0) {
    client.print("AUTH ");
    client.print(authToken);
    client.print("\n");
  }

  client.setNoDelay(true);
  reconnectDelayMs = 1000;
  nextConnectAttemptMs = 0;
  Serial.println("Server connected");
}

void streamAudioFrame() {
  long absSum = 0;
  int minRaw = 4095;
  int maxRaw = 0;

  for (int i = 0; i < FRAME_SAMPLES; i++) {
    int raw = analogRead(MIC_PIN);      // 0..4095
    // Track slow-moving DC bias and remove it so voice energy is meaningful.
    micDc = (0.995f * micDc) + (0.005f * raw);
    int centered = (int)(raw - micDc);
    frameBuf[i] = (int32_t)centered;  // send as-is; Python PCM_INT32_GAIN_DIV=1
    absSum += abs(centered);
    if (raw < minRaw) minRaw = raw;
    if (raw > maxRaw) maxRaw = raw;
    delayMicroseconds(SAMPLE_DELAY_US);
  }

  unsigned long now = millis();
  if (now - lastLevelLogMs >= 1000) {
    int avgAbs = (int)(absSum / FRAME_SAMPLES);
    int p2p = maxRaw - minRaw;
    Serial.printf("Mic level avgAbs=%d p2p=%d\n", avgAbs, p2p);
    lastLevelLogMs = now;
  }

  size_t want = sizeof(frameBuf);
  size_t sent = client.write((const uint8_t*)frameBuf, want);
  if (sent != want) {
    Serial.println("Partial send/disconnect");
    client.stop();
    nextConnectAttemptMs = millis() + reconnectDelayMs;
    reconnectDelayMs = min(reconnectDelayMs * 2, 10000UL);
  }
}

void setup() {
  Serial.begin(115200);
  delay(250);
  analogReadResolution(12);
  analogSetPinAttenuation(MIC_PIN, ADC_11db);  // full 0–3.3V range; default 0dB clips at 1.1V

  loadConfig();
  printConfigToSerial();
  Serial.println("Serial commands: RESETCFG | SHOWCFG");
  Serial.printf("Setup login user/pass: %s / %s\n", SETUP_USER, setupPass.c_str());
  bool ok = connectWiFiStation();
  if (!ok) {
    startSetupPortal();
  }
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();
    if (cmd == "RESETCFG") {
      Serial.println("Resetting config and rebooting...");
      factoryResetConfig();
      delay(200);
      ESP.restart();
    } else if (cmd == "SHOWCFG") {
      printConfigToSerial();
    } else if (cmd == "STATUS") {
      printConfigToSerial();
    }
  }

  if (setupMode) {
    server.handleClient();
    delay(4);
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    if (!connectWiFiStation()) {
      startSetupPortal();
      return;
    }
  }

  if (!client.connected()) {
    connectServer();
    return;
  }

  streamAudioFrame();
}
