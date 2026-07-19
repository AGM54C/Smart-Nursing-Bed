/**
 * 智能护理病床 - ESP32 传感器节点主程序
 *
 * 功能:
 *   1. 初始化所有传感器 (MAX30102/MLX90614/MPU6050/Velostat/HK-2000B+)
 *   2. 连接WiFi → 连接树莓派Mosquitto MQTT Broker
 *   3. 定时采集 → MQTT发布到对应Topic
 *   4. 订阅控制命令Topic
 *
 * 硬件: ESP32-S3-N16R8 (USB-C, 16MB Flash, 8MB PSRAM)
 * 框架: Arduino (PlatformIO)
 */

#include "config.h"
#include <Arduino.h>
#include <ArduinoJson.h>
#include <Wire.h>

// ─── 外部函数声明 ───

// mqtt_client.cpp
extern void mqtt_init();
extern void mqtt_loop();
extern bool mqtt_publish(const char *topic, const char *payload);
extern bool mqtt_publish_quiet(const char *topic, const char *payload);
extern void mqtt_set_cmd_callback(void (*cb)(const char *, const char *));
extern bool mqtt_is_connected();
extern bool wifi_is_connected();

// sensor_max30102.cpp
extern bool max30102_init();
extern bool max30102_update();
extern bool max30102_measure_spo2();
extern int max30102_get_heart_rate();
extern int max30102_get_spo2();
extern bool max30102_has_finger();
extern bool max30102_is_ok();

// sensor_mlx90614.cpp
extern bool mlx90614_init();
extern float mlx90614_get_object_temp();
extern float mlx90614_get_ambient_temp();
extern bool mlx90614_is_ok();

// sensor_mpu6050.cpp
extern bool mpu6050_init();
extern void mpu6050_update();
extern const char *mpu6050_get_posture();
extern int mpu6050_get_movement();
extern bool mpu6050_is_ok();

// sensor_pressure_mat.cpp
extern bool pressure_mat_init();
extern void pressure_mat_scan();
extern uint32_t pressure_mat_get_total();
extern bool pressure_mat_is_occupied();
extern void pressure_mat_to_json(char *buf, size_t bufSize);
extern bool pressure_mat_is_ok();

// sensor_pulse.cpp
extern bool pulse_sensor_init();
extern void pulse_sensor_sample();
extern void pulse_estimate_bp();
extern float pulse_get_bpm();
extern int pulse_get_sys();
extern int pulse_get_dia();
extern bool pulse_has_signal();
extern bool pulse_is_formal_bp();

// ─── 定时器 ───
static unsigned long lastVitalsTime = 0;
static unsigned long lastPressureTime = 0;
static unsigned long lastPulseEstTime = 0;
static unsigned long lastBatteryTime = 0;
static unsigned long lastSpo2Time = 0;

// ─── LED指示 (LED_PIN from config.h) ───

// ─── 命令回调 ───
void onCommand(const char *topic, const char *payload) {
  Serial.printf("📩 CMD [%s]: %s\n", topic, payload);

  // 可扩展: 解析命令执行对应操作
  // 比如远程切换采集间隔、触发校准等
}

// ─── 发布体征数据 ───
void publishVitals() {
  JsonDocument doc;
  doc["patient_id"] = PATIENT_ID;

  // 心率
  int hr = max30102_get_heart_rate();
  if (hr > 0)
    doc["heart_rate"] = hr;

  // 血氧
  int spo2 = max30102_get_spo2();
  if (spo2 > 0)
    doc["blood_oxygen"] = spo2;

  // 体温
  float temp = mlx90614_get_object_temp();
  if (temp > 0)
    doc["temperature"] = serialized(String(temp, 1));

  // 睡姿
  mpu6050_update();
  const char *posture = mpu6050_get_posture();
  doc["sleep_posture"] = posture;

  // 体动强度
  doc["movement"] = mpu6050_get_movement();

  // 血压 (估算或正式传感器)
  if (pulse_has_signal()) {
    pulse_estimate_bp();
    int sys = pulse_get_sys();
    int dia = pulse_get_dia();
    if (sys > 0 && dia > 0) {
      doc["blood_pressure_sys"] = sys;
      doc["blood_pressure_dia"] = dia;
      doc["bp_source"] = pulse_is_formal_bp() ? "formal" : "estimated";
    }
  }

  // 序列化并发布
  char payload[512];
  serializeJson(doc, payload, sizeof(payload));
  mqtt_publish(TOPIC_VITALS, payload);
}

// ─── 发布压力矩阵 ───
void publishPressureMat() {
  pressure_mat_scan();

  // 构建JSON: {"patient_id":1, "grid":[[...],[...],...], "occupied":true,
  // "total":12345}
  char gridJson[1500];
  pressure_mat_to_json(gridJson, sizeof(gridJson));

  char payload[1800];
  snprintf(payload, sizeof(payload),
           "{\"patient_id\":%d,\"grid\":%s,\"occupied\":%s,\"total\":%lu}",
           PATIENT_ID, gridJson, pressure_mat_is_occupied() ? "true" : "false",
           pressure_mat_get_total());

  mqtt_publish(TOPIC_PRESSURE_MAT, payload);
}

