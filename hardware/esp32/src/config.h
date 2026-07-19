/**
 * 智能护理病床 - ESP32-S3-N16R8 传感器节点配置
 *
 * 芯片: ESP32-S3 (16MB Flash, 8MB PSRAM, USB-C)
 * ⚠️ 收到硬件后，只需修改此文件中的WiFi和MQTT配置即可
 */

#ifndef CONFIG_H
#define CONFIG_H

// ═══════════════════════════════════════════
//  WiFi 配置 (修改为你的WiFi)
// ═══════════════════════════════════════════
#define WIFI_SSID "Creator_Space"
#define WIFI_PASSWORD "iloveSCU"
#define WIFI_RETRY_DELAY 5000 // 重连间隔(ms)
#define WIFI_MAX_RETRIES 20

// ═══════════════════════════════════════════
//  MQTT 配置 (树莓派Mosquitto Broker)
// ═══════════════════════════════════════════
#define MQTT_BROKER "10.20.42.167" // 树莓派IP，按实际修改
#define MQTT_PORT 1883
#define MQTT_CLIENT_ID "esp32-bed-sensor"
#define MQTT_USER "" // Mosquitto如设了认证则填写
#define MQTT_PASS ""
#define MQTT_RETRY_DELAY 3000

// MQTT Topics
#define TOPIC_VITALS "bed/vitals"
#define TOPIC_PRESSURE_MAT "bed/pressure_mat"
#define TOPIC_PULSE_WAVE "bed/pulse_wave"
#define TOPIC_BATTERY "bed/battery"
#define TOPIC_BREATH "bed/breath" // 4Hz压力总和 → 树莓派FFT提取呼吸率
#define TOPIC_CMD "bed/cmd/#" // 订阅所有命令

// ═══════════════════════════════════════════
//  患者配置
// ═══════════════════════════════════════════
#define PATIENT_ID 1

// ═══════════════════════════════════════════
//  传感器采集间隔 (ms)
// ═══════════════════════════════════════════
#define VITALS_INTERVAL 5000   // 心率/血氧/体温 每5秒
#define PRESSURE_INTERVAL 2000 // 压力矩阵 每2秒
#define PULSE_INTERVAL 1000    // 脉搏波 每1秒
#define BREATH_INTERVAL 250    // 呼吸微动采样 4Hz (压力总和)
#define BATTERY_INTERVAL 30000 // 电池电压 每30秒

// ═══════════════════════════════════════════
//  I2C 引脚 (传感器共用总线)
//  ESP32-S3 默认I2C引脚与原版ESP32不同
// ═══════════════════════════════════════════
#define I2C_SDA 2
#define I2C_SCL 1

// I2C 地址
#define MAX30102_ADDR 0x57
#define MLX90614_ADDR 0x5A
#define MPU6050_ADDR 0x68

// ═══════════════════════════════════════════
//  Velostat 压力矩阵引脚
//  ESP32-S3 ADC1: GPIO1-10 (可与WiFi共用)
//  ESP32-S3 ADC2: GPIO11-20 (WiFi时不可用,避免使用)
// ═══════════════════════════════════════════
// MUX1 (行选择) CD74HC4051 控制引脚
#define MUX_ROW_S0 39
#define MUX_ROW_S1 40
#define MUX_ROW_S2 41
// MUX2 (列选择) CD74HC4051 控制引脚
#define MUX_COL_S0 42
#define MUX_COL_S1 21
#define MUX_COL_S2 47
// MUX 模拟输出 → ESP32-S3 ADC1
#define PRESSURE_ADC_PIN 4 // ADC1_CH3
// MUX 行驱动使能
#define MUX_ROW_SIG 48 // 行MUX的SIG引脚

// 矩阵尺寸
#define MAT_ROWS 8
#define MAT_COLS 8

// ═══════════════════════════════════════════
//  HK-2000B+ 脉搏传感器
// ═══════════════════════════════════════════
#define PULSE_ADC_PIN 5 // ADC1_CH4 (ESP32-S3)
// 3.5mm TRS 插头接线:
//   黑线 (Sleeve) → GND
//   红线 (Ring)   → 3.3V
//   黄线 (Tip)    → GPIO5

// ═══════════════════════════════════════════
//  预留: 正式连续血压传感器接口
//  未来接入连续血压模块时修改以下配置
// ═══════════════════════════════════════════
#define BP_SENSOR_ENABLED false // 改为true启用正式血压传感器
#define BP_SENSOR_RX 16         // UART1 RX (预留)
#define BP_SENSOR_TX 15         // UART1 TX (预留)
#define BP_SENSOR_BAUD 9600     // 串口波特率 (预留)
// 当BP_SENSOR_ENABLED=true时，系统将从UART1读取血压数据
// 而非使用HK-2000B+的脉搏波估算

// ═══════════════════════════════════════════
//  电池电压检测
// ═══════════════════════════════════════════
#define BATTERY_ADC_PIN 6 // ADC1_CH5 (ESP32-S3)
// 分压电阻: 100kΩ + 33kΩ, 12V → 2.97V (ESP32安全范围)
// 接线: 12V+ → 100kΩ → [GPIO6测量点] → 33kΩ → GND
#define BATTERY_R1 100000.0
#define BATTERY_R2 33000.0
#define BATTERY_FULL_V 12.6 // 3S满电
#define BATTERY_EMPTY_V 9.9 // 3S截止

// ═══════════════════════════════════════════
//  调试
// ═══════════════════════════════════════════
#define SERIAL_BAUD 115200
#define DEBUG_PRINT true

// ESP32-S3 内置RGB LED (WS2812)
#define LED_PIN 38 // 部分S3开发板RGB在GPIO38或GPIO48

#endif // CONFIG_H
