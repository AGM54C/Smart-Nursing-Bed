#!/usr/bin/env python3
"""
智能护理病床 - MQTT → 云端HTTP Bridge (v2.0)

功能升级:
  - 本地MQTT + 涂鸦AI云TuyaLink双链路 (树莓派网关直连, 属性上报+云端命令下发)
  - AI自主决策引擎集成
  - 多模态融合告警
  - 区块链健康数据存证
  - 压力矩阵AI分析 (MobileNet/ONNX)
"""

import json
import random
import math
from collections import deque
import time
import threading
import requests
import paho.mqtt.client as mqtt
from config import *

# ─── 压力矩阵AI分析器 ───
try:
    from pressure_analyzer import PressureAnalyzer
    _analyzer = PressureAnalyzer()
except Exception as e:
    print(f"[MQTT Bridge] ⚠️ PressureAnalyzer not available: {e}")
    _analyzer = None

# ─── AI自主决策引擎 ───
try:
    from decision_engine import DecisionEngine
    _decision_engine = None  # 需要actuator后初始化
except ImportError:
    print("[MQTT Bridge] ⚠️ DecisionEngine not available")
    _decision_engine = None
    DecisionEngine = None

# ─── 多模态融合 ───
try:
    from multimodal_fusion import MultiModalFusion
    _fusion = MultiModalFusion()
except ImportError:
    print("[MQTT Bridge] ⚠️ MultiModalFusion not available")
    _fusion = None

# ─── 区块链存证 ───
try:
    from blockchain import HealthBlockchain
    _blockchain = HealthBlockchain("health_chain.json")
except ImportError:
    print("[MQTT Bridge] ⚠️ Blockchain not available")
    _blockchain = None

# ─── 非接触呼吸率监测 (压力总和4Hz时序 → FFT频域提取) ───
try:
    from breath_monitor import BreathMonitor
    _breath = BreathMonitor()
except Exception as e:
    print(f"[MQTT Bridge] ⚠️ BreathMonitor not available: {e}")
    _breath = None

# 最新传感器数据 (其他模块可读取)
latest_data = {
    "vitals": {},
    "pressure_mat": {},
    "pressure_analysis": {},
    "battery": {},
    "decision_log": [],
    "fusion_result": {},
    "nearlink": {},           # NearLink定位数据
    "last_update": 0
}
data_lock = threading.Lock()

# 传感器在线追踪
_last_real_sensor_time = 0   # 最后一次收到ESP32真实数据的时间戳
_SENSOR_OFFLINE_TIMEOUT = 60 # 超过60秒无真实数据视为无传感器

# 模拟体征状态 (用于无传感器时的AI决策engine输入)
_sim_state = {
    "heart_rate":         72.0,
    "blood_oxygen":       97.5,
    "temperature":        36.5,
    "blood_pressure_sys": 118.0,
    "blood_pressure_dia": 76.0,
    "respiration_rate":   16.0,
}
_SIM_RANGES = {
    "heart_rate":         (62,  88,  0.4),   # (min, max, step)
    "blood_oxygen":       (95.5, 99.0, 0.08),
    "temperature":        (36.1, 37.0, 0.02),
    "blood_pressure_sys": (108, 132,  0.6),
    "blood_pressure_dia": (68,  88,   0.4),
    "respiration_rate":   (12,  20,   0.15),
}

# 姿态时间追踪
_posture_state = {"current": "unknown", "since": time.time(), "turn_count": 0}

# 体征历史 (用于趋势分析)
_vitals_history = {
    "heart_rate": deque(maxlen=6),
    "blood_oxygen": deque(maxlen=6),
    "temperature": deque(maxlen=6),
    "bp_sys": deque(maxlen=6),
}


