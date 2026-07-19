/**
 * 智能护理病床 - Velostat 8×8 压力矩阵传感器
 *
 * 硬件接线:
 *   Velostat矩阵 → 两片CD74HC4051多路复用器 → ESP32 ADC
 *
 * 工作原理:
 *   1. MUX1选择行 → 对选中行施加HIGH信号
 *   2. MUX2选择列 → 读取该列的ADC值
 *   3. 逐行逐列扫描，得到8×8压力矩阵
 *
 * Velostat特性: 受压→电阻降低→ADC读数升高
 * 无压力时ADC≈0，重压时ADC→4095
 */

#include "config.h"
#include <Arduino.h>


// 8×8 压力数据
static uint16_t pressureGrid[MAT_ROWS][MAT_COLS];
static bool mat_initialized = false;

// MUX选择引脚数组
static const int muxRowPins[] = {MUX_ROW_S0, MUX_ROW_S1, MUX_ROW_S2};
static const int muxColPins[] = {MUX_COL_S0, MUX_COL_S1, MUX_COL_S2};

/**
 * 设置MUX通道 (0-7)
 */
static void selectMuxChannel(const int pins[], int channel) {
  digitalWrite(pins[0], (channel >> 0) & 1);
  digitalWrite(pins[1], (channel >> 1) & 1);
  digitalWrite(pins[2], (channel >> 2) & 1);
}

bool pressure_mat_init() {
  // 配置MUX控制引脚
  for (int i = 0; i < 3; i++) {
    pinMode(muxRowPins[i], OUTPUT);
    pinMode(muxColPins[i], OUTPUT);
  }

  // 行驱动信号
  pinMode(MUX_ROW_SIG, OUTPUT);
  digitalWrite(MUX_ROW_SIG, LOW);

  // ADC引脚 (ESP32 ADC1通道, GPIO34只读)
  analogReadResolution(12);       // 12位: 0-4095
  analogSetAttenuation(ADC_11db); // 0-3.3V满量程

  // 清零
  memset(pressureGrid, 0, sizeof(pressureGrid));

  mat_initialized = true;
  Serial.println("[PressureMat] Initialized OK (8x8 Velostat)");
  return true;
}

/**
 * 扫描整个8×8矩阵
 * 耗时约 8×8×0.2ms ≈ 13ms
 */
void pressure_mat_scan() {
  if (!mat_initialized)
    return;

  for (int row = 0; row < MAT_ROWS; row++) {
    // 选择行
    selectMuxChannel(muxRowPins, row);
    // 驱动该行 HIGH
    digitalWrite(MUX_ROW_SIG, HIGH);
    delayMicroseconds(50); // 等待信号稳定

    for (int col = 0; col < MAT_COLS; col++) {
      // 选择列
      selectMuxChannel(muxColPins, col);
      delayMicroseconds(100); // ADC稳定时间

      // 读取ADC
      uint16_t raw = analogRead(PRESSURE_ADC_PIN);

      // 简单滤波: 与上次值取平均
      pressureGrid[row][col] = (pressureGrid[row][col] + raw) / 2;
    }

    // 关闭行驱动
    digitalWrite(MUX_ROW_SIG, LOW);
  }
}

/**
 * 获取压力矩阵数据指针
 */
const uint16_t (*pressure_mat_get_grid())[MAT_COLS] { return pressureGrid; }

/**
 * 获取单点压力值
 */
uint16_t pressure_mat_get_point(int row, int col) {
  if (row < 0 || row >= MAT_ROWS || col < 0 || col >= MAT_COLS)
    return 0;
  return pressureGrid[row][col];
}

/**
 * 获取总压力 (所有点之和)
 * 用于检测是否有人在床上
 */
uint32_t pressure_mat_get_total() {
  uint32_t total = 0;
  for (int r = 0; r < MAT_ROWS; r++) {
    for (int c = 0; c < MAT_COLS; c++) {
      total += pressureGrid[r][c];
    }
  }
  return total;
}

/**
 * 检测是否有人在床上
 * 阈值: 总压力 > 5000 视为有人
 */
bool pressure_mat_is_occupied() { return pressure_mat_get_total() > 5000; }

/**
 * 序列化为JSON数组字符串
 * 格式: [[r0c0,r0c1,...],[r1c0,...],...]
 */
void pressure_mat_to_json(char *buf, size_t bufSize) {
  int pos = 0;
  pos += snprintf(buf + pos, bufSize - pos, "[");

  for (int r = 0; r < MAT_ROWS; r++) {
    pos += snprintf(buf + pos, bufSize - pos, "[");
    for (int c = 0; c < MAT_COLS; c++) {
      pos += snprintf(buf + pos, bufSize - pos, "%u", pressureGrid[r][c]);
      if (c < MAT_COLS - 1) {
        pos += snprintf(buf + pos, bufSize - pos, ",");
      }
    }
    pos += snprintf(buf + pos, bufSize - pos, "]");
    if (r < MAT_ROWS - 1) {
      pos += snprintf(buf + pos, bufSize - pos, ",");
    }
  }

  snprintf(buf + pos, bufSize - pos, "]");
}

bool pressure_mat_is_ok() { return mat_initialized; }