// ─── 发布电池电压 ───
void publishBattery() {
  uint16_t raw = analogRead(BATTERY_ADC_PIN);
  float voltage = raw * 3.3 / 4095.0 * (BATTERY_R1 + BATTERY_R2) / BATTERY_R2;
  int percent = (int)((voltage - BATTERY_EMPTY_V) /
                      (BATTERY_FULL_V - BATTERY_EMPTY_V) * 100);
  if (percent < 0)
    percent = 0;
  if (percent > 100)
    percent = 100;

  char payload[64];
  snprintf(payload, sizeof(payload), "{\"voltage\":%.1f,\"percent\":%d}",
           voltage, percent);
  mqtt_publish(TOPIC_BATTERY, payload);
}

// ═══════════════════════════════════════════
//  Arduino Setup
// ═══════════════════════════════════════════
void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1000);

  Serial.println();
  Serial.println("╔══════════════════════════════════════════╗");
  Serial.println("║  🛏️ 智能护理病床 - ESP32传感器节点        ║");
  Serial.println("╚══════════════════════════════════════════╝");

  // LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // I2C 初始化 (降到 100kHz 标准模式,更稳定)
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(100000); // 100kHz Standard Mode
  Serial.println("[I2C] Bus initialized at 100kHz");
  delay(100); // 让总线稳定

  // 初始化各传感器 (MLX90614 最先初始化,避免其他库干扰 I2C)
  Serial.println("─── Initializing sensors ───");
  mlx90614_init();
  delay(50);
  max30102_init();
  delay(50);
  mpu6050_init();
  delay(50);
  pressure_mat_init();
  pulse_sensor_init();

  // 打印传感器状态
  Serial.println("─── Sensor Status ───");
  Serial.printf("  MAX30102 (HR/SpO2): %s\n", max30102_is_ok() ? "✅" : "❌");
  Serial.printf("  MLX90614 (Temp):    %s\n", mlx90614_is_ok() ? "✅" : "❌");
  Serial.printf("  MPU6050 (Posture):  %s\n", mpu6050_is_ok() ? "✅" : "❌");
  Serial.printf("  Pressure Mat:       %s\n",
                pressure_mat_is_ok() ? "✅" : "❌");
  Serial.printf("  Pulse (BP):         %s (%s)\n", "✅",
                pulse_is_formal_bp() ? "Formal BP Sensor"
                                     : "HK-2000B+ Estimated");

  // 初始化MQTT
  Serial.println("─── Connecting MQTT ───");
  mqtt_init();
  mqtt_set_cmd_callback(onCommand);

  // 初始化定时器
  lastVitalsTime = millis();
  lastPressureTime = millis();
  lastBatteryTime = millis();
  lastSpo2Time = millis();
  lastPulseEstTime = millis();

  Serial.println("═══ System Ready ═══\n");
  digitalWrite(LED_PIN, HIGH);
}

// ═══════════════════════════════════════════
//  Arduino Loop
// ═══════════════════════════════════════════
void loop() {
  unsigned long now = millis();

  // MQTT维护 (WiFi重连+MQTT重连+消息处理)
  mqtt_loop();

  // 高频: MAX30102心率检测 (需要持续调用以积累心跳数据)
  max30102_update();

  // 高频: 脉搏波采样 (每2ms一次)
  static unsigned long lastPulseSample = 0;
  if (now - lastPulseSample >= 2) {
    pulse_sensor_sample();
    lastPulseSample = now;
  }

  // 高频: 呼吸微动采样 (4Hz发布压力总和, 树莓派FFT提取呼吸率)
  static unsigned long lastBreathTime = 0;
  if (now - lastBreathTime >= BREATH_INTERVAL) {
    pressure_mat_scan();
    char breathPayload[48];
    snprintf(breathPayload, sizeof(breathPayload), "{\"t\":%lu,\"v\":%lu}",
             now, (unsigned long)pressure_mat_get_total());
    mqtt_publish_quiet(TOPIC_BREATH, breathPayload);
    lastBreathTime = now;
  }

  // 定时: 发布体征数据
  if (now - lastVitalsTime >= VITALS_INTERVAL) {
    publishVitals();
    lastVitalsTime = now;
    // LED闪烁表示活动
    digitalWrite(LED_PIN, !digitalRead(LED_PIN));
  }

  // 定时: 发布压力矩阵
  if (now - lastPressureTime >= PRESSURE_INTERVAL) {
    publishPressureMat();
    lastPressureTime = now;
  }

  // 定时: SpO2完整测量 (每60秒, 因为需要阻塞4秒)
  if (now - lastSpo2Time >= 60000) {
    max30102_measure_spo2();
    lastSpo2Time = now;
  }

  // 定时: 电池电压
  if (now - lastBatteryTime >= BATTERY_INTERVAL) {
    publishBattery();
    lastBatteryTime = now;
  }

  // 极小延时, 让出CPU给WiFi/MQTT任务
  delay(1);
}