def _generate_sim_vitals():
    """生成正常范围随机漂移的模拟体征 (仅供本地决策引擎，不上报云端)"""
    for key, (lo, hi, step) in _SIM_RANGES.items():
        delta = random.gauss(0, step)
        _sim_state[key] = max(lo, min(hi, _sim_state[key] + delta))
    return {
        "patient_id":         PATIENT_ID,
        "heart_rate":         round(_sim_state["heart_rate"],  1),
        "blood_oxygen":       round(_sim_state["blood_oxygen"], 1),
        "temperature":        round(_sim_state["temperature"],  2),
        "blood_pressure_sys": round(_sim_state["blood_pressure_sys"], 0),
        "blood_pressure_dia": round(_sim_state["blood_pressure_dia"], 0),
        "respiration_rate":   round(_sim_state["respiration_rate"], 1),
        "sleep_posture":      "supine",
        "_simulated":         True,   # 内部标记，区分真实/模拟
    }


def _sensor_watchdog():
    """后台看门狗：无传感器时向决策引擎注入模拟体征（仅写log，不上报云端/网页）"""
    global _last_real_sensor_time
    # 等待系统启动完成
    time.sleep(20)
    while True:
        time.sleep(15)
        offline = (time.time() - _last_real_sensor_time) > _SENSOR_OFFLINE_TIMEOUT
        if offline:
            sim = _generate_sim_vitals()
            print(f"[Fallback] No sensor detected (>{_SENSOR_OFFLINE_TIMEOUT}s), "
                  f"using simulated vitals for AI engine only "
                  f"(HR={sim['heart_rate']}, SpO2={sim['blood_oxygen']}, "
                  f"Temp={sim['temperature']}) — NOT forwarded to cloud/UI")
            # 仅更新决策引擎上下文，不转发云端
            _update_decision_context_vitals(sim)
            with data_lock:
                # 内部缓存也更新(供本地web_remote查询), 但标记为simulated
                latest_data["vitals"] = sim



# ═══════════════════════════════════════════
#  本地 MQTT Broker 回调
# ═══════════════════════════════════════════

