#!/usr/bin/env python3
"""
左后轮 IN2 诊断 - 只后退不工作
  左后: IN1=GPIO5, IN2=GPIO6, ENA=GPIO11

正转(GPIO5高)正常 -> IN1/EN/电机/L298N输出都好
反转(GPIO6高)失败 -> 问题锁定在 GPIO6 -> IN2 这一路

用法: sudo python3 test_rear_left_in2.py
"""

import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("[ERROR] 请在树莓派上运行")
    exit(1)

IN1 = 5
IN2 = 6
EN = 11
PWM_FREQ = 1000

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
for pin in (IN1, IN2, EN):
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)


def pause(msg, sec=4):
    print(f"\n>>> {msg}  ({sec}s)")
    time.sleep(1)


try:
    print("=" * 50)
    print("左后轮 IN2(GPIO6) 诊断")
    print("=" * 50)

    # 测试 1: EN 常高, 只驱动 IN2 反转 (排除 PWM 干扰)
    pause("1: EN=常高, IN1=LOW IN2=HIGH  期望后退")
    GPIO.output(EN, GPIO.HIGH)
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.HIGH)
    time.sleep(4)
    GPIO.output(IN2, GPIO.LOW)
    GPIO.output(EN, GPIO.LOW)

    # 测试 2: 单独把 GPIO6 拉高 8 秒, 用万用表量电平
    print("\n" + "=" * 50)
    print("2: GPIO6 单独拉高 8 秒")
    print("   万用表红表笔点 GPIO6 引脚, 黑表笔点 GND")
    print("   -> 应约 3.3V")
    print("   再点 L298N 的 IN2 输入端子 vs GND")
    print("   -> 也应约 3.3V; 若这里是 0V 则杜邦线断/松")
    print("=" * 50)
    GPIO.output(IN2, GPIO.HIGH)
    time.sleep(8)
    GPIO.output(IN2, GPIO.LOW)

    # 测试 3: 对比 - 单独把 GPIO5 拉高 (已知好使的那路)
    print("\n" + "=" * 50)
    print("3: 对比 - GPIO5 单独拉高 8 秒 (已知正常路)")
    print("   同样量 GPIO5 和 L298N IN1 端子, 应约 3.3V")
    print("=" * 50)
    GPIO.output(IN1, GPIO.HIGH)
    time.sleep(8)
    GPIO.output(IN1, GPIO.LOW)

    print("\n" + "=" * 50)
    print("判断:")
    print("  - 测试1能后退 -> GPIO6正常, 之前不转是 PWM 相关(概率低)")
    print("  - 测试2: GPIO6脚有3.3V 但 L298N IN2端子是0V -> 杜邦线断/松")
    print("  - 测试2: GPIO6脚本身就是0V -> 该GPIO或排线问题")
    print("  - 测试2/3都正常有电压但仍不转 -> L298N 的 IN2 输入损坏")
    print("=" * 50)

except KeyboardInterrupt:
    print("\n[中断]")
finally:
    GPIO.cleanup()
    print("[清理] GPIO 已释放")
