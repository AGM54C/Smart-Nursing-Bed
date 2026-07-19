/**
 * 智能护理病床 - ESP32 MQTT客户端
 *
 * 连接树莓派Mosquitto Broker，发布传感器数据，订阅控制命令
 */

#include "config.h"
#include <PubSubClient.h>
#include <WiFi.h>


WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

// ─── 回调声明 ───
typedef void (*MqttCallback)(const char *topic, const char *payload);
static MqttCallback _cmdCallback = nullptr;

// ─── WiFi 连接 ───
bool wifi_connect() {
  if (WiFi.status() == WL_CONNECTED)
    return true;

  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < WIFI_MAX_RETRIES) {
    delay(WIFI_RETRY_DELAY);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Connected! IP: %s\n",
                  WiFi.localIP().toString().c_str());
    return true;
  } else {
    Serial.println("\n[WiFi] Connection FAILED!");
    return false;
  }
}

// ─── MQTT 内部回调 ───
static void mqtt_internal_callback(char *topic, byte *payload,
                                   unsigned int length) {
  char msg[512];
  unsigned int len = (length < sizeof(msg) - 1) ? length : sizeof(msg) - 1;
  memcpy(msg, payload, len);
  msg[len] = '\0';

#if DEBUG_PRINT
  Serial.printf("[MQTT] Received %s: %s\n", topic, msg);
#endif

  if (_cmdCallback) {
    _cmdCallback(topic, msg);
  }
}

// ─── MQTT 连接 ───
bool mqtt_connect() {
  if (mqttClient.connected())
    return true;

  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqtt_internal_callback);
  mqttClient.setBufferSize(2048); // 压力矩阵数据较大

  Serial.printf("[MQTT] Connecting to %s:%d...\n", MQTT_BROKER, MQTT_PORT);

  bool connected;
  if (strlen(MQTT_USER) > 0) {
    connected = mqttClient.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS);
  } else {
    connected = mqttClient.connect(MQTT_CLIENT_ID);
  }

  if (connected) {
    Serial.println("[MQTT] Connected!");
    // 订阅命令Topic
    mqttClient.subscribe(TOPIC_CMD);
    Serial.printf("[MQTT] Subscribed to %s\n", TOPIC_CMD);
    return true;
  } else {
    Serial.printf("[MQTT] Failed, rc=%d. Retry in %dms\n", mqttClient.state(),
                  MQTT_RETRY_DELAY);
    return false;
  }
}

// ─── 初始化 ───
void mqtt_init() {
  wifi_connect();
  mqtt_connect();
}

// ─── 循环维护 (在loop中调用) ───
void mqtt_loop() {
  // WiFi重连
  if (WiFi.status() != WL_CONNECTED) {
    wifi_connect();
  }

  // MQTT重连
  if (!mqttClient.connected()) {
    mqtt_connect();
  }

  mqttClient.loop();
}

// ─── 发布消息 ───
bool mqtt_publish(const char *topic, const char *payload) {
  if (!mqttClient.connected()) {
    if (!mqtt_connect())
      return false;
  }

  bool ok = mqttClient.publish(topic, payload);
#if DEBUG_PRINT
  if (ok) {
    Serial.printf("[MQTT] Published to %s (%d bytes)\n", topic,
                  strlen(payload));
  } else {
    Serial.printf("[MQTT] Publish FAILED to %s\n", topic);
  }
#endif
  return ok;
}

// ─── 发布消息 (静默版: 高频话题用, 不刷串口/不阻塞重连) ───
bool mqtt_publish_quiet(const char *topic, const char *payload) {
  if (!mqttClient.connected())
    return false;
  return mqttClient.publish(topic, payload);
}

// ─── 设置命令回调 ───
void mqtt_set_cmd_callback(MqttCallback cb) { _cmdCallback = cb; }

// ─── 状态查询 ───
bool mqtt_is_connected() { return mqttClient.connected(); }

bool wifi_is_connected() { return WiFi.status() == WL_CONNECTED; }
