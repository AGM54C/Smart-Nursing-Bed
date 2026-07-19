/**
 * 智能护理病床 - MLX90614 非接触式红外测温
 * 使用原始 I2C 读取,绕过 Adafruit 库的兼容性问题
 */

#include <Arduino.h>
#include "config.h"
#include <Wire.h>

static bool mlx_ok = false;

// 直接读取 MLX90614 寄存器 (SMBus 协议)
static float mlx90614_read_temp(uint8_t reg) {
  Wire.beginTransmission(MLX90614_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return -999.0;  // 通信失败
  }

  Wire.requestFrom(MLX90614_ADDR, 3);
  if (Wire.available() < 3) {
    return -999.0;
  }

  uint8_t temp_low = Wire.read();
  uint8_t temp_high = Wire.read();
  Wire.read();  // PEC 校验字节 (暂时忽略)

  uint16_t raw_temp = (temp_high << 8) | temp_low;
  return raw_temp * 0.02 - 273.15;  // 转换为摄氏度
}

bool mlx90614_init() {
  delay(100);

  // 测试读取环境温度 (寄存器 0x06)
  float ambient = mlx90614_read_temp(0x06);

  if (ambient < -40.0 || ambient > 85.0) {
    Serial.println("[MLX90614] NOT FOUND! Check wiring.");
    mlx_ok = false;
    return false;
  }

  mlx_ok = true;
  Serial.printf("[MLX90614] Initialized OK, Ambient=%.2f°C\n", ambient);
  return true;
}

/**
 * 读取目标物体温度 (人体温度)
 * 寄存器 0x07
 */
float mlx90614_get_object_temp() {
  if (!mlx_ok)
    return -1.0;

  float temp = mlx90614_read_temp(0x07);

  // 合理性校验: 人体温度范围 20-50°C
  if (temp < 20.0 || temp > 50.0) {
    return -1.0;
  }

  return temp;
}

/**
 * 读取环境温度
 * 寄存器 0x06
 */
float mlx90614_get_ambient_temp() {
  if (!mlx_ok)
    return -1.0;
  return mlx90614_read_temp(0x06);
}

bool mlx90614_is_ok() { return mlx_ok; }
