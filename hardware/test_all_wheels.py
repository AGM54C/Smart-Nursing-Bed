#!/usr/bin/env python3
"""
四轮综合测试 - L298N #1(前轮) + #2(后轮)

引脚 (BCM, 与 config.py 一致):
  左前: IN1=17, IN2=27, EN=12
  右前: IN1=23, IN2=22, EN=16   # 已对调做反向修正(原22/23)
  左后: IN1=5,  IN2=6,  EN=11
  右后: IN1=9,  IN2=10, EN=2

用法: sudo python3 test_all_wheels.py

依次测试整车动作: 前进 / 后退 / 左转 / 右转 / 原地左旋 / 原地右旋 / 停止
建议把小车架空, 避免乱跑。
"""

import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("[ERROR] RPi.GPIO 不可用, 请在树莓派上运行")
    exit(1)

PWM_FREQ = 1000
SPEED = 60

# ── 四个轮子: (IN1, IN2, EN) ──
WHEELS = {
    "左前": (17, 27, 12),
    "右前": (23, 22, 16),   # 反向修正: IN1/IN2 已对调
    "左后": (5, 6, 11),
    "右后": (9, 10, 2),
}

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

pwm = {}
for name, (in1, in2, en) in WHEELS.items():
    for p in (in1, in2, en):
        GPIO.setup(p, GPIO.OUT)
        GPIO.output(p, GPIO.LOW)
    pwm[name] = GPIO.PWM(en, PWM_FREQ)
    pwm[name].start(0)


def wheel(name, direction, speed=SPEED):
    """direction: 'fwd' | 'bwd' | 'stop'"""
    in1, in2, _ = WHEELS[name]
    if direction == "fwd":
        GPIO.output(in1, GPIO.HIGH)
        GPIO.output(in2, GPIO.LOW)
    elif direction == "bwd":
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.HIGH)
    else:
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.LOW)
    pwm[name].ChangeDutyCycle(0 if direction == "stop" else speed)


def all_wheels(lf, rf, lb, rb):
    """一次设置四轮方向"""
    wheel("左前", lf)
    wheel("右前", rf)
    wheel("左后", lb)
    wheel("右后", rb)


def stop():
    all_wheels("stop", "stop", "stop", "stop")


def move(msg, lf, rf, lb, rb, sec=2):
    print(f"\n>>> {msg}")
    all_wheels(lf, rf, lb, rb)
    time.sleep(sec)
    stop()
    time.sleep(1)


try:
    print("=" * 44)
    print("四轮综合测试  (每个动作 2 秒)")
    print("建议架空小车观察")
    print("=" * 44)

    # 整车动作: 左侧=左前+左后, 右侧=右前+右后
    move("前进   (四轮向前)", "fwd", "fwd", "fwd", "fwd")
    move("后退   (四轮向后)", "bwd", "bwd", "bwd", "bwd")
    move("左转   (左停 右转)", "stop", "fwd", "stop", "fwd")
    move("右转   (左转 右停)", "fwd", "stop", "fwd", "stop")
    move("原地左旋 (左后 右前)", "bwd", "fwd", "bwd", "fwd")
    move("原地右旋 (左前 右后)", "fwd", "bwd", "fwd", "bwd")

    print("\n" + "=" * 44)
    print("测试完成")
    print("重点确认: '前进'时四轮同向, '后退'时四轮同向")
    print("如仍有轮子反向, 告诉我是哪个(左前/右前/左后/右后)")
    print("=" * 44)

except KeyboardInterrupt:
    print("\n[中断] 用户停止")

finally:
    stop()
    for p in pwm.values():
        p.stop()
    GPIO.cleanup()
    print("[清理] GPIO 已释放")
