#!/usr/bin/env python3
"""
Mock ESP32 数据发布器 - 模拟传感器数据 (无需硬件)

用法:
    python3 mock_publisher.py              # 正常模拟数据
    python3 mock_publisher.py --abnormal   # 模拟异常数据 (触发告警)
    python3 mock_publisher.py --pressure   # 模拟持续高压 (触发预测预警)
"""

import json
import time
import random
import math
import sys
import paho.mqtt.client as mqtt

# ─── MQTT Topics (与 config.py 一致) ───
TOPIC_VITALS = "bed/vitals"
TOPIC_PRESSURE_MAT = "bed/pressure_mat"
TOPIC_BATTERY = "bed/battery"

MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# ─── 模拟数据生成器 ───

class MockSensorGenerator:
    """模拟 ESP32 传感器数据"""

    def __init__(self, mode="normal"):
        self.mode = mode
        self.tick = 0
        self.posture_cycle = ["supine", "supine", "supine", "left_side",
                              "supine", "supine", "right_side", "supine"]

    def vitals(self):
        """生成体征数据 (模拟 MAX30102 + MLX90614 + MPU6050)"""
        t = self.tick
        base_hr = 72
        base_spo2 = 97
        base_temp = 36.5

        if self.mode == "abnormal":
            # 模拟异常: 心率偏高, 血氧偏低
            hr = random.randint(95, 115)
            spo2 = random.randint(88, 93)
            temp = round(random.uniform(37.5, 38.5), 1)
        else:
            # 正常波动
            hr = base_hr + int(5 * math.sin(t * 0.3)) + random.randint(-3, 3)
            spo2 = base_spo2 + random.choice([0, 0, 0, -1, 1])
            temp = round(base_temp + 0.1 * math.sin(t * 0.1) + random.uniform(-0.2, 0.2), 1)

        posture = self.posture_cycle[t % len(self.posture_cycle)]

        return {
            "heart_rate": max(50, min(hr, 150)),
            "blood_oxygen": max(85, min(spo2, 100)),
            "temperature": max(35.0, min(temp, 42.0)),
            "blood_pressure_sys": random.randint(110, 130),
            "blood_pressure_dia": random.randint(65, 85),
            "sleep_posture": posture,
            "patient_id": 1,
            "accel_x": round(random.uniform(-0.1, 0.1), 2),
            "accel_y": round(random.uniform(-0.1, 0.1), 2),
            "accel_z": round(random.uniform(0.9, 1.1), 2),
        }

    def pressure_matrix(self):
        """生成 8×8 压力矩阵数据 (模拟织物传感器)"""
        t = self.tick
        grid = [[0] * 8 for _ in range(8)]

        if self.mode == "pressure":
            # 模拟持续高压 (骶尾部 - 中下区域)
            for r in range(4, 7):
                for c in range(2, 6):
                    grid[r][c] = random.randint(700, 950)
            # 其他区域低压
            for r in range(0, 4):
                for c in range(8):
                    grid[r][c] = random.randint(50, 200)
        else:
            posture = self.posture_cycle[t % len(self.posture_cycle)]
            if posture == "supine":
                # 仰卧: 背部+臀部均匀分布
                for r in range(8):
                    for c in range(8):
                        if 2 <= r <= 6 and 1 <= c <= 6:
                            grid[r][c] = random.randint(300, 550)
                        else:
                            grid[r][c] = random.randint(20, 100)
            elif posture == "left_side":
                # 左侧卧: 左侧压力集中
                for r in range(8):
                    for c in range(8):
                        if c <= 3:
                            grid[r][c] = random.randint(400, 650)
                        else:
                            grid[r][c] = random.randint(10, 80)
            elif posture == "right_side":
                # 右侧卧: 右侧压力集中
                for r in range(8):
                    for c in range(8):
                        if c >= 4:
                            grid[r][c] = random.randint(400, 650)
                        else:
                            grid[r][c] = random.randint(10, 80)

        return {
            "grid": grid,
            "patient_id": 1,
            "timestamp": int(time.time())
        }

    def battery(self):
        """模拟电池状态"""
        return {
            "voltage": round(random.uniform(3.7, 4.2), 2),
            "percentage": random.randint(60, 95),
            "charging": False
        }

    def advance(self):
        self.tick += 1


def main():
    mode = "normal"
    if "--abnormal" in sys.argv:
        mode = "abnormal"
        print("⚠️  异常模式: 模拟高心率/低血氧/发热 → 触发LLM告警")
    elif "--pressure" in sys.argv:
        mode = "pressure"
        print("⚠️  高压模式: 模拟持续高压 → 触发预测性护理预警")
    else:
        print("✅ 正常模式: 模拟稳定体征数据")

    print(f"📡 连接 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")

    client = mqtt.Client(client_id="mock-esp32")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"❌ MQTT 连接失败: {e}")
        print("💡 先在树莓派上启动 Mosquitto: sudo systemctl start mosquitto")
        return

    client.loop_start()
    gen = MockSensorGenerator(mode)

    print("🚀 开始发布模拟数据 (Ctrl+C 停止)\n")

    try:
        while True:
            # 发布体征 (每5秒)
            vitals = gen.vitals()
            client.publish(TOPIC_VITALS, json.dumps(vitals))
            print(f"💓 HR={vitals['heart_rate']} SpO2={vitals['blood_oxygen']}% "
                  f"Temp={vitals['temperature']}°C 姿态={vitals['sleep_posture']}")

            # 发布压力矩阵 (每5秒)
            pressure = gen.pressure_matrix()
            max_p = max(max(row) for row in pressure["grid"])
            client.publish(TOPIC_PRESSURE_MAT, json.dumps(pressure))
            print(f"📊 压力矩阵 max={max_p}")

            # 发布电池 (每30秒)
            if gen.tick % 6 == 0:
                battery = gen.battery()
                client.publish(TOPIC_BATTERY, json.dumps(battery))
                print(f"🔋 电池 {battery['percentage']}%")

            gen.advance()
            print("─" * 50)
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n⏹️  已停止模拟数据发布")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
