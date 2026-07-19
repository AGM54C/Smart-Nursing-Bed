#!/usr/bin/env python3
"""
智能护理病床 - 树莓派主控入口

整合所有模块:
  - MQTT Bridge (ESP32传感器→云端 + 涂鸦AI云TuyaLink)
  - 导航引擎 (循迹/RFID寻房/遥控)
  - 病床升降
  - AI自主决策引擎
  - 语音AI陪聊
  - Web遥控界面
"""

import sys
import time
import signal
import threading

# 配置
from config import *

# 模块
from mqtt_bridge import start_bridge, stop_bridge, init_decision_engine
from navigation import Navigator
from bed_actuator import BedActuator
from air_cushion import AirCushionController
from web_remote import start_web_server
from camera_stream import start_camera_stream, stop_camera_stream
from lcd_display import LCDDisplay


def main():
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║  🛏️  智能护理病床 · 树莓派主控 v4.0          ║")
    print("║  [Multi-Agent Swarm + 预测性护理 + 气囊减压]     ║")
    print("║  Cloud: {:38s} ║".format(CLOUD_SERVER))
    print("║  MQTT:  {:38s} ║".format(f"{MQTT_BROKER}:{MQTT_PORT}"))
    print("║  Tuya:  {:38s} ║".format("Enabled" if TUYA_ENABLED else "Disabled"))
    print("╚══════════════════════════════════════════════╝")
    print()

    # ─── 1. 启动MQTT Bridge (v2.1: +涂鸦云) ───
    print("─── [1/7] Starting MQTT Bridge + TuyaLink ───")
    try:
        start_bridge()
    except Exception as e:
        print(f"⚠️ MQTT Bridge failed: {e}")
        print("   确保Mosquitto已运行: sudo systemctl start mosquitto")

    # ─── 注册设备IP到云端 (供摄像头自动发现) ───
    import socket as _sock, requests as _req
    try:
        _s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        _s.connect(("8.8.8.8", 80))
        _my_ip = _s.getsockname()[0]
        _s.close()
        _req.post(f"{CLOUD_SERVER}/api/device/register",
                  json={"patient_id": PATIENT_ID, "ip": _my_ip}, timeout=5)
        print(f"[Main] ✅ 设备IP已注册: {_my_ip} → {CLOUD_SERVER}")
    except Exception as _e:
        print(f"[Main] ⚠️ 设备IP注册失败: {_e}")

    # ─── 2. 初始化硬件 ───
    print("─── [2/7] Initializing Hardware ───")
    navigator = Navigator()
    actuator = BedActuator()
    print("  ✅ Navigator ready")
    print("  ✅ Actuator ready")

    # 气囊减压控制器 (创新点: 闭环自动减压)
    air_cushion = None
    try:
        air_cushion = AirCushionController()
        print("  ✅ Air Cushion ready")
    except Exception as e:
        print(f"  ⚠️ Air Cushion failed: {e}")

    # ─── 3. AI自主决策引擎 v2.0 ───
    print("─── [3/7] Starting AI Decision Engine v2.0 ───")
    try:
        init_decision_engine(actuator=actuator, voice_fn=None, air_cushion=air_cushion)
        print("  ✅ Decision Engine v4.0 ready (Multi-Agent Swarm)")
    except Exception as e:
        print(f"  ⚠️ Decision Engine failed: {e}")

    # ─── 4. 启动Web遥控 ───
    print("─── [4/7] Starting Web Remote Control ───")
    import mqtt_bridge as bridge_module
    start_web_server(navigator, actuator, bridge_module, port=5000)

    # ─── 5. 启动摄像头视频流 ───
    print("─── [5/7] Starting Camera Stream ───")
    try:
        start_camera_stream()
    except Exception as e:
        print(f"  ⚠️ Camera failed: {e}")

    # ─── 6. 启动语音客户端 (可选) ───
    print("─── [6/7] Voice Client ───")
    voice_thread = None
    try:
        from voice_client import VoiceClient
        voice_client = VoiceClient(CLOUD_SERVER, PATIENT_ID, auto_mode=VOICE_AUTO_MODE)

        def voice_loop():
            try:
                print("[Voice] Starting voice chat loop...")
                voice_client.run_loop()
            except Exception as e:
                print(f"  ⚠️ Voice loop stopped: {e}")

        voice_thread = threading.Thread(target=voice_loop, daemon=True)
        voice_thread.start()
        print("  ✅ Voice client started")
    except ImportError as e:
        print(f"  ⚠️ Voice client not available: {e}")
        print("     Install: pip install pyaudio requests")
    except Exception as e:
        print(f"  ⚠️ Voice client error: {e}")

    # ─── 7. 启动LCD屏幕显示 ───
    print("─── [7/7] LCD Display ───")
    lcd = LCDDisplay()
    try:
        from mqtt_bridge import (get_latest_vitals, get_latest_battery,
                                 get_latest_analysis, publish_command)
        from lcd_display import make_call_nurse_handler

        def lcd_data():
            return {
                "vitals":   get_latest_vitals(),
                "battery":  get_latest_battery(),
                "nav":      navigator.get_status() if navigator else {},
                "analysis": get_latest_analysis(),
            }

        # 呼叫护士：语音播报 + MQTT告警
        _vc = voice_client if 'voice_client' in dir() else None
        call_nurse_cb = make_call_nurse_handler(
            lcd_display  = lcd,
            voice_client = _vc,
            mqtt_pub_fn  = publish_command,
            patient_id   = PATIENT_ID,
        )

        # 床体控制操作额外路由到 actuator
        def lcd_action(action_key):
            call_nurse_cb(action_key)          # 呼叫护士 / 日志
            if action_key == 'bed_raise':
                actuator.raise_bed()
            elif action_key == 'bed_lower':
                actuator.lower_bed()
            elif action_key == 'bed_stop':
                actuator.stop()

        lcd.show_message("系统启动中...", '#7b8cff')
        lcd.start(data_getter=lcd_data, action_callback=lcd_action)
        print("  ✅ LCD Display started (3-page touch UI)")
    except Exception as e:
        print(f"  ⚠️ LCD failed: {e}")

    # ─── 系统就绪 ───
    print()
    print("═══════════════════════════════════════════════")
    print("  ✅ System Ready!")
    print(f"  🌐 Web Remote:  http://<RPi-IP>:5000")
    print(f"  📹 Camera:      http://<RPi-IP>:{CAMERA_STREAM_PORT}/stream")
    print(f"  📡 MQTT Broker:  {MQTT_BROKER}:{MQTT_PORT}")
    print(f"  ☁️  Cloud API:   {CLOUD_SERVER}")
    if TUYA_ENABLED:
        print(f"  🔗 TuyaCloud:   {TUYA_MQTT_BROKER}")
    print("  🧠 AI Engine:   DecisionEngine v4.0 Multi-Agent Swarm")
    print("  👥 Agents:      VitalsAgent + PressureAgent + EmergencyAgent + CompanionAgent")
    print("  🔮 Prediction:  1D-CNN Risk Forecasting")
    print("  🫧 AirCushion:  {}".format("Active" if air_cushion else "Disabled"))
    print("  🔗 Blockchain:  HealthChain active")
    print("  Ctrl+C to shutdown")
    print("═══════════════════════════════════════════════")
    print()

    # ─── 优雅退出 ───
    def shutdown(signum=None, frame=None):
        print("\n🛑 Shutting down...")
        navigator.cleanup()
        actuator.cleanup()
        if air_cushion:
            air_cushion.cleanup()
        stop_camera_stream()
        lcd.stop()
        stop_bridge()
        try:
            import RPi.GPIO as GPIO
            GPIO.cleanup()
        except Exception:
            pass
        print("👋 Goodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 保持主线程
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
