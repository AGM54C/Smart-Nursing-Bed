#!/usr/bin/env python3
"""
后轮测试脚本 - L298N #2
  左后: IN1=GPIO5,  IN2=GPIO6,  ENA=GPIO11
  右后: IN3=GPIO9,  IN4=GPIO10, ENB=GPIO2

用法: sudo python3 test_rear_wheels.py

依次测试:
  1. 左后轮正转 / 反转
  2. 右后轮正转 / 反转
  3. 两轮同时前进 / 后退
每步之间停 1 秒, 方便观察方向是否正确。
"""

import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("[ERROR] RPi.GPIO 不可用, 请在树莓派上运行")
    exit(1)

# ── 后轮引脚 (BCM 编号) ──
LEFT_IN1 = 5
LEFT_IN2 = 6
LEFT_EN = 11
RIGHT_IN1 = 9
RIGHT_IN2 = 10
RIGHT_EN = 2

PWM_FREQ = 1000   # Hz
SPEED = 60        # 占空比 0-100

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

for pin in (LEFT_IN1, LEFT_IN2, LEFT_EN, RIGHT_IN1, RIGHT_IN2, RIGHT_EN):
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

pwm_left = GPIO.PWM(LEFT_EN, PWM_FREQ)
pwm_right = GPIO.PWM(RIGHT_EN, PWM_FREQ)
pwm_left.start(0)
pwm_right.start(0)


def left_wheel(direction, speed=SPEED):
    """direction: 'fwd' | 'bwd' | 'stop'"""
    if direction == "fwd":
        GPIO.output(LEFT_IN1, GPIO.HIGH)
        GPIO.output(LEFT_IN2, GPIO.LOW)
    elif direction == "bwd":
        GPIO.output(LEFT_IN1, GPIO.LOW)
        GPIO.output(LEFT_IN2, GPIO.HIGH)
    else:
        GPIO.output(LEFT_IN1, GPIO.LOW)
        GPIO.output(LEFT_IN2, GPIO.LOW)
    pwm_left.ChangeDutyCycle(0 if direction == "stop" else speed)


def right_wheel(direction, speed=SPEED):
    if direction == "fwd":
        GPIO.output(RIGHT_IN1, GPIO.HIGH)
        GPIO.output(RIGHT_IN2, GPIO.LOW)
    elif direction == "bwd":
        GPIO.output(RIGHT_IN1, GPIO.LOW)
        GPIO.output(RIGHT_IN2, GPIO.HIGH)
    else:
        GPIO.output(RIGHT_IN1, GPIO.LOW)
        GPIO.output(RIGHT_IN2, GPIO.LOW)
    pwm_right.ChangeDutyCycle(0 if direction == "stop" else speed)


def step(msg, seconds=1):
    print(f"\n>>> {msg}")
    time.sleep(seconds)


try:
    print("=" * 40)
    print("后轮测试开始 (每步 2 秒)")
    print("请观察每个轮子的实际转向是否符合预期")
    print("=" * 40)

    # 1. 左后轮
    step("左后轮 正转 (期望: 向前)")
    left_wheel("fwd")
    time.sleep(2)
    left_wheel("stop")

    step("左后轮 反转 (期望: 向后)")
    left_wheel("bwd")
    time.sleep(2)
    left_wheel("stop")

    # 2. 右后轮
    step("右后轮 正转 (期望: 向前)")
    right_wheel("fwd")
    time.sleep(2)
    right_wheel("stop")

    step("右后轮 反转 (期望: 向后)")
    right_wheel("bwd")
    time.sleep(2)
    right_wheel("stop")

    # 3. 两轮同步
    step("两后轮 同时前进")
    left_wheel("fwd")
    right_wheel("fwd")
    time.sleep(2)
    left_wheel("stop")
    right_wheel("stop")

    step("两后轮 同时后退")
    left_wheel("bwd")
    right_wheel("bwd")
    time.sleep(2)
    left_wheel("stop")
    right_wheel("stop")

    print("\n" + "=" * 40)
    print("测试完成")
    print("如有轮子转向相反, 记下是哪个轮子(左后/右后),")
    print("告诉我, 我在 config.py 里对调该轮 IN 引脚做反向修正。")
    print("=" * 40)

except KeyboardInterrupt:
    print("\n[中断] 用户停止")

finally:
    pwm_left.stop()
    pwm_right.stop()
    GPIO.cleanup()
    print("[清理] GPIO 已释放")
