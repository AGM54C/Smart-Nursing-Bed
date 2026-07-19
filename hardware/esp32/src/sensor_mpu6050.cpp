/**
 * 智能护理病床 - MPU6050 姿态/睡姿检测
 *
 * 通过加速度计判断人体姿态:
 *   - 仰卧: Z轴朝上 (az > 0.7g)
 *   - 俯卧: Z轴朝下 (az < -0.7g)
 *   - 左侧卧: Y轴朝下 (ay < -0.7g)
 *   - 右侧卧: Y轴朝上 (ay > 0.7g)
 *   - 坐起: X轴朝下 (ax < -0.7g, 身体直立)
 */

#include "config.h"
#include <MPU6050.h>
#include <Wire.h>


static MPU6050 mpu;
static bool mpu_ok = false;

// 加速度原始值
static int16_t ax, ay, az;
static int16_t gx, gy, gz;

// 姿态字符串
static const char *POSTURE_SUPINE = "supine";    // 仰卧
static const char *POSTURE_PRONE = "prone";      // 俯卧
static const char *POSTURE_LEFT = "left_side";   // 左侧卧
static const char *POSTURE_RIGHT = "right_side"; // 右侧卧
static const char *POSTURE_SITTING = "sitting";  // 坐起
static const char *POSTURE_UNKNOWN = "unknown";

bool mpu6050_init() {
  // 延时让传感器稳定
  delay(100);

  // MPU6050 库会自动使用已初始化的 Wire
  mpu.initialize();

  // 检查 WHO_AM_I 寄存器 (0x75)
  // MPU6050 返回 0x68, MPU6500/9250 返回 0x70-0x73
  uint8_t who_am_i = mpu.getDeviceID();
  Serial.printf("[MPU6050] WHO_AM_I: 0x%02X ", who_am_i);

  // 接受 MPU6050/6500/9250 系列 (Device ID 范围)
  if (who_am_i == 0x34 || who_am_i == 0x0C || who_am_i == 0x3A ||
      who_am_i == 0x30 || who_am_i == 0x38) {  // 0x30=MPU6500, 0x38=MPU9250
    Serial.println("✅");
  } else {
    Serial.printf("❌ (不支持的设备 ID)\n");
    mpu_ok = false;
    return false;
  }

  // 设置加速度范围 ±2g (最灵敏)
  mpu.setFullScaleAccelRange(MPU6050_ACCEL_FS_2);
  // 设置低通滤波
  mpu.setDLPFMode(MPU6050_DLPF_BW_42);

  mpu_ok = true;
  Serial.println("[MPU6050] Initialized OK");
  return true;
}

/**
 * 更新传感器数据
 */
void mpu6050_update() {
  if (!mpu_ok)
    return;
  mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
}

/**
 * 判断睡姿
 * 返回姿态字符串
 */
const char *mpu6050_get_posture() {
  if (!mpu_ok)
    return POSTURE_UNKNOWN;

  // 将原始值转换为g值 (±2g范围, 16384 LSB/g)
  float fax = ax / 16384.0;
  float fay = ay / 16384.0;
  float faz = az / 16384.0;

  // 阈值 0.7g 用于判断主导轴向
  const float THRESHOLD = 0.7;

  if (faz > THRESHOLD) {
    return POSTURE_SUPINE; // Z轴朝上 → 仰卧
  } else if (faz < -THRESHOLD) {
    return POSTURE_PRONE; // Z轴朝下 → 俯卧
  } else if (fay < -THRESHOLD) {
    return POSTURE_LEFT; // Y轴朝下 → 左侧卧
  } else if (fay > THRESHOLD) {
    return POSTURE_RIGHT; // Y轴朝上 → 右侧卧
  } else if (fax < -THRESHOLD) {
    return POSTURE_SITTING; // X轴朝下 → 坐起
  }

  return POSTURE_UNKNOWN;
}

/**
 * 获取体动强度 (0-100)
 * 用陀螺仪角速度的模判断体动
 */
int mpu6050_get_movement() {
  if (!mpu_ok)
    return 0;

  float fgx = gx / 131.0; // ±250°/s, 131 LSB/°/s
  float fgy = gy / 131.0;
  float fgz = gz / 131.0;

  // 角速度的模
  float magnitude = sqrt(fgx * fgx + fgy * fgy + fgz * fgz);

  // 映射到0-100
  int movement = (int)(magnitude * 10);
  if (movement > 100)
    movement = 100;

  return movement;
}

/**
 * 获取原始加速度 (g值)
 */
void mpu6050_get_accel(float *x, float *y, float *z) {
  if (x)
    *x = ax / 16384.0;
  if (y)
    *y = ay / 16384.0;
  if (z)
    *z = az / 16384.0;
}

bool mpu6050_is_ok() { return mpu_ok; }
