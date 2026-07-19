#!/usr/bin/env python3
"""
电动推杆测试脚本 - L298N #3 Channel A
  IN1=GPIO13 (伸出/升)
  IN2=GPIO19 (缩回/降)
  ENA=GPIO26 (PWM)
  OUT1/OUT2 → 推杆   (Channel B 空置)

用法: sudo python3 test_actuator.py

安全设计:
  - 每次动作最长 3 秒自动停 (避免顶到极限堵转烧 L298N)
  - 动作间停 2 秒
  - Ctrl+C 随时急停并清理
测试序列:
  1. 伸出 3 秒 → 停
  2. 缩回 3 秒 → 停
  3. 半速伸出 2 秒 → 停 (验证 PWM 调速)
  4. 半速缩回 2 秒 → 停
"""

import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("[ERROR] RPi.GPIO 不可用, 请在树莓派上运行")
    exit(1)

# ── 推杆引脚 (BCM, 与 config.py 一致) ──
IN1 = 13   # 伸出
IN2 = 19   # 缩回
EN = 26    # PWM

PWM_FREQ = 1000
SPEED_FULL = 100   # 推杆负载重, 全速跑
SPEED_HALF = 60    # 半速验证 PWM

MAX_RUN_SEC = 3    # 单次动作最长时间 (堵转保护)

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
for p in (IN1, IN2, EN):
    GPIO.setup(p, GPIO.OUT)
    GPIO.output(p, GPIO.LOW)

pwm = GPIO.PWM(EN, PWM_FREQ)
pwm.start(0)


def extend(speed=SPEED_FULL):
    """伸出 (升)"""
    GPIO.output(IN1, GPIO.HIGH)
    GPIO.output(IN2, GPIO.LOW)
    pwm.ChangeDutyCycle(speed)


def retract(speed=SPEED_FULL):
    """缩回 (降)"""
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.HIGH)
    pwm.ChangeDutyCycle(speed)


def stop():
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.LOW)
    pwm.ChangeDutyCycle(0)


def run(msg, action, speed, sec):
    sec = min(sec, MAX_RUN_SEC)  # 硬上限
    print(f"\n>>> {msg}  ({sec}s, speed={speed}%)")
    action(speed)
    time.sleep(sec)
    stop()
    print("    [停]")
    time.sleep(2)


try:
    print("=" * 46)
    print("电动推杆测试  IN1=13 IN2=19 EN=26")
    print(f"单次动作上限 {MAX_RUN_SEC}s (堵转保护), Ctrl+C 急停")
    print("=" * 46)
    print("\n⚠️ 观察要点:")
    print("  - '伸出'时推杆杆体应该伸长, 反了则接线极性相反(告诉我改软件)")
    print("  - 若推杆已在极限位置, 对应方向不会动, 属正常")
    print("  - L298N 是否异常发烫? 烫则立即断电")

    run("1. 全速伸出", extend, SPEED_FULL, 3)
    run("2. 全速缩回", retract, SPEED_FULL, 3)
    run("3. 半速伸出 (验证PWM)", extend, SPEED_HALF, 2)
    run("4. 半速缩回 (验证PWM)", retract, SPEED_HALF, 2)

    print("\n" + "=" * 46)
    print("测试完成, 请反馈:")
    print("  a) 伸出/缩回方向是否正确? (反了我对调 IN 引脚)")
    print("  b) 半速时推杆是否明显变慢? (验证 PWM 有效)")
    print("  c) L298N 温度是否正常?")
    print("=" * 46)

except KeyboardInterrupt:
    print("\n[急停]")

finally:
    stop()
    pwm.stop()
    GPIO.cleanup()
    print("[清理] GPIO 已释放")