def _on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT Bridge] Connected to Mosquitto")
        client.subscribe(TOPIC_VITALS)
        client.subscribe(TOPIC_PRESSURE_MAT)
        client.subscribe(TOPIC_PULSE_WAVE)
        client.subscribe(TOPIC_BATTERY)
        client.subscribe(TOPIC_BREATH)   # 呼吸微动 4Hz
        client.subscribe("bed/demo/#")   # 演示注入通道 (硬件故障兜底)
        # NearLink定位数据
        if NEARLINK_ENABLED:
            client.subscribe(TOPIC_NL_RANGING)
            client.subscribe(TOPIC_NL_POSITION)
            client.subscribe(TOPIC_NL_STATUS)
            print(f"[MQTT Bridge] Subscribed to NearLink topics")
        print(f"[MQTT Bridge] Subscribed to bed/# topics")
    else:
        print(f"[MQTT Bridge] Connection failed, rc={rc}")


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        topic = msg.topic

        # 更新本地缓存
        with data_lock:
            if topic == TOPIC_VITALS:
                global _last_real_sensor_time
                _last_real_sensor_time = time.time()  # 记录真实传感器最后在线时间
                # 附加边缘提取的呼吸率 (随体征一路上云/上涂鸦/进决策)
                if _breath:
                    payload.update(_breath.get_rate())
                latest_data["vitals"] = payload
                latest_data["last_update"] = time.time()
                _forward_vitals(payload)
                _update_decision_context_vitals(payload)
                # 涂鸦云上报
                _report_to_tuya("vitals", payload)
                # 区块链存证 (每5分钟存一次)
                _blockchain_record_vitals(payload)

            elif topic == TOPIC_PRESSURE_MAT:
                latest_data["pressure_mat"] = payload
                # AI分析压力矩阵
                if _analyzer and "grid" in payload:
                    analysis = _analyzer.analyze(payload["grid"])
                    latest_data["pressure_analysis"] = analysis
                    # 用CNN睡姿覆盖MPU6050结果 (更准确)
                    if analysis.get("posture", {}).get("confidence", 0) > 0.7:
                        cnn_posture = analysis["posture"]["posture"]
                        if cnn_posture != "empty":
                            latest_data["vitals"]["sleep_posture"] = cnn_posture
                            latest_data["vitals"]["posture_source"] = "cnn"
                    # 更新决策引擎上下文
                    _update_decision_context_pressure(analysis)
                    # 更新多模态融合
                    if _fusion:
                        _fusion.update_pressure(analysis)
                _forward_pressure(payload)
                _report_to_tuya("pressure", payload)

            elif topic == TOPIC_BATTERY:
                latest_data["battery"] = payload
                _report_to_tuya("battery", payload)

            elif topic == TOPIC_BREATH:
                # 4Hz高频小包: 只喂给呼吸率监测器, 不转发不存证
                if _breath:
                    _breath.ingest(payload.get("t"), payload.get("v"))

            elif topic.startswith("bed/demo/"):
                # 演示注入 (无真实硬件时驱动完整链路):
                #   mosquitto_pub -t bed/demo/fusion -m '{"event":"fall"}'
                #   mosquitto_pub -t bed/demo/sos    -m '{"text":"救命"}'
                _handle_demo_command(topic, payload)

            # NearLink定位数据缓存
            elif topic == TOPIC_NL_POSITION:
                latest_data["nearlink"] = payload
                print(f"[Bridge] NearLink position: ({payload.get('x')}, {payload.get('y')}) "
                      f"→ Room {payload.get('target_room')} dist={payload.get('distance_to_target')}m")

            elif topic == TOPIC_NL_STATUS:
                latest_data["nearlink_status"] = payload

    except json.JSONDecodeError as e:
        print(f"[MQTT Bridge] JSON parse error: {e}")
    except Exception as e:
        import traceback
        print(f"[MQTT Bridge] Error: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════
#  演示注入 (bed/demo/#) — 硬件故障时的保底演示通道
# ═══════════════════════════════════════════

def _handle_demo_command(topic, payload):
    kind = topic.rsplit("/", 1)[-1]
    if not isinstance(payload, dict):
        payload = {}

    if kind == "fusion" and _fusion:
        event = payload.get("event", "fall")
        result = _fusion.inject_demo(event)
        print(f"[Demo] 融合注入 event={event} → level={result.get('alert_level')} "
              f"Bel={result.get('belief')}")

    elif kind == "sos":
        text = payload.get("text", "救命(演示注入)")
        def _post():
            try:
                resp = requests.post(
                    f"{CLOUD_SERVER}/api/alerts",
                    json={
                        "patient_id": payload.get("patient_id", PATIENT_ID),
                        "alert_type": "critical",
                        "metric": "voice_sos",
                        "value": None,
                        "threshold": "demo",
                        "message": f"🆘 语音SOS呼救: 「{text}」",
                    },
                    headers={"X-API-Key": DEVICE_API_KEY},
                    timeout=8,
                )
                print(f"[Demo] SOS注入已上报 (HTTP {resp.status_code})")
            except Exception as e:
                print(f"[Demo] SOS注入失败: {e}")
        threading.Thread(target=_post, daemon=True).start()

    else:
        print(f"[Demo] 未知演示指令: {topic}")


# ═══════════════════════════════════════════
#  云端转发
# ═══════════════════════════════════════════

def _forward_vitals(data):
    """转发体征数据到云端 /api/vitals"""
    try:
        api_data = {
            "patient_id": data.get("patient_id", PATIENT_ID),
            "heart_rate": data.get("heart_rate"),
            "blood_pressure_sys": data.get("blood_pressure_sys"),
            "blood_pressure_dia": data.get("blood_pressure_dia"),
            "blood_oxygen": data.get("blood_oxygen"),
            "temperature": data.get("temperature"),
            "respiration_rate": data.get("respiration_rate"),
            "sleep_posture": data.get("sleep_posture"),
        }
        api_data = {k: v for k, v in api_data.items() if v is not None}

        resp = requests.post(
            f"{CLOUD_SERVER}/api/vitals",
            json=api_data,
            headers={"X-API-Key": DEVICE_API_KEY},
            timeout=10
        )

        if resp.status_code == 201:
            print(f"[Bridge→Cloud] Vitals forwarded OK (HR={data.get('heart_rate')})")
        else:
            print(f"[Bridge→Cloud] Vitals forward FAILED: {resp.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"[Bridge→Cloud] Network error: {e}")


def _forward_pressure(data):
    """转发压力矩阵+AI分析结果到云端"""
    try:
        grid = data.get("grid")
        if not grid:
            return

        api_data = {
            "patient_id": data.get("patient_id", PATIENT_ID),
            "fabric_sensor_raw": grid
        }

        if _analyzer:
            analysis = _analyzer.get_latest()
            if analysis:
                posture_info = analysis.get("posture", {})
                if posture_info.get("posture") and posture_info["posture"] != "empty":
                    api_data["sleep_posture"] = posture_info["posture"]
                ulcer = analysis.get("ulcer_risk")
                if ulcer:
                    api_data["pressure_ulcer_risk"] = ulcer["level"]

        resp = requests.post(
            f"{CLOUD_SERVER}/api/vitals",
            json=api_data,
            headers={"X-API-Key": DEVICE_API_KEY},
            timeout=10
        )

        if resp.status_code == 201:
            total = data.get("total", 0)
            posture_str = ""
            if _analyzer:
                latest = _analyzer.get_latest()
                if latest:
                    p = latest.get("posture", {})
                    posture_str = f", posture={p.get('posture')}({p.get('confidence', 0):.0%})"
            print(f"[Bridge→Cloud] Pressure forwarded (total={total}{posture_str})")

    except requests.exceptions.RequestException as e:
        print(f"[Bridge→Cloud] Pressure forward error: {e}")


# ═══════════════════════════════════════════
#  涂鸦AI云 TuyaLink 集成 (树莓派网关直连)
#  物模型DP定义见 TUYA_MIGRATION.md
# ═══════════════════════════════════════════

try:
    from tuya_link import TuyaLinkClient
except ImportError:
    print("[MQTT Bridge] ⚠️ tuya_link module not available")
    TuyaLinkClient = None

_tuya_client = None
_tuya_last_report = {"pressure": 0}   # 压力矩阵限流 (2s采样→5s上报, 节省云端配额)
_TUYA_PRESSURE_INTERVAL = 5


def _connect_tuya():
    """连接涂鸦云 (TuyaLink TLS MQTT, 设备三元组认证)"""
    global _tuya_client
    if not TUYA_ENABLED or TuyaLinkClient is None:
        return

    try:
        _tuya_client = TuyaLinkClient(
            TUYA_PRODUCT_ID, TUYA_DEVICE_ID, TUYA_DEVICE_SECRET,
            broker=TUYA_MQTT_BROKER, port=TUYA_MQTT_PORT,
            on_property_set=_handle_tuya_property_set,
            on_action=_handle_tuya_action,
        )
        _tuya_client.connect()
    except Exception as e:
        print(f"[TuyaLink] ⚠️ Connection failed: {e}")
        _tuya_client = None


def _report_to_tuya(data_type, data):
    """上报物模型属性到涂鸦云"""
    if not _tuya_client or not TUYA_ENABLED:
        return

    try:
        if data_type == "vitals":
            temp = data.get("temperature")
            props = {
                "heart_rate": int(data.get("heart_rate") or 0),
                "blood_oxygen": int(data.get("blood_oxygen") or 0),
                # 物模型 temperature 为 value 型, scale=1 → 上报 0.1°C 整数
                "temperature": int(round(float(temp) * 10)) if temp is not None else None,
                "blood_pressure_sys": int(data.get("blood_pressure_sys") or 0),
                "blood_pressure_dia": int(data.get("blood_pressure_dia") or 0),
                "sleep_posture": data.get("sleep_posture", "unknown"),
            }
        elif data_type == "pressure":
            now = time.time()
            if now - _tuya_last_report["pressure"] < _TUYA_PRESSURE_INTERVAL:
                return
            _tuya_last_report["pressure"] = now
            analysis = latest_data.get("pressure_analysis", {})
            ulcer = (analysis.get("ulcer_risk") or {}).get("level", "none")
            props = {
                "pressure_total": int(data.get("total") or 0),
                "bed_occupied": bool(data.get("occupied", False)),
                "posture_ai": (analysis.get("posture") or {}).get("posture", "unknown"),
                "ulcer_risk": ulcer,
            }
        elif data_type == "battery":
            volt = data.get("voltage")
            props = {
                # battery_voltage 为 value 型, scale=1 → 0.1V 整数
                "battery_voltage": int(round(float(volt) * 10)) if volt is not None else None,
                "battery_percent": int(data.get("percent") or 0),
            }
        else:
            return

        _tuya_client.report_properties(props)

    except Exception as e:
        print(f"[TuyaLink] Report error: {e}")


def _handle_tuya_property_set(data):
    """云端属性设置 → 本地硬件命令 (涂鸦App面板可写DP)"""
    if "target_bed_angle" in data:
        publish_command("actuator", {"action": "set_angle",
                                     "angle": data["target_bed_angle"]})
    if "target_room" in data:
        publish_command("navigation", {"action": "goto",
                                       "room": str(data["target_room"])})


def _handle_tuya_action(action_code, params):
    """云端动作调用 → 本地硬件命令, 返回outputParams"""
    if action_code == "set_bed_angle":
        publish_command("actuator", {"action": "set_angle",
                                     "angle": params.get("angle", 0)})
        return {"result": "ok"}
    if action_code == "emergency_stop":
        publish_command("motor", {"action": "stop"})
        return {"result": "ok"}
    if action_code == "navigate_room":
        publish_command("navigation", {"action": "goto",
                                       "room": str(params.get("room", ""))})
        return {"result": "ok"}
    if action_code == "air_decompress":
        publish_command("air", {"action": "decompress",
                                "zone": params.get("zone", "both")})
        return {"result": "ok"}
    if action_code == "get_status":
        v = latest_data.get("vitals", {})
        return {"status": "online",
                "heart_rate": int(v.get("heart_rate") or 0),
                "blood_oxygen": int(v.get("blood_oxygen") or 0)}
    print(f"[TuyaLink] Unknown action: {action_code}")
    return {"result": f"unknown action: {action_code}"}


# ═══════════════════════════════════════════
#  决策引擎上下文更新
# ═══════════════════════════════════════════

def _update_decision_context_vitals(vitals):
    """将体征数据注入决策引擎 (含趋势分析)"""
    if not _decision_engine:
        return

    # 记录历史 (用于趋势计算)
    for key, hist_key in [("heart_rate", "heart_rate"), ("blood_oxygen", "blood_oxygen"),
                           ("temperature", "temperature"), ("blood_pressure_sys", "bp_sys")]:
        val = vitals.get(key)
        if val is not None:
            _vitals_history[hist_key].append(float(val))

    # 计算趋势 (创新点: 为LLM Agent提供上下文)
    vitals_trend = {}
    for hist_key in _vitals_history:
        h = list(_vitals_history[hist_key])
        if len(h) >= 4:
            early = sum(h[:len(h)//2]) / (len(h)//2)
            late = sum(h[len(h)//2:]) / (len(h) - len(h)//2)
            if early > 0:
                change = (late - early) / early
                if change > 0.05:
                    vitals_trend[f"{hist_key}_trend"] = "上升"
                elif change < -0.05:
                    vitals_trend[f"{hist_key}_trend"] = "下降"
                else:
                    vitals_trend[f"{hist_key}_trend"] = "稳定"

    _decision_engine.update_context(
        heart_rate=vitals.get("heart_rate"),
        blood_oxygen=vitals.get("blood_oxygen"),
        temperature=vitals.get("temperature"),
        blood_pressure_sys=vitals.get("blood_pressure_sys"),
        blood_pressure_dia=vitals.get("blood_pressure_dia"),
        posture=vitals.get("sleep_posture"),
        vitals_trend=vitals_trend
    )

    # 多模态体征更新
    if _fusion:
        _fusion.update_vitals(vitals)


def _update_decision_context_pressure(analysis):
    """将压力分析结果注入决策引擎 (含预测风险)"""
    if not _decision_engine:
        return

    posture = analysis.get("posture", {}).get("posture")
    ulcer_risk = analysis.get("ulcer_risk") or {}

    # 跟踪姿态持续时间
    if posture and posture != _posture_state["current"]:
        _posture_state["turn_count"] += 1
        _posture_state["current"] = posture
        _posture_state["since"] = time.time()

    minutes_unchanged = (time.time() - _posture_state["since"]) / 60

    # 提取预测风险 (创新点: 时序预测性护理)
    prediction = analysis.get("prediction") or {}
    predicted_risk = prediction.get("risk", 0)
    predicted_level = prediction.get("level", "none")

    _decision_engine.update_context(
        posture=posture,
        ulcer_risk_level=ulcer_risk.get("level"),
        pressure_empty=not analysis.get("occupied", True),
        posture_unchanged_minutes=minutes_unchanged,
        was_occupied=True,
        predicted_risk=predicted_risk,
        predicted_risk_level=predicted_level
    )

    # 多模态融合 → 决策引擎
    if _fusion:
        fusion_result = _fusion.fuse()
        with data_lock:
            latest_data["fusion_result"] = fusion_result
        if fusion_result.get("fall_detected"):
            _decision_engine.update_context(
                fall_detected=True,
                vision_fall=fusion_result.get("confidence", 0) > 0.5,
                pressure_empty=fusion_result.get("alert_level") == "critical"
            )


# ═══════════════════════════════════════════
#  区块链存证
# ═══════════════════════════════════════════

_last_chain_time = 0


def _blockchain_record_vitals(vitals):
    """定期区块链存证体征数据 (每5分钟一次)"""
    global _last_chain_time
    if not _blockchain:
        return
    now = time.time()
    if now - _last_chain_time < 300:
        return
    _last_chain_time = now

    try:
        _blockchain.add_vital_record(
            PATIENT_ID,
            vitals,
            posture=vitals.get("sleep_posture"),
            anomalies=[]
        )
    except Exception as e:
        print(f"[Blockchain] Record error: {e}")


def blockchain_record_alert(level, message, metric, value):
    """告警事件存证 (供决策引擎回调)"""
    if _blockchain:
        try:
            _blockchain.add_alert_record(PATIENT_ID, level, metric, value, message)
        except Exception:
            pass


# ═══════════════════════════════════════════
#  公开接口
# ═══════════════════════════════════════════

def get_latest_vitals():
    with data_lock:
        return latest_data["vitals"].copy()


def get_latest_pressure():
    with data_lock:
        return latest_data["pressure_mat"].copy()


def get_latest_battery():
    with data_lock:
        return latest_data["battery"].copy()


def get_latest_analysis():
    with data_lock:
        return latest_data.get("pressure_analysis", {}).copy()


def get_fusion_result():
    with data_lock:
        return latest_data.get("fusion_result", {}).copy()


def get_decision_log():
    if _decision_engine:
        return _decision_engine.get_action_log()
    return []


def get_blockchain_info():
    if _blockchain:
        return _blockchain.get_chain_info()
    return {}


# ═══════════════════════════════════════════
#  初始化决策引擎 (需要actuator引用)
# ═══════════════════════════════════════════

def init_decision_engine(actuator=None, voice_fn=None, air_cushion=None):
    """初始化决策引擎 v4.0 Multi-Agent Swarm (由main.py在硬件初始化后调用)"""
    global _decision_engine
    if DecisionEngine is None:
        return

    def alert_callback(level, message, metric, value):
        # 告警 → 云端API + 区块链
        try:
            requests.post(
                f"{CLOUD_SERVER}/api/alerts",
                json={
                    "patient_id": PATIENT_ID,
                    "alert_type": level,
                    "metric": metric,
                    "value": value,
                    "message": message
                },
                headers={"X-API-Key": DEVICE_API_KEY},
                timeout=5
            )
        except Exception:
            pass
        blockchain_record_alert(level, message, metric, value)

    _decision_engine = DecisionEngine(
        actuator=actuator,
        voice_fn=voice_fn,
        alert_fn=alert_callback,
        air_cushion=air_cushion,
        cloud_server=CLOUD_SERVER,
        api_key=DEVICE_API_KEY
    )

    # ─── v4.0: 创建 Multi-Agent Swarm 组件 ───
    try:
        from patient_memory import PatientMemory
        patient_memory = PatientMemory(PATIENT_ID)
        _decision_engine.patient_memory = patient_memory
        print("[MQTT Bridge]   🧠 PatientMemory loaded")
    except ImportError:
        patient_memory = None
        print("[MQTT Bridge]   ⚠️ PatientMemory not available")

    try:
        from agent_mailbox import AgentMailbox
        mailbox = AgentMailbox(persist_dir="memory/mailbox")
        print("[MQTT Bridge]   📬 AgentMailbox initialized")
    except ImportError:
        mailbox = None
        print("[MQTT Bridge]   ⚠️ AgentMailbox not available")

    try:
        from decision_engine import NursingCoordinator
        coordinator = NursingCoordinator(
            cloud_server=CLOUD_SERVER,
            api_key=DEVICE_API_KEY,
            patient_memory=patient_memory,
            mailbox=mailbox,
        )
        _decision_engine.coordinator = coordinator
        print("[MQTT Bridge]   🏥 NursingCoordinator attached (%d agents)" %
              len(coordinator.agents))
    except (ImportError, Exception) as e:
        print(f"[MQTT Bridge]   ⚠️ NursingCoordinator not available: {e}")
        print("[MQTT Bridge]   🔄 Falling back to single LLM Agent")

    _decision_engine.start(interval=10)
    mode = "Multi-Agent Swarm" if _decision_engine.coordinator else "Single LLM Agent"
    print(f"[MQTT Bridge] ✅ DecisionEngine v4.0 started ({mode})")


# ═══════════════════════════════════════════
#  MQTT Bridge 启停
# ═══════════════════════════════════════════

_mqtt_client = None


def start_bridge():
    """启动MQTT Bridge + 涂鸦云连接 + 传感器看门狗"""
    global _mqtt_client

    # 本地Mosquitto
    _mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID + "-bridge")
    _mqtt_client.on_connect = _on_connect
    _mqtt_client.on_message = _on_message

    print(f"[MQTT Bridge] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")

    try:
        _mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        _mqtt_client.loop_start()
        print("[MQTT Bridge] Running in background")
    except Exception as e:
        print(f"[MQTT Bridge] Failed to start: {e}")
        raise

    # 涂鸦AI云 TuyaLink
    if TUYA_ENABLED:
        threading.Thread(target=_connect_tuya, daemon=True).start()

    # 传感器看门狗（无传感器时向决策引擎注入模拟数据）
    threading.Thread(target=_sensor_watchdog, daemon=True, name="SensorWatchdog").start()
    print("[MQTT Bridge] Sensor watchdog started (fallback if no ESP32 data)")


def publish_command(sub_topic, payload_dict):
    """发布控制命令到MQTT"""
    if _mqtt_client and _mqtt_client.is_connected():
        topic = f"{TOPIC_CMD_PREFIX}/{sub_topic}"
        _mqtt_client.publish(topic, json.dumps(payload_dict))


def stop_bridge():
    """停止MQTT Bridge"""
    if _decision_engine:
        _decision_engine.stop()
    if _mqtt_client:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()
    if _tuya_client:
        _tuya_client.disconnect()
    print("[MQTT Bridge] Stopped")


if __name__ == "__main__":
    print("═══ MQTT Bridge v2.1 独立测试模式 ═══")
    print("  Features: Local MQTT + TuyaLink + DecisionEngine + Blockchain")
    start_bridge()
    try:
        while True:
            time.sleep(5)
            v = get_latest_vitals()
            if v:
                print(f"  Latest: HR={v.get('heart_rate')}, SpO2={v.get('blood_oxygen')}")
            bi = get_blockchain_info()
            if bi:
                print(f"  Chain: {bi.get('length', 0)} blocks")
    except KeyboardInterrupt:
        stop_bridge()
        print("Bridge stopped.")
