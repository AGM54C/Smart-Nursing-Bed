/**
 * 智能护理病床 - HK-2000B+ 脉搏波传感器 + 血压估算
 *
 * HK-2000B+ 输出模拟脉搏波信号 → ESP32 ADC采集
 * 通过脉搏波特征(PTT法)粗略估算血压
 *
 * ⚠️ 估算血压仅供参考, 不可用于临床诊断
 *
 * 预留接口: 当 BP_SENSOR_ENABLED=true 时,
 * 将从 UART2 读取正式连续血压传感器数据
 */

#include "config.h"
#include <Arduino.h>


// 脉搏波缓冲区
#define PULSE_BUF_SIZE 500 // 500个采样点
static uint16_t pulseBuf[PULSE_BUF_SIZE];
static int pulseIndex = 0;
static bool bufferFull = false;

// 脉搏波分析结果
static float pulseBPM = 0;
static int estimatedSys = 0; // 估算收缩压
static int estimatedDia = 0; // 估算舒张压
static unsigned long lastPeakTime = 0;
static int peakCount = 0;

// 正式血压传感器 (预留)
#if BP_SENSOR_ENABLED
static HardwareSerial BPSerial(2); // UART2
#endif

bool pulse_sensor_init() {
  analogReadResolution(12);

#if BP_SENSOR_ENABLED
  // 正式血压传感器模式
  BPSerial.begin(BP_SENSOR_BAUD, SERIAL_8N1, BP_SENSOR_RX, BP_SENSOR_TX);
  Serial.println("[Pulse] Formal BP sensor mode (UART2)");
#else
  Serial.println("[Pulse] HK-2000B+ mode (ADC analog)");
#endif

  memset(pulseBuf, 0, sizeof(pulseBuf));
  Serial.println("[Pulse] Initialized OK");
  return true;
}

/**
 * 采集一个脉搏波样本 (在loop中高频调用)
 * 建议调用频率: 每2ms一次 (500Hz采样率)
 */
void pulse_sensor_sample() {
#if BP_SENSOR_ENABLED
  // 正式血压传感器: 从UART读取数据
  // 这里预留协议解析框架，具体协议需根据传感器型号适配
  if (BPSerial.available() >= 8) {
    uint8_t header = BPSerial.read();
    // TODO: 根据具体传感器协议解析血压数据
    // 示例: [Header][SYS_H][SYS_L][DIA_H][DIA_L][HR][Checksum]
    // estimatedSys = ...;
    // estimatedDia = ...;
  }
  return;
#endif

  // HK-2000B+ 模拟信号采集
  uint16_t raw = analogRead(PULSE_ADC_PIN);
  pulseBuf[pulseIndex] = raw;
  pulseIndex = (pulseIndex + 1) % PULSE_BUF_SIZE;
  if (pulseIndex == 0)
    bufferFull = true;

  // 简单峰值检测 (脉搏波峰值=收缩期)
  static uint16_t lastVal = 0;
  static uint16_t lastLastVal = 0;
  static bool rising = false;

  if (raw > lastVal && lastVal <= lastLastVal) {
    rising = true;
  }

  if (rising && raw < lastVal && lastVal > 1000) {
    // 检测到峰值
    unsigned long now = millis();
    if (lastPeakTime > 0) {
      unsigned long interval = now - lastPeakTime;
      if (interval > 300 && interval < 2000) {
        // 有效心跳间隔 (30-200 BPM)
        pulseBPM = 60000.0 / interval;
        peakCount++;
      }
    }
    lastPeakTime = now;
    rising = false;
  }

  lastLastVal = lastVal;
  lastVal = raw;
}

/**
 * 基于脉搏波特征估算血压 (PTT简化版)
 *
 * 估算公式 (经验公式, 精度有限):
 *   SYS ≈ 0.5 × HR + 80 + amplitude_factor
 *   DIA ≈ 0.3 × HR + 50 + amplitude_factor
 *
 * ⚠️ 这只是粗略估算, 仅供Demo演示
 */
void pulse_estimate_bp() {
#if BP_SENSOR_ENABLED
  return; // 正式传感器模式下不需要估算
#endif

  if (pulseBPM < 30 || pulseBPM > 200) {
    estimatedSys = 0;
    estimatedDia = 0;
    return;
  }

  // 计算脉搏波振幅
  uint16_t maxVal = 0, minVal = 4095;
  int count = bufferFull ? PULSE_BUF_SIZE : pulseIndex;
  for (int i = 0; i < count; i++) {
    if (pulseBuf[i] > maxVal)
      maxVal = pulseBuf[i];
    if (pulseBuf[i] < minVal)
      minVal = pulseBuf[i];
  }
  float amplitude = (maxVal - minVal) / 4095.0; // 归一化 0-1

  // 经验公式估算
  float ampFactor = amplitude * 20 - 10; // 振幅修正 ±10
  estimatedSys = (int)(0.5 * pulseBPM + 80 + ampFactor);
  estimatedDia = (int)(0.3 * pulseBPM + 50 + ampFactor * 0.6);

  // 合理性限制
  if (estimatedSys < 80)
    estimatedSys = 80;
  if (estimatedSys > 200)
    estimatedSys = 200;
  if (estimatedDia < 40)
    estimatedDia = 40;
  if (estimatedDia > 130)
    estimatedDia = 130;
  if (estimatedDia >= estimatedSys)
    estimatedDia = estimatedSys - 30;
}

// ─── 取值接口 ───
float pulse_get_bpm() { return pulseBPM; }
int pulse_get_sys() { return estimatedSys; }
int pulse_get_dia() { return estimatedDia; }

/**
 * 获取最近的脉搏波原始数据 (用于上传波形)
 * 返回最近n个采样点
 */
int pulse_get_wave(uint16_t *out, int maxCount) {
  int count = bufferFull ? PULSE_BUF_SIZE : pulseIndex;
  if (count > maxCount)
    count = maxCount;

  // 从当前位置往回取
  for (int i = 0; i < count; i++) {
    int idx = (pulseIndex - count + i + PULSE_BUF_SIZE) % PULSE_BUF_SIZE;
    out[i] = pulseBuf[idx];
  }
  return count;
}

bool pulse_has_signal() { return pulseBPM > 30 && pulseBPM < 200; }

bool pulse_is_formal_bp() {
#if BP_SENSOR_ENABLED
  return true;
#else
  return false;
#endif
}
