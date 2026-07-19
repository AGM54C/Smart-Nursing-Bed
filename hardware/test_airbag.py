#!/usr/bin/env python3
"""
气囊系统测试 - 气泵 + 双区电磁阀 (等到货后再跑)
  气泵继电器 = GPIO3  (低电平触发)
  左区电磁阀 = GPIO14 (低电平触发)
  右区电磁阀 = GPIO15 (低电平触发)

用法: sudo python3 test_airbag.py

⚠️ 跑之前:
  1. raspi-config 里必须已关闭串口console (GPIO14/15是UART0)
  2. 继电器模块选"低电平触发"档 (板上跳线)
  3. 没接气囊也能干跑: 听继电器咔哒声即代表GPIO控制正常

安全设计: 气泵单次最长 5 秒; 结束时强制开阀排气+断泵。
"""

import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("[ERROR] 请在树莓派上运行")
    exit(1)

PUMP = 3
VALVE_L = 14
VALVE_R = 15
ACTIVE_LOW = True          # 低电平触发继电器
PUMP_MAX_SEC = 5           # 气泵单次硬上限

ON = GPIO.LOW if ACTIVE_LOW else GPIO.HIGH
OFF = GPIO.HIGH if ACTIVE_LOW else GPIO.LOW

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
for p in (PUMP, VALVE_L, VALVE_R):
    GPIO.setup(p, GPIO.OUT)
    GPIO.output(p, OFF)     # 上电先全关


def set_dev(pin, on):
    GPIO.output(pin, ON if on else OFF)


def all_off_safe():
    """安全态: 泵停, 双阀打开排气 2 秒后关阀"""
    set_dev(PUMP, False)
    set_dev(VALVE_L, True)
    set_dev(VALVE_R, True)
    time.sleep(2)
    set_dev(VALVE_L, False)
    set_dev(VALVE_R, False)


def step(msg, sec):
    print(f">>> {msg}  ({sec}s)")
    time.sleep(sec)


try:
    print("=" * 50)
    print("气囊系统测试  泵=GPIO3 左阀=GPIO14 右阀=GPIO15")
    print("低电平触发; Ctrl+C 随时急停(自动排气)")
    print("=" * 50)

    step("1. 初始排气: 双阀开", 0)
    set_dev(VALVE_L, True)
    set_dev(VALVE_R, True)
    time.sleep(2)
    set_dev(VALVE_L, False)
    set_dev(VALVE_R, False)
    time.sleep(1)

    step("2. 充气: 关阀 + 开泵", 0)
    set_dev(PUMP, True)
    time.sleep(min(3, PUMP_MAX_SEC))
    set_dev(PUMP, False)
    print("   [泵停] 保压 2s")
    time.sleep(2)

    step("3. 左区放气: 开左阀", 0)
    set_dev(VALVE_L, True)
    time.sleep(3)
    set_dev(VALVE_L, False)
    time.sleep(1)

    step("4. 右区放气: 开右阀", 0)
    set_dev(VALVE_R, True)
    time.sleep(3)
    set_dev(VALVE_R, False)

    print("\n" + "=" * 50)
    print("测试完成, 请确认:")
    print("  a) 泵/左阀/右阀 三个继电器都有独立咔哒声?")
    print("  b) 接了气囊的话: 充气鼓起, 分区放气各自瘪下?")
    print("  c) 若继电器反逻辑(上电常吸合) -> 模块换跳线或改 ACTIVE_LOW")
    print("=" * 50)

except KeyboardInterrupt:
    print("\n[急停] 排气中...")

finally:
    all_off_safe()
    GPIO.cleanup()
    print("[清理] 已排气, GPIO 已释放")
