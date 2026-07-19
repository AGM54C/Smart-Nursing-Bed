#!/usr/bin/env python3
"""
超声波测试 - 3x HC-SR04
  前方: TRIG=24, ECHO=25
  左侧: TRIG=7,  ECHO=8
  右侧: TRIG=20, ECHO=21

用法: sudo python3 test_ultrasonic.py

⚠️ 接线前必读:
  HC-SR04 是 5V 模块, ECHO 输出 5V 高电平!
  ECHO 必须经分压(1kΩ+2kΩ)降到 3.3V 再进树莓派,
  直连会烧 GPIO。TRIG 可以直连(3.3V 能触发)。
  VCC → 5V, GND → 共地。
"""

import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("[ERROR] 请在树莓派上运行")
    exit(1)

SENSORS = {
    "前方": {"trig": 24, "echo": 25},
    "左侧": {"trig": 7, "echo": 8},
    "右侧": {"trig": 20, "echo": 21},
}

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

for s in SENSORS.values():
    GPIO.setup(s["trig"], GPIO.OUT)
    GPIO.output(s["trig"], GPIO.LOW)
    GPIO.setup(s["echo"], GPIO.IN)


def measure(trig, echo, timeout=0.04):
    """单次测距, 返回 cm; 失败返回 None"""
    GPIO.output(trig, GPIO.HIGH)
    time.sleep(0.00001)          # 10us 触发脉冲
    GPIO.output(trig, GPIO.LOW)

    t0 = time.time()
    while GPIO.input(echo) == 0:            # 等回波开始
        if time.time() - t0 > timeout:
            return None
    start = time.time()
    while GPIO.input(echo) == 1:            # 等回波结束
        if time.time() - start > timeout:
            return None
    end = time.time()

    return (end - start) * 34300 / 2        # 声速 343m/s


def median3(trig, echo):
    """测3次取中位数, 抗毛刺"""
    vals = [v for v in (measure(trig, echo) for _ in range(3)) if v]
    if not vals:
        return None
    vals.sort()
    return vals[len(vals) // 2]


try:
    print("=" * 52)
    print("超声波测试: 10 轮 x 3 传感器 (每轮间隔 0.5s)")
    print("用手/纸板在传感器前 10~50cm 处移动, 观察读数变化")
    print("=" * 52)
    print(f"\n{'轮次':<4} {'前方(cm)':>10} {'左侧(cm)':>10} {'右侧(cm)':>10}")

    fails = {name: 0 for name in SENSORS}
    for i in range(1, 11):
        row = []
        for name, s in SENSORS.items():
            d = median3(s["trig"], s["echo"])
            if d is None:
                fails[name] += 1
                row.append("超时")
            else:
                row.append(f"{d:.1f}")
            time.sleep(0.06)  # 传感器间错开, 避免串扰
        print(f"{i:<6} {row[0]:>10} {row[1]:>10} {row[2]:>10}")
        time.sleep(0.5)

    print("\n" + "=" * 52)
    for name, n in fails.items():
        if n == 10:
            print(f"❌ {name}: 全部超时 -> 查接线(TRIG/ECHO是否接反, ECHO分压, 5V供电)")
        elif n > 3:
            print(f"⚠️ {name}: {n}/10 超时 -> 接触不良或分压电阻问题")
        else:
            print(f"✅ {name}: 正常 ({10-n}/10 有效)")
    print("=" * 52)

except KeyboardInterrupt:
    print("\n[中断]")
finally:
    GPIO.cleanup()
    print("[清理] GPIO 已释放")
