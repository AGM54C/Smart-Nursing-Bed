#!/usr/bin/env python3
"""
智能护理病床 - 涂鸦AI云 TuyaLink MQTT 直连客户端

树莓派作为网关设备, 通过 TuyaLink 协议 (物模型) 直连涂鸦云:
  - 设备三元组认证 (productId / deviceId / deviceSecret, HMAC-SHA256签名)
  - TLS MQTT (8883)
  - 属性上报: tylink/{deviceId}/thing/property/report
  - 云端下发: tylink/{deviceId}/thing/property/set   (属性设置)
              tylink/{deviceId}/thing/action/execute (动作调用)

独立测试: python3 tuya_link.py  (需先在config.py填好三元组并 TUYA_ENABLED=True)
协议参考: https://developer.tuya.com/cn/docs/iot-device-dev (TuyaLink 接入方案)
"""

import hashlib
import hmac
import json
import threading
import time

import paho.mqtt.client as mqtt


def _make_mqtt_client(client_id):
    """兼容 paho-mqtt 1.x 与 2.x 的 Client 构造"""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    except AttributeError:
        return mqtt.Client(client_id=client_id)


class TuyaLinkClient:
    """TuyaLink 直连设备客户端 (网关模式)

    Args:
        product_id / device_id / device_secret: 设备三元组
        broker / port: 数据中心接入点 (中国区 m1.tuyacn.com:8883)
        on_property_set: 回调 fn(data: dict) — 云端属性设置 {code: value}
        on_action: 回调 fn(action_code: str, input_params: dict) -> dict|None
                   返回值作为 outputParams 回给云端
    """

    def __init__(self, product_id, device_id, device_secret,
                 broker="m1.tuyacn.com", port=8883,
                 on_property_set=None, on_action=None):
        self.product_id = product_id
        self.device_id = device_id
        self.device_secret = device_secret
        self.broker = broker
        self.port = port
        self.on_property_set = on_property_set
        self.on_action = on_action

        self.topic_report = f"tylink/{device_id}/thing/property/report"
        self.topic_set = f"tylink/{device_id}/thing/property/set"
        self.topic_action = f"tylink/{device_id}/thing/action/execute"
        self.topic_action_resp = f"tylink/{device_id}/thing/action/execute_response"

        self._client = None
        self._connected = False
        self._msg_seq = 0
        self._lock = threading.Lock()

    # ─── 认证 ───

    def _credentials(self):
        """生成 TuyaLink 一机一密登录凭据 (secureMode=1 直连设备)"""
        t = str(int(time.time()))
        client_id = f"tuyalink_{self.device_id}"
        username = (f"{self.device_id}|signMethod=hmacSha256,"
                    f"timestamp={t},secureMode=1,accessType=1")
        sign_content = (f"deviceId={self.device_id},"
                        f"timestamp={t},secureMode=1,accessType=1")
        password = hmac.new(self.device_secret.encode(),
                            sign_content.encode(),
                            hashlib.sha256).hexdigest()
        return client_id, username, password

    def _next_msg_id(self):
        with self._lock:
            self._msg_seq += 1
            return f"{int(time.time() * 1000)}{self._msg_seq:04d}"

    # ─── 连接 ───

    def connect(self):
        client_id, username, password = self._credentials()
        self._client = _make_mqtt_client(client_id)
        self._client.username_pw_set(username, password)
        self._client.tls_set()
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        print(f"[TuyaLink] Connecting to {self.broker}:{self.port} ...")
        self._client.connect(self.broker, self.port, keepalive=120)
        self._client.loop_start()

    def disconnect(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False

    @property
    def connected(self):
        return self._connected

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            client.subscribe(self.topic_set)
            client.subscribe(self.topic_action)
            print("[TuyaLink] ✅ Connected to Tuya Cloud, subscribed to set/action topics")
        else:
            print(f"[TuyaLink] Connection refused: rc={rc} "
                  "(检查三元组是否正确、数据中心是否为中国区)")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            print(f"[TuyaLink] ⚠️ Unexpected disconnect (rc={rc}), auto-reconnecting...")

    # ─── 属性上报 ───

    def report_properties(self, props):
        """上报物模型属性. props: {code: value} 平铺字典"""
        if not self._connected or not props:
            return False
        now_ms = int(time.time() * 1000)
        payload = {
            "msgId": self._next_msg_id(),
            "time": now_ms,
            "data": {code: {"value": value, "time": now_ms}
                     for code, value in props.items() if value is not None},
        }
        if not payload["data"]:
            return False
        result = self._client.publish(self.topic_report, json.dumps(payload), qos=1)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    # ─── 云端下行 ───

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"[TuyaLink] Bad downlink payload: {e}")
            return

        try:
            if msg.topic == self.topic_set:
                data = payload.get("data", {})
                print(f"[TuyaLink] Property set: {data}")
                if self.on_property_set:
                    self.on_property_set(data)

            elif msg.topic == self.topic_action:
                data = payload.get("data", {})
                action_code = data.get("actionCode", "")
                input_params = data.get("inputParams", {}) or {}
                print(f"[TuyaLink] Action: {action_code} → {input_params}")
                output = None
                if self.on_action:
                    output = self.on_action(action_code, input_params)
                resp = {
                    "msgId": payload.get("msgId", self._next_msg_id()),
                    "time": int(time.time() * 1000),
                    "data": {
                        "actionCode": action_code,
                        "outputParams": output if isinstance(output, dict) else {},
                    },
                }
                client.publish(self.topic_action_resp, json.dumps(resp))
        except Exception as e:
            import traceback
            print(f"[TuyaLink] Downlink handler error: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    # 独立测试: 连接涂鸦云并每5秒上报一组模拟体征
    from config import (TUYA_ENABLED, TUYA_PRODUCT_ID, TUYA_DEVICE_ID,
                        TUYA_DEVICE_SECRET, TUYA_MQTT_BROKER, TUYA_MQTT_PORT)

    if not TUYA_ENABLED or "YOUR_" in TUYA_DEVICE_ID:
        print("⚠️ 请先在 config.py 填入设备三元组并设置 TUYA_ENABLED = True")
        raise SystemExit(1)

    def on_set(data):
        print(f"  >> 收到属性设置: {data}")

    def on_action(code, params):
        print(f"  >> 收到动作: {code}({params})")
        return {"result": "ok"}

    c = TuyaLinkClient(TUYA_PRODUCT_ID, TUYA_DEVICE_ID, TUYA_DEVICE_SECRET,
                       TUYA_MQTT_BROKER, TUYA_MQTT_PORT,
                       on_property_set=on_set, on_action=on_action)
    c.connect()
    try:
        while True:
            time.sleep(5)
            ok = c.report_properties({
                "heart_rate": 72,
                "blood_oxygen": 98,
                "temperature": 365,     # 0.1°C 精度 → 36.5°C (物模型scale=1)
                "sleep_posture": "supine",
            })
            print(f"  << 上报{'成功' if ok else '失败(未连接?)'}")
    except KeyboardInterrupt:
        c.disconnect()
        print("Bye.")
