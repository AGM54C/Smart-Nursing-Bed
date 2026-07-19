#!/usr/bin/env python3
"""
左前轮诊断 - L298N #1 Channel A
  IN1=GPIO17, IN2=GPIO27, ENA=GPIO12

用法: sudo python3 test_left_front_debug.py

逐项排查左前轮不转的原因:
  A. ENA 常高 (排除 PWM 问题) + IN1/IN2 正反
  B. 单独拉高每个引脚, 用万用表可测电平
  C. 提高到全速, 排除电机堵转/电压不足
"""

import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("[ERROR] 请在树莓派上运行")
    exit(1)

IN1 = 17
IN2 = 27
EN = 12
PWM_FREQ = 1000

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
for pin in (IN1, IN2, EN):
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)


def pause(msg, sec=3):
    print(f"\n>>> {msg}  ({sec}s)")
    time.sleep(sec)


try:
    print("=" * 50)
    print("左前轮诊断  IN1=17 IN2=27 EN=12")
    print("=" * 50)

    # ── 测试 A: ENA 直接常高 (不走 PWM), 正转 ──
    # 如果这样能转, 说明是 PWM/EN 引脚的问题
    pause("A1: EN=常高(HIGH), IN1=HIGH IN2=LOW  期望正转")
    GPIO.output(EN, GPIO.HIGH)
    GPIO.output(IN1, GPIO.HIGH)
    GPIO.output(IN2, GPIO.LOW)
    time.sleep(3)

    pause("A2: EN=常高(HIGH), IN1=LOW IN2=HIGH  期望反转")
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.HIGH)
    time.sleep(3)

    # 停
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.LOW)
    GPIO.output(EN, GPIO.LOW)

    # ── 测试 B: 用 PWM 全速 ──
    pause("B: 用 PWM EN=100% 全速, IN1=HIGH IN2=LOW")
    pwm = GPIO.PWM(EN, PWM_FREQ)
    pwm.start(100)
    GPIO.output(IN1, GPIO.HIGH)
    GPIO.output(IN2, GPIO.LOW)
    time.sleep(3)
    pwm.ChangeDutyCycle(0)
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.LOW)
    pwm.stop()

    # ── 测试 C: 逐引脚拉高, 便于万用表测电平 ──
    print("\n" + "=" * 50)
    print("C: 逐引脚拉高 5 秒, 用万用表测 GPIO 与 L298N 输入脚电平")
    print("   (探针: GPIO 引脚 vs GND, 应约 3.3V)")
    print("=" * 50)

    for name, pin in (("IN1=GPIO17", IN1), ("IN2=GPIO27", IN2), ("EN=GPIO12", EN)):
        pause(f"C: {name} 拉高 -> 量此脚应为 ~3.3V", 5)
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(5)
        GPIO.output(pin, GPIO.LOW)

    print("\n" + "=" * 50)
    print("诊断结束, 请反馈:")
    print("  - A1/A2 (EN常高) 转不转?")
    print("  - B (PWM全速) 转不转?")
    print("  - 若全都不转 -> 大概率 L298N 的 A 通道输出脚(OUT1/OUT2)")
    print("    或该路 ENA 跳线/电机线焊点问题")
    print("  - 若 A 转但原始测试(60%)不转 -> PWM 占空比太低/电压不足")
    print("=" * 50)

except KeyboardInterrupt:
    print("\n[中断]")
finally:
    GPIO.cleanup()
    print("[清理] GPIO 已释放")
