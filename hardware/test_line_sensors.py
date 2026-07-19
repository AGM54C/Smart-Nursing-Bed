#!/usr/bin/env python3
"""
循迹传感器测试 - 3路 TCRT5000 (5路板只接 S1/S3/S5)
  左=GPIO4  中=GPIO18  右=GPIO0

用法: sudo python3 test_line_sensors.py
实时显示 20 秒, 用黑胶带在传感器下方左右移动观察。
TCRT5000: 黑线反射弱 → 输出 LOW → 显示 ■(在线上)
"""

import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("[ERROR] 请在树莓派上运行")
    exit(1)

PINS = {"左": 4, "中": 18, "右": 0}
DURATION = 20

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
for p in PINS.values():
    GPIO.setup(p, GPIO.IN)

print("=" * 46)
print("3路循迹测试 (%d 秒), ■=检测到黑线  □=白色/悬空" % DURATION)
print("传感器距地面 1~2cm, 用黑胶带左右扫过测试")
print("=" * 46)

try:
    t_end = time.time() + DURATION
    while time.time() < t_end:
        # 黑线=LOW=1(在线上)
        state = {k: (GPIO.input(p) == GPIO.LOW) for k, p in PINS.items()}
        bar = "  ".join(f"{k}:{'■' if v else '□'}" for k, v in state.items())
        raw = "  ".join(f"{k}={GPIO.input(p)}" for k, p in PINS.items())
        print(f"\r  {bar}   (raw: {raw})   ", end="", flush=True)
        time.sleep(0.15)

    print("\n" + "=" * 46)
    print("判读:")
    print("  - 黑胶带压过哪路, 哪路应变 ■")
    print("  - 全程恒 ■ 或恒 □ 不变 -> 该路接线/灵敏度旋钮问题")
    print("  - TCRT5000 板上有电位器, 可调触发灵敏度")
    print("=" * 46)

except KeyboardInterrupt:
    print("\n[中断]")
finally:
    GPIO.cleanup()
    print("[清理] GPIO 已释放")
