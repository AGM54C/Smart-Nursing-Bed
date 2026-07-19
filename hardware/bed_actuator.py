#!/usr/bin/env python3
"""
智能护理病床 - 推杆升降控制

硬件: L298N #3 (专用, 与轮子驱动板 #1/#2 完全独立)
  ACTUATOR_IN1 = GPIO13  → L298N #3  IN1
  ACTUATOR_IN2 = GPIO19  → L298N #3  IN2
  ACTUATOR_EN  = GPIO26  → L298N #3  ENA (PWM)
  L298N #3 12V → 12V总线
  L298N #3 GND → GND总线

优点: 电机反电动势不影响推杆控制; 推杆满载电流≈2A，独立供给更稳定
支持: 升起/降下/停止/定时
"""


import time
import threading

try:
    import RPi.GPIO as GPIO
except ImportError:
    from motor_control import MockGPIO as _MG
    GPIO = _MG()

from config import *


class BedActuator:
    """电动推杆控制"""

    def __init__(self):
        GPIO.setmode(GPIO.BCM)

        GPIO.setup(ACTUATOR_IN1, GPIO.OUT)
        GPIO.setup(ACTUATOR_IN2, GPIO.OUT)
        GPIO.setup(ACTUATOR_EN, GPIO.OUT)

        self.pwm = GPIO.PWM(ACTUATOR_EN, PWM_FREQ)
        self.pwm.start(0)

        self._state = "down"  # "up", "down", "moving"
        self._timer = None
        print("[Actuator] Initialized")

    def raise_bed(self, duration=None, speed=80):
        """
        升起靠背
        duration: 运行时间(秒), None=完全升起
        """
        if duration is None:
            duration = ACTUATOR_RAISE_TIME

        print(f"[Actuator] Raising ({duration}s, speed={speed}%)")
        self._state = "moving"

        GPIO.output(ACTUATOR_IN1, GPIO.HIGH)
        GPIO.output(ACTUATOR_IN2, GPIO.LOW)
        self.pwm.ChangeDutyCycle(speed)

        # 定时停止
        self._cancel_timer()
        self._timer = threading.Timer(duration, self._auto_stop, args=["up"])
        self._timer.start()

    def lower_bed(self, duration=None, speed=80):
        """
        降低靠背
        duration: 运行时间(秒), None=完全降下
        """
        if duration is None:
            duration = ACTUATOR_LOWER_TIME

        print(f"[Actuator] Lowering ({duration}s, speed={speed}%)")
        self._state = "moving"

        GPIO.output(ACTUATOR_IN1, GPIO.LOW)
        GPIO.output(ACTUATOR_IN2, GPIO.HIGH)
        self.pwm.ChangeDutyCycle(speed)

        self._cancel_timer()
        self._timer = threading.Timer(duration, self._auto_stop, args=["down"])
        self._timer.start()

    def stop(self):
        """立即停止"""
        GPIO.output(ACTUATOR_IN1, GPIO.LOW)
        GPIO.output(ACTUATOR_IN2, GPIO.LOW)
        self.pwm.ChangeDutyCycle(0)
        self._cancel_timer()
        print(f"[Actuator] Stopped (state={self._state})")

    def _auto_stop(self, final_state):
        GPIO.output(ACTUATOR_IN1, GPIO.LOW)
        GPIO.output(ACTUATOR_IN2, GPIO.LOW)
        self.pwm.ChangeDutyCycle(0)
        self._state = final_state
        print(f"[Actuator] Auto-stopped → {final_state}")

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def get_state(self):
        return self._state

    def toggle(self):
        """切换升降状态"""
        if self._state == "down" or self._state == "moving":
            self.raise_bed()
        else:
            self.lower_bed()

    def cleanup(self):
        self.stop()
        self.pwm.stop()
