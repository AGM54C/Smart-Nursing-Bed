#!/usr/bin/env python3
"""
智能护理病床 - 超声波避障模块

3个HC-SR04: 前/左/右
支持异步测距和障碍物检测
"""

import time
import threading

try:
    import RPi.GPIO as GPIO
except ImportError:
    from motor_control import MockGPIO as _MG
    GPIO = _MG()

from config import *


class ObstacleAvoidance:
    """HC-SR04 超声波避障"""

    def __init__(self):
        GPIO.setmode(GPIO.BCM)

        # 配置引脚
        self.sensors = {
            "front": (ULTRA_FRONT_TRIG, ULTRA_FRONT_ECHO),
            "left": (ULTRA_LEFT_TRIG, ULTRA_LEFT_ECHO),
            "right": (ULTRA_RIGHT_TRIG, ULTRA_RIGHT_ECHO),
        }

        for name, (trig, echo) in self.sensors.items():
            GPIO.setup(trig, GPIO.OUT)
            GPIO.setup(echo, GPIO.IN)
            GPIO.output(trig, GPIO.LOW)

        # 最新距离
        self.distances = {"front": 999, "left": 999, "right": 999}
        self._lock = threading.Lock()
        self._running = False

        print("[Obstacle] Initialized (3x HC-SR04)")

    def measure_distance(self, sensor_name):
        """测量单个传感器距离 (cm)"""
        if sensor_name not in self.sensors:
            return 999

        trig, echo = self.sensors[sensor_name]

        try:
            # 发送10us脉冲
            GPIO.output(trig, GPIO.HIGH)
            time.sleep(0.00001)
            GPIO.output(trig, GPIO.LOW)

            # 等待回波开始 (超时保护)
            start = time.time()
            timeout = start + 0.03  # 30ms超时 (~5m)

            while GPIO.input(echo) == GPIO.LOW:
                start = time.time()
                if start > timeout:
                    return 999

            # 等待回波结束
            end = time.time()
            timeout = end + 0.03

            while GPIO.input(echo) == GPIO.HIGH:
                end = time.time()
                if end > timeout:
                    return 999

            # 计算距离
            duration = end - start
            distance = duration * 34300 / 2  # 声速340m/s

            # 合理性校验
            if distance < 2 or distance > 400:
                return 999

            return round(distance, 1)

        except Exception as e:
            return 999

    def scan_all(self):
        """扫描所有传感器"""
        with self._lock:
            for name in self.sensors:
                self.distances[name] = self.measure_distance(name)
                time.sleep(0.02)  # 传感器间间隔避免干扰

        return self.get_distances()

    def get_distances(self):
        """获取最新距离"""
        with self._lock:
            return self.distances.copy()

    def is_blocked(self, direction="front"):
        """指定方向是否有障碍物 (< STOP距离)"""
        with self._lock:
            return self.distances.get(direction, 999) < OBSTACLE_DISTANCE_STOP

    def should_slow_down(self, direction="front"):
        """指定方向是否需要减速"""
        with self._lock:
            d = self.distances.get(direction, 999)
            return OBSTACLE_DISTANCE_STOP <= d < OBSTACLE_DISTANCE_SLOW

    def get_best_direction(self):
        """
        获取最佳行进方向
        返回: "forward", "left", "right", "blocked"
        """
        with self._lock:
            f = self.distances["front"]
            l = self.distances["left"]
            r = self.distances["right"]

        if f >= OBSTACLE_DISTANCE_SLOW:
            return "forward"
        elif f < OBSTACLE_DISTANCE_STOP:
            if l > r and l >= OBSTACLE_DISTANCE_SLOW:
                return "left"
            elif r >= OBSTACLE_DISTANCE_SLOW:
                return "right"
            else:
                return "blocked"
        else:
            return "forward"  # 减速前进

    # ─── 后台持续扫描 ───

    def start_continuous(self, interval=0.1):
        """启动后台持续扫描"""
        self._running = True

        def _scan_loop():
            while self._running:
                self.scan_all()
                time.sleep(interval)

        t = threading.Thread(target=_scan_loop, daemon=True)
        t.start()
        print(f"[Obstacle] Continuous scanning started ({interval}s interval)")

    def stop_continuous(self):
        """停止后台扫描"""
        self._running = False

    def cleanup(self):
        self.stop_continuous()
