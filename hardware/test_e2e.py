#!/usr/bin/env python3
"""
端到端虚拟联调测试 (无需任何硬件)

链路: MockSensor(模拟ESP32) → 本地MQTT broker → mqtt_bridge → 云端API → SQLite

用法:
  1. 启动MQTT broker (树莓派: mosquitto / 开发机: npx aedes-cli --port 1883)
  2. 启动云端: PORT=3100 node server.js  (或指向真实服务器, 见 CLOUD_OVERRIDE)
  3. python3 test_e2e.py
"""

import json
import os
import sqlite3
import sys
import time

# Windows GBK 控制台下强制 UTF-8 输出 (打印 emoji 不再崩溃)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── 在导入 mqtt_bridge 前覆盖 config (仅测试, 不改动生产配置) ───
CLOUD_OVERRIDE = os.environ.get("E2E_CLOUD", "http://127.0.0.1:3100")
import config
config.CLOUD_SERVER = CLOUD_OVERRIDE

import mqtt_bridge
mqtt_bridge.CLOUD_SERVER = CLOUD_OVERRIDE  # from-import 快照同步覆盖

import paho.mqtt.client as mqtt
from mock_publisher import MockSensorGenerator

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "nursing.db")


def count_vitals():
    con = sqlite3.connect(DB_PATH)
    try:
        return con.execute("SELECT COUNT(*) FROM vitals").fetchone()[0]
    finally:
        con.close()


def main():
    print("═══ 端到端虚拟联调 (Mock ESP32 → MQTT → Bridge → Cloud → SQLite) ═══")
    print(f"  云端: {CLOUD_OVERRIDE}")

    before = count_vitals()
    print(f"  测试前 vitals 行数: {before}")

    # 1. 启动桥接 (连本地broker, 订阅 bed/#)
    mqtt_bridge.start_bridge()
    time.sleep(2)

    # 2. 模拟ESP32发布3轮数据
    pub = mqtt.Client(client_id="mock-esp32-e2e")
    pub.connect("localhost", 1883, 30)
    pub.loop_start()
    gen = MockSensorGenerator("normal")

    for i in range(3):
        pub.publish("bed/vitals", json.dumps(gen.vitals()))
        pub.publish("bed/pressure_mat", json.dumps(gen.pressure_matrix()))
        pub.publish("bed/battery", json.dumps(gen.battery()))
        gen.advance()
        print(f"  → 已发布第 {i+1}/3 轮模拟数据")
        time.sleep(3)

    time.sleep(3)  # 等桥接转发完成

    # 3. 校验
    v = mqtt_bridge.get_latest_vitals()
    a = mqtt_bridge.get_latest_analysis()
    after = count_vitals()

    print("\n─── 校验结果 ───")
    ok = True
    if v.get("heart_rate"):
        print(f"  ✅ Bridge缓存体征: HR={v['heart_rate']} SpO2={v.get('blood_oxygen')} "
              f"姿态={v.get('sleep_posture')}")
    else:
        print("  ❌ Bridge未收到体征"); ok = False

    if a:
        p = a.get("posture", {})
        print(f"  ✅ 压力AI分析: posture={p.get('posture')} conf={p.get('confidence', 0):.0%} "
              f"engine={a.get('engine', '?')}")
    else:
        print("  ⚠️ 压力AI分析为空 (无训练模型时正常)")

    delta = after - before
    if delta >= 3:
        print(f"  ✅ 云端SQLite新增 {delta} 行 vitals (HTTP POST 201 全链路通)")
    else:
        print(f"  ❌ 云端SQLite仅新增 {delta} 行 (检查云端是否启动/API Key)"); ok = False

    pub.loop_stop(); pub.disconnect()
    mqtt_bridge.stop_bridge()
    print("\n" + ("═══ ✅ E2E PASS ═══" if ok else "═══ ❌ E2E FAIL ═══"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
