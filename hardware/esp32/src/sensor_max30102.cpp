/**
 * 智能护理病床 - MAX30102 心率血氧传感器
 */

#include "MAX30105.h" // SparkFun库
#include "config.h"
#include "heartRate.h"      // 峰值检测算法
#include "spo2_algorithm.h" // SpO2算法
#include <Wire.h>


static MAX30105 max30102;
static bool max30102_ok = false;

// 心率计算相关
static const byte RATE_SIZE = 4;
static byte rates[RATE_SIZE];
static byte rateSpot = 0;
static long lastBeat = 0;
static float beatsPerMinute = 0;
static int beatAvg = 0;

// SpO2相关
static uint32_t irBuffer[100];
static uint32_t redBuffer[100];
static int32_t spo2Value = 0;
static int8_t spo2Valid = 0;
static int32_t heartRateValue = 0;
static int8_t heartRateValid = 0;

bool max30102_init() {
  if (!max30102.begin(Wire, I2C_SPEED_FAST, MAX30102_ADDR)) {
    Serial.println("[MAX30102] NOT FOUND! Check wiring.");
    max30102_ok = false;
    return false;
  }

  // 配置传感器
  max30102.setup(60, // LED亮度 (0-255)
                 4,  // 采样平均 (1,2,4,8,16,32)
                 2, // LED模式 (1=仅红光, 2=红光+红外, 3=红光+红外+绿光)
                 100, // 采样率 (50,100,200,400,800,1000,1600,3200)
                 411, // 脉宽 (69,118,215,411)
                 4096 // ADC范围 (2048,4096,8192,16384)
  );

  max30102.setPulseAmplitudeRed(0x0A); // 指示灯微亮
  max30102.setPulseAmplitudeGreen(0);  // 关闭绿灯

  max30102_ok = true;
  Serial.println("[MAX30102] Initialized OK");
  return true;
}

/**
 * 快速读取心率 (在loop中频繁调用以积累数据)
 * 返回true表示有新的有效心跳
 */
bool max30102_update() {
  if (!max30102_ok)
    return false;

  long irValue = max30102.getIR();

  // 检测是否有手指放上
  if (irValue < 50000) {
    // 没有检测到手指
    beatAvg = 0;
    return false;
  }

  if (checkForBeat(irValue)) {
    long delta = millis() - lastBeat;
    lastBeat = millis();
    beatsPerMinute = 60.0 / (delta / 1000.0);

    if (beatsPerMinute > 20 && beatsPerMinute < 255) {
      rates[rateSpot++ % RATE_SIZE] = (byte)beatsPerMinute;

      // 计算平均心率
      beatAvg = 0;
      for (byte x = 0; x < RATE_SIZE; x++) {
        beatAvg += rates[x];
      }
      beatAvg /= RATE_SIZE;
      return true;
    }
  }
  return false;
}

/**
 * 完整SpO2测量 (阻塞约4秒，不要频繁调用)
 * 返回true表示测量成功
 */
bool max30102_measure_spo2() {
  if (!max30102_ok)
    return false;

  Serial.println("[MAX30102] Measuring SpO2 (takes ~4s)...");

  // 采集100个样本
  for (int i = 0; i < 100; i++) {
    while (!max30102.available())
      max30102.check();

    redBuffer[i] = max30102.getRed();
    irBuffer[i] = max30102.getIR();
    max30102.nextSample();

    // 检测是否有手指
    if (irBuffer[i] < 50000) {
      Serial.println("[MAX30102] No finger detected during SpO2");
      return false;
    }
  }

  // 计算SpO2和心率
  maxim_heart_rate_and_oxygen_saturation(irBuffer, 100, redBuffer, &spo2Value,
                                         &spo2Valid, &heartRateValue,
                                         &heartRateValid);

  if (spo2Valid && heartRateValid) {
    Serial.printf("[MAX30102] SpO2=%d%%, HR=%d bpm\n", spo2Value,
                  heartRateValue);
    return true;
  } else {
    Serial.println("[MAX30102] SpO2 measurement invalid");
    return false;
  }
}

// ─── 取值接口 ───
int max30102_get_heart_rate() {
  return beatAvg > 0 ? beatAvg : (heartRateValid ? heartRateValue : 0);
}

int max30102_get_spo2() { return spo2Valid ? spo2Value : 0; }

bool max30102_has_finger() {
  if (!max30102_ok)
    return false;
  return max30102.getIR() > 50000;
}

bool max30102_is_ok() { return max30102_ok; }
