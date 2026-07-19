#!/usr/bin/env python3
"""
NearLink 星闪定位链路测试
  数据流: Hi3863锚点 --WiFi--> MQTT(bed/nearlink/ranging) --> 本脚本
  不占用任何树莓派 GPIO

用法: python3 test_nearlink.py   (不需要 sudo)

检查项:
  1. 本机 Mosquitto 能否连上
  2. 60 秒内收到哪些锚点的测距数据
  3. 在线锚点数是否 >= 3 (三边定位最低要求)
"""

import json
import time
from collections import defaultdict

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("[ERROR] 缺少 paho-mqtt:  pip3 install paho-mqtt")
    exit(1)

BROKER = "localhost"
PORT = 1883
TOPICS = [("bed/nearlink/ranging", 0), ("bed/nearlink/status", 0)]
LISTEN_SEC = 60

anchor_msgs = defaultdict(int)     # anchor_id -> 消息数
anchor_last = {}                   # anchor_id -> 最近一条距离
raw_count = 0


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ 已连接 MQTT {BROKER}:{PORT}")
        client.subscribe(TOPICS)
        print(f"   已订阅: {[t for t, _ in TOPICS]}")
        print(f"\n监听 {LISTEN_SEC} 秒... (确保锚点已上电并连上 WiFi)\n")
    else:
        print(f"❌ MQTT 连接失败 rc={rc}")


def on_message(client, userdata, msg):
    global raw_count
    raw_count += 1
    payload = msg.payload.decode(errors="replace")
    stamp = time.strftime("%H:%M:%S")

    try:
        data = json.loads(payload)
        # 兼容常见字段名: anchor/anchor_id/id, distance/dist/range
        aid = data.get("anchor") or data.get("anchor_id") or data.get("id") or "?"
        dist = data.get("distance") or data.get("dist") or data.get("range")
        anchor_msgs[aid] += 1
        anchor_last[aid] = dist
        print(f"[{stamp}] {msg.topic}  锚点={aid}  距离={dist}")
    except (json.JSONDecodeError, AttributeError):
        print(f"[{stamp}] {msg.topic}  (非JSON) {payload[:80]}")


client = mqtt.Client(client_id="nearlink-test")
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(BROKER, PORT, keepalive=30)
except Exception as e:
    print(f"❌ 无法连接 Mosquitto: {e}")
    print("   检查: sudo systemctl status mosquitto")
    exit(1)

client.loop_start()
try:
    time.sleep(LISTEN_SEC)
except KeyboardInterrupt:
    print("\n[提前结束]")
client.loop_stop()

print("\n" + "=" * 52)
print(f"共收到 {raw_count} 条消息, {len(anchor_msgs)} 个锚点在线:")
for aid, n in sorted(anchor_msgs.items()):
    hz = n / LISTEN_SEC
    print(f"  锚点 {aid}: {n} 条 (~{hz:.1f}Hz), 最近距离 {anchor_last.get(aid)}")

print("-" * 52)
if len(anchor_msgs) >= 3:
    print("✅ 锚点数 >= 3, 满足三边定位, 可以跑定位解算")
elif len(anchor_msgs) > 0:
    print(f"⚠️ 只有 {len(anchor_msgs)} 个锚点, 三边定位需要 >= 3 个")
    print("   检查缺失锚点的供电和 WiFi 配置")
else:
    print("❌ 没收到任何数据, 排查顺序:")
    print("   1. 锚点是否上电、串口日志是否显示已连 WiFi+MQTT")
    print("   2. 锚点固件里 MQTT 地址是否指向本树莓派 IP")
    print("   3. mosquitto_sub -t 'bed/nearlink/#' -v 手动验证")
print("=" * 52)
