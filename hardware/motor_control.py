#!/usr/bin/env python3
"""
智能护理病床 - L298N 电机驱动控制

硬件配置:
  L298N #1 → 前轮 (左前 Channel A, 右前 Channel B)
  L298N #2 → 后轮 (左后 Channel A, 右后 Channel B)
  L298N #3 → 电动推杆 (见 bed_actuator.py)

控制4WD底盘: 前进/后退/左转/右转/旋转/停止
支持PWM调速
"""


import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    # PC调试模式: 模拟GPIO
    print("[Motor] ⚠️ RPi.GPIO not available, using mock mode")

    class MockGPIO:
        BCM = "BCM"
        OUT = "OUT"
        IN = "IN"
        HIGH = 1
        LOW = 0

        @staticmethod
        def setmode(m): pass
        @staticmethod
        def setup(pin, mode): pass
        @staticmethod
        def output(pin, val): pass
        @staticmethod
        def cleanup(): pass

        class PWM:
            def __init__(self, pin, freq):
                self.pin = pin
            def start(self, dc): pass
            def ChangeDutyCycle(self, dc): pass
            def stop(self): pass

    GPIO = MockGPIO()

from config import *


class MotorController:
    """L298N 4WD 电机控制器"""

    def __init__(self):
        GPIO.setmode(GPIO.BCM)

        # 设置所有电机引脚为输出
        motor_pins = [
            MOTOR_LEFT_IN1, MOTOR_LEFT_IN2,
            MOTOR_RIGHT_IN1, MOTOR_RIGHT_IN2,
            MOTOR_REAR_LEFT_IN1, MOTOR_REAR_LEFT_IN2,
            MOTOR_REAR_RIGHT_IN1, MOTOR_REAR_RIGHT_IN2,
        ]
        for pin in motor_pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        # PWM调速
        GPIO.setup(MOTOR_ENA, GPIO.OUT)
        GPIO.setup(MOTOR_ENB, GPIO.OUT)
        GPIO.setup(MOTOR_ENC, GPIO.OUT)
        GPIO.setup(MOTOR_END, GPIO.OUT)

        self.pwm_a = GPIO.PWM(MOTOR_ENA, PWM_FREQ)
        self.pwm_b = GPIO.PWM(MOTOR_ENB, PWM_FREQ)
        self.pwm_c = GPIO.PWM(MOTOR_ENC, PWM_FREQ)
        self.pwm_d = GPIO.PWM(MOTOR_END, PWM_FREQ)

        self.pwm_a.start(0)
        self.pwm_b.start(0)
        self.pwm_c.start(0)
        self.pwm_d.start(0)

        self._speed = MOTOR_SPEED_DEFAULT
        self._running = False
        print(f"[Motor] Initialized, default speed={self._speed}%")

    def set_speed(self, speed):
        """设置速度 0-100"""
        self._speed = max(0, min(100, speed))
        if self._running:
            self._apply_speed()

    def _apply_speed(self):
        self.pwm_a.ChangeDutyCycle(self._speed)
        self.pwm_b.ChangeDutyCycle(self._speed)
        self.pwm_c.ChangeDutyCycle(self._speed)
        self.pwm_d.ChangeDutyCycle(self._speed)

    def _set_motors(self, left_fwd, left_bwd, right_fwd, right_bwd):
        """设置四轮方向"""
        # 前左
        GPIO.output(MOTOR_LEFT_IN1, GPIO.HIGH if left_fwd else GPIO.LOW)
        GPIO.output(MOTOR_LEFT_IN2, GPIO.HIGH if left_bwd else GPIO.LOW)
        # 前右
        GPIO.output(MOTOR_RIGHT_IN1, GPIO.HIGH if right_fwd else GPIO.LOW)
        GPIO.output(MOTOR_RIGHT_IN2, GPIO.HIGH if right_bwd else GPIO.LOW)
        # 后左
        GPIO.output(MOTOR_REAR_LEFT_IN1, GPIO.HIGH if left_fwd else GPIO.LOW)
        GPIO.output(MOTOR_REAR_LEFT_IN2, GPIO.HIGH if left_bwd else GPIO.LOW)
        # 后右
        GPIO.output(MOTOR_REAR_RIGHT_IN1, GPIO.HIGH if right_fwd else GPIO.LOW)
        GPIO.output(MOTOR_REAR_RIGHT_IN2, GPIO.HIGH if right_bwd else GPIO.LOW)

        self._running = True
        self._apply_speed()

    def forward(self, speed=None):
        """前进"""
        if speed: self._speed = speed
        self._set_motors(True, False, True, False)
        print(f"[Motor] Forward @ {self._speed}%")

    def backward(self, speed=None):
        """后退"""
        if speed: self._speed = speed
        self._set_motors(False, True, False, True)
        print(f"[Motor] Backward @ {self._speed}%")

    def turn_left(self, speed=None):
        """左转 (左轮慢/停, 右轮正转)"""
        if speed: self._speed = speed
        # 左轮停, 右轮转
        GPIO.output(MOTOR_LEFT_IN1, GPIO.LOW)
        GPIO.output(MOTOR_LEFT_IN2, GPIO.LOW)
        GPIO.output(MOTOR_RIGHT_IN1, GPIO.HIGH)
        GPIO.output(MOTOR_RIGHT_IN2, GPIO.LOW)
        GPIO.output(MOTOR_REAR_LEFT_IN1, GPIO.LOW)
        GPIO.output(MOTOR_REAR_LEFT_IN2, GPIO.LOW)
        GPIO.output(MOTOR_REAR_RIGHT_IN1, GPIO.HIGH)
        GPIO.output(MOTOR_REAR_RIGHT_IN2, GPIO.LOW)
        self._running = True
        self.pwm_a.ChangeDutyCycle(0)
        self.pwm_b.ChangeDutyCycle(self._speed)
        self.pwm_c.ChangeDutyCycle(0)
        self.pwm_d.ChangeDutyCycle(self._speed)
        print(f"[Motor] Turn Left @ {self._speed}%")

    def turn_right(self, speed=None):
        """右转 (左轮正转, 右轮慢/停)"""
        if speed: self._speed = speed
        GPIO.output(MOTOR_LEFT_IN1, GPIO.HIGH)
        GPIO.output(MOTOR_LEFT_IN2, GPIO.LOW)
        GPIO.output(MOTOR_RIGHT_IN1, GPIO.LOW)
        GPIO.output(MOTOR_RIGHT_IN2, GPIO.LOW)
        GPIO.output(MOTOR_REAR_LEFT_IN1, GPIO.HIGH)
        GPIO.output(MOTOR_REAR_LEFT_IN2, GPIO.LOW)
        GPIO.output(MOTOR_REAR_RIGHT_IN1, GPIO.LOW)
        GPIO.output(MOTOR_REAR_RIGHT_IN2, GPIO.LOW)
        self._running = True
        self.pwm_a.ChangeDutyCycle(self._speed)
        self.pwm_b.ChangeDutyCycle(0)
        self.pwm_c.ChangeDutyCycle(self._speed)
        self.pwm_d.ChangeDutyCycle(0)
        print(f"[Motor] Turn Right @ {self._speed}%")

    def spin_left(self, speed=None):
        """原地左旋 (左轮反转, 右轮正转)"""
        if speed: self._speed = speed
        self._set_motors(False, True, True, False)
        print(f"[Motor] Spin Left @ {self._speed}%")

    def spin_right(self, speed=None):
        """原地右旋 (左轮正转, 右轮反转)"""
        if speed: self._speed = speed
        self._set_motors(True, False, False, True)
        print(f"[Motor] Spin Right @ {self._speed}%")

    def stop(self):
        """停车"""
        self._set_motors(False, False, False, False)
        self.pwm_a.ChangeDutyCycle(0)
        self.pwm_b.ChangeDutyCycle(0)
        self.pwm_c.ChangeDutyCycle(0)
        self.pwm_d.ChangeDutyCycle(0)
        self._running = False
        print("[Motor] STOPPED")

    def cleanup(self):
        """释放资源"""
        self.stop()
        self.pwm_a.stop()
        self.pwm_b.stop()
        self.pwm_c.stop()
        self.pwm_d.stop()
        print("[Motor] Cleaned up")
