#!/usr/bin/env python3
"""
智能护理病床 - 自主导航模块 (v2.0 NearLink升级版)

支持五种导航模式:
  1. LINE_FOLLOW:      家用循迹模式 (沿黑线行驶)
  2. RFID_SEEK:        [DEPRECATED] 医院寻房模式 (循迹+RFID识别)
  3. NEARLINK_HYBRID:  ★ 方案B: 循迹+NearLink混合 (巡线走路+NearLink测距感知)
  4. NEARLINK_NAV:     [预留] 方案A: 纯NearLink坐标导航 (路径规划+航向PID)
  5. MANUAL:           手动遥控模式
"""

import time
import threading
from enum import Enum

try:
    import RPi.GPIO as GPIO
except ImportError:
    from motor_control import MockGPIO as _MG
    GPIO = _MG()

from config import *
from motor_control import MotorController
from obstacle_avoidance import ObstacleAvoidance

# RFID: deprecated but importable for fallback
try:
    from rfid_reader import RFIDReader
except ImportError:
    RFIDReader = None

# NearLink定位
try:
    from nearlink_positioning import NearLinkPositioning
except ImportError:
    NearLinkPositioning = None
    print("[Nav] ⚠️ NearLink positioning not available")


class NavMode(Enum):
    IDLE = "idle"
    LINE_FOLLOW = "line_follow"
    RFID_SEEK = "rfid_seek"                # DEPRECATED
    NEARLINK_HYBRID = "nearlink_hybrid"    # 方案B: 巡线+NearLink
    NEARLINK_NAV = "nearlink_nav"          # 方案A预留: 纯坐标导航
    MANUAL = "manual"


class NavState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED_OBSTACLE = "paused_obstacle"
    APPROACHING = "approaching"    # NearLink: 接近目标, 已减速
    ARRIVED = "arrived"
    ERROR = "error"


class Navigator:
    """自主导航控制器 v2.0"""

    def __init__(self, motor=None, obstacle=None, rfid=None, nearlink=None):
        self.motor = motor or MotorController()
        self.obstacle = obstacle or ObstacleAvoidance()

        # RFID (deprecated, 保留fallback)
        if rfid:
            self.rfid = rfid
        elif RFIDReader:
            self.rfid = RFIDReader()
        else:
            self.rfid = None

        # NearLink定位系统
        if nearlink:
            self.nearlink = nearlink
        elif NearLinkPositioning and NEARLINK_ENABLED:
            self.nearlink = NearLinkPositioning()
        else:
            self.nearlink = None

        # 状态
        self.mode = NavMode.IDLE
        self.state = NavState.STOPPED
        self.target_room = NEARLINK_TARGET_ROOM if NEARLINK_ENABLED else RFID_TARGET_ROOM
        self._running = False
        self._thread = None
        self._callback = None  # 到达回调

        # 循迹传感器
        GPIO.setmode(GPIO.BCM)
        for pin in LINE_SENSORS:
            GPIO.setup(pin, GPIO.IN)

        print("[Nav] v2.0 Initialized")
        if self.nearlink:
            print("[Nav] ✅ NearLink positioning available")
        if self.rfid:
            print("[Nav] ⚠️ RFID available (deprecated fallback)")

    # ═══════════════════════════════════════════
    #  循迹算法 (方案B和原始模式共用)
    # ═══════════════════════════════════════════

    def read_line_sensors(self):
        """
        读取循迹传感器 (数量由 LINE_SENSORS 决定, 当前3路: [L, C, R])
        返回: 从左到右的列表, 1=在黑线上, 0=不在
        """
        readings = []
        for pin in LINE_SENSORS:
            val = GPIO.input(pin)
            # TCRT5000: 黑线反射弱→输出LOW
            readings.append(1 if val == GPIO.LOW else 0)
        return readings

    def _follow_line(self):
        """循迹算法: PID风格的循迹"""
        sensors = self.read_line_sensors()
        # sensors 从左到右, 数量自适应 (3路=[L,C,R], 5路=[L2,L1,C,R1,R2])

        # 权重对称分布, 偏差归一化到 -1..+1 (左偏为负, 右偏为正)
        n = len(sensors)
        half = (n - 1) / 2
        weights = [i - half for i in range(n)]
        total = sum(sensors)

        if total == 0:
            # 全部脱离黑线 → 停车
            return "lost"

        position = sum(s * w for s, w in zip(sensors, weights)) / total / half

        # 控制策略 (阈值基于归一化偏差, 与原5路 0.3/1.0 等价)
        if abs(position) < 0.15:
            self.motor.forward(MOTOR_SPEED_DEFAULT)
            return "straight"
        elif position < -0.5:
            self.motor.turn_left(MOTOR_SPEED_SLOW)
            return "left_sharp"
        elif position < 0:
            # 轻微左偏 → 微调
            self.motor.forward(MOTOR_SPEED_DEFAULT)
            return "left_slight"
        elif position > 0.5:
            self.motor.turn_right(MOTOR_SPEED_SLOW)
            return "right_sharp"
        else:
            self.motor.forward(MOTOR_SPEED_DEFAULT)
            return "right_slight"

    # ═══════════════════════════════════════════
    #  模式1: 循迹导航 (不变)
    # ═══════════════════════════════════════════

    def _nav_loop_line_follow(self):
        """循迹导航主循环"""
        print("[Nav] Line-follow mode started")
        self.state = NavState.RUNNING
        self.obstacle.start_continuous(interval=0.1)

        while self._running:
            # 1. 避障检查
            if self.obstacle.is_blocked("front"):
                self.motor.stop()
                self.state = NavState.PAUSED_OBSTACLE
                print("[Nav] ⚠️ Obstacle detected! Pausing...")
                while self._running and self.obstacle.is_blocked("front"):
                    time.sleep(0.2)
                if self._running:
                    print("[Nav] Obstacle cleared, resuming")
                    self.state = NavState.RUNNING
                continue

            # 2. 减速检查
            if self.obstacle.should_slow_down("front"):
                self.motor.set_speed(MOTOR_SPEED_SLOW)
            else:
                self.motor.set_speed(MOTOR_SPEED_DEFAULT)

            # 3. 循迹
            result = self._follow_line()
            if result == "lost":
                self.motor.stop()
                print("[Nav] Line lost! Stopping")
                self.state = NavState.STOPPED
                break

            time.sleep(0.05)  # 20Hz控制频率

        self.motor.stop()
        self.obstacle.stop_continuous()

    # ═══════════════════════════════════════════
    #  模式2: RFID寻房 (DEPRECATED, 保留fallback)
    # ═══════════════════════════════════════════

    def _nav_loop_rfid_seek(self):
        """RFID寻房导航主循环 [DEPRECATED]"""
        print(f"[Nav] ⚠️ RFID-seek mode (DEPRECATED), target room: {self.target_room}")

        if not self.rfid:
            print("[Nav] ❌ RFID reader not available, aborting")
            self.state = NavState.ERROR
            return

        self.state = NavState.RUNNING
        self.obstacle.start_continuous(interval=0.1)

        while self._running:
            # 1. 避障
            if self.obstacle.is_blocked("front"):
                self.motor.stop()
                self.state = NavState.PAUSED_OBSTACLE
                while self._running and self.obstacle.is_blocked("front"):
                    time.sleep(0.2)
                if self._running:
                    self.state = NavState.RUNNING
                continue

            # 2. RFID扫描
            match = self.rfid.check_room(self.target_room)
            if match is True:
                # 找到目标病房! 执行进入动作
                print(f"[Nav] 🎯 Room {self.target_room} found! Turning in...")
                self.motor.stop()
                time.sleep(0.3)

                # 右转90度进入病房
                self.motor.spin_right(MOTOR_SPEED_SLOW)
                time.sleep(1.5)  # 约90度

                # 前进一小段进入房间
                self.motor.forward(MOTOR_SPEED_SLOW)
                time.sleep(1.0)

                self.motor.stop()
                self.state = NavState.ARRIVED
                print(f"[Nav] ✅ Arrived at room {self.target_room}!")

                if self._callback:
                    self._callback(self.target_room)
                break

            elif match is False:
                # 扫到了别的房间, 继续前进
                _, text = self.rfid.get_last_read()
                print(f"[Nav] Passed room {text}, not target")

            # 3. 循迹前进
            if self.obstacle.should_slow_down("front"):
                self.motor.set_speed(MOTOR_SPEED_SLOW)
            else:
                self.motor.set_speed(MOTOR_SPEED_DEFAULT)

            self._follow_line()
            time.sleep(0.05)

        self.motor.stop()
        self.obstacle.stop_continuous()

    # ═══════════════════════════════════════════
    #  模式3: ★ NearLink+RFID 双保险混合导航 (方案B)
    #  巡线走路径 + NearLink连续测距 + RFID到达确认
    # ═══════════════════════════════════════════

    def _nav_loop_nearlink_hybrid(self):
        """
        NearLink+RFID双保险混合导航主循环 (方案B)

        双保险逻辑:
          - 循迹传感器: 控制行走路径 (沿黑线)
          - NearLink:    实时提供到目标的连续距离, 用于减速和接近感知
          - RFID:        到达病房门口时扫描RFID标签, 作为物理确认

        到达判定 (三重验证):
          ① NearLink距离 < 阈值 → 初步判定到达
          ② RFID扫到目标房间标签 → 物理确认到达
          ③ 任一条件满足即触发到达, 双条件同时满足为最高置信度
        """
        print(f"[Nav] ★ NearLink+RFID hybrid mode started, target: {self.target_room}")

        has_nearlink = self.nearlink is not None
        has_rfid = self.rfid is not None

        if not has_nearlink and not has_rfid:
            print("[Nav] ❌ Neither NearLink nor RFID available, aborting")
            self.state = NavState.ERROR
            return

        if not has_nearlink:
            print("[Nav] ⚠️ NearLink不可用, 仅使用RFID模式")
        if not has_rfid:
            print("[Nav] ⚠️ RFID不可用, 仅使用NearLink测距模式")

        # 启动NearLink定位
        if has_nearlink:
            self.nearlink.set_target_room(self.target_room)
            self.nearlink.start()

        self.state = NavState.RUNNING
        self.obstacle.start_continuous(interval=0.1)

        last_dist_report = 0
        report_interval = 2.0  # 每2秒报告一次距离

        # 双保险到达状态
        nl_arrived = False   # NearLink判定到达
        rfid_arrived = False # RFID判定到达

        while self._running:
            # 1. 避障检查 (最高优先级)
            if self.obstacle.is_blocked("front"):
                self.motor.stop()
                self.state = NavState.PAUSED_OBSTACLE
                print("[Nav] ⚠️ Obstacle detected! Pausing...")
                while self._running and self.obstacle.is_blocked("front"):
                    time.sleep(0.2)
                if self._running:
                    print("[Nav] Obstacle cleared, resuming")
                    self.state = NavState.RUNNING
                continue

            # 2. NearLink位置感知
            dist = float('inf')
            if has_nearlink:
                dist = self.nearlink.get_distance_to_target()
                nl_check = self.nearlink.check_arrived(self.target_room)
                if nl_check is True:
                    nl_arrived = True

                # 周期性距离播报
                now = time.time()
                if now - last_dist_report > report_interval:
                    pos = self.nearlink.get_position()
                    if pos.get("valid"):
                        rfid_hint = " [RFID待确认]" if nl_arrived and not rfid_arrived else ""
                        print(f"[Nav] 📍 ({pos['x']:.1f}, {pos['y']:.1f}), "
                              f"距{self.target_room}号: {dist:.1f}m{rfid_hint}")
                    last_dist_report = now

            # 3. RFID扫描 (并行检测)
            if has_rfid:
                rfid_match = self.rfid.check_room(self.target_room)
                if rfid_match is True:
                    rfid_arrived = True
                    print(f"[Nav] 📇 RFID确认: 到达{self.target_room}号病房!")
                elif rfid_match is False:
                    # 扫到别的房间
                    _, text = self.rfid.get_last_read()
                    print(f"[Nav] 📇 经过{text}号房间, 非目标")

            # 4. ★ 双保险到达判定
            confirm_source = None
            if nl_arrived and rfid_arrived:
                confirm_source = "NearLink+RFID双重确认"
            elif rfid_arrived:
                confirm_source = "RFID物理确认"
            elif nl_arrived:
                confirm_source = "NearLink测距确认"

            if confirm_source:
                confidence = "🔒 最高" if (nl_arrived and rfid_arrived) else "✅ 单源"
                print(f"[Nav] 🎯 Room {self.target_room} reached! "
                      f"({confirm_source}, 置信度: {confidence})")
                if has_nearlink:
                    print(f"    NearLink距离: {dist:.2f}m")
                print(f"    RFID确认: {'✅' if rfid_arrived else '❌ 未扫到'}")

                self.motor.stop()
                time.sleep(0.3)

                # 右转90度进入病房
                print(f"[Nav] Turning into room {self.target_room}...")
                self.motor.spin_right(MOTOR_SPEED_SLOW)
                time.sleep(1.5)  # 约90度

                # 前进一小段进入房间
                self.motor.forward(MOTOR_SPEED_SLOW)
                time.sleep(1.0)

                self.motor.stop()
                self.state = NavState.ARRIVED
                print(f"[Nav] ✅ Arrived at room {self.target_room}! "
                      f"(确认方式: {confirm_source})")

                if self._callback:
                    self._callback(self.target_room)
                break

            # 5. 速度控制 (NearLink距离感知 + 超声波)
            if has_nearlink and self.nearlink.should_slow_down(self.target_room):
                # 接近目标, 低速行驶
                self.motor.set_speed(MOTOR_SPEED_SLOW)
                if self.state != NavState.APPROACHING:
                    self.state = NavState.APPROACHING
                    print(f"[Nav] 🐢 Approaching room {self.target_room}, "
                          f"slowing down (dist={dist:.1f}m)")
            elif self.obstacle.should_slow_down("front"):
                self.motor.set_speed(MOTOR_SPEED_SLOW)
            else:
                self.motor.set_speed(MOTOR_SPEED_DEFAULT)

            # 6. 循迹行走
            result = self._follow_line()
            if result == "lost":
                self.motor.stop()
                print("[Nav] Line lost! Stopping")
                self.state = NavState.ERROR
                break

            time.sleep(0.05)  # 20Hz

        self.motor.stop()
        self.obstacle.stop_continuous()
        # NearLink保持运行 (不关闭, 继续提供位置)

    # ═══════════════════════════════════════════
    #  模式4: [预留] 纯NearLink坐标导航 (方案A)
    # ═══════════════════════════════════════════

    def _nav_loop_nearlink_nav(self):
        """
        [方案A预留] 纯NearLink坐标导航

        未来实现:
          - 不依赖巡线, 完全基于NearLink坐标
          - A*/Dijkstra路径规划
          - 航向PID控制
          - IMU辅助航向稳定

        当前: 输出提示后回退到方案B
        """
        print("[Nav] ⚠️ NearLink NAV mode (Plan A) is not yet implemented")
        print("[Nav] Falling back to NearLink HYBRID mode (Plan B)")

        # 回退到方案B
        self._nav_loop_nearlink_hybrid()

    # ═══════════════════════════════════════════
    #  公开接口
    # ═══════════════════════════════════════════

    def start_line_follow(self):
        """启动循迹导航"""
        self.stop()
        self.mode = NavMode.LINE_FOLLOW
        self._running = True
        self._thread = threading.Thread(target=self._nav_loop_line_follow, daemon=True)
        self._thread.start()

    def start_rfid_seek(self, target_room=None, on_arrival=None):
        """启动纯RFID寻房导航 (仅RFID, 无NearLink)"""
        print("[Nav] Starting RFID-only seek mode")
        self.stop()
        if target_room:
            self.target_room = str(target_room)
        self._callback = on_arrival
        self.mode = NavMode.RFID_SEEK
        self._running = True
        self._thread = threading.Thread(target=self._nav_loop_rfid_seek, daemon=True)
        self._thread.start()

    def start_nearlink_hybrid(self, target_room=None, on_arrival=None):
        """★ 启动NearLink混合导航 (方案B: 巡线+NearLink)"""
        self.stop()
        if target_room:
            self.target_room = str(target_room)
        self._callback = on_arrival
        self.mode = NavMode.NEARLINK_HYBRID
        self._running = True
        self._thread = threading.Thread(target=self._nav_loop_nearlink_hybrid, daemon=True)
        self._thread.start()

    def start_nearlink_nav(self, target_room=None, on_arrival=None):
        """[预留] 启动NearLink坐标导航 (方案A)"""
        self.stop()
        if target_room:
            self.target_room = str(target_room)
        self._callback = on_arrival
        self.mode = NavMode.NEARLINK_NAV
        self._running = True
        self._thread = threading.Thread(target=self._nav_loop_nearlink_nav, daemon=True)
        self._thread.start()

    def start_seek(self, target_room=None, on_arrival=None):
        """
        智能寻房 (自动选择最优方案)

        优先级: NearLink混合 > RFID > 错误
        """
        if self.nearlink and NEARLINK_ENABLED:
            return self.start_nearlink_hybrid(target_room, on_arrival)
        elif self.rfid:
            return self.start_rfid_seek(target_room, on_arrival)
        else:
            print("[Nav] ❌ No positioning system available!")
            self.state = NavState.ERROR

    def stop(self):
        """停止导航"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        self.motor.stop()
        self.mode = NavMode.IDLE
        self.state = NavState.STOPPED
        print("[Nav] Stopped")

    def get_status(self):
        """获取导航状态"""
        status = {
            "mode": self.mode.value,
            "state": self.state.value,
            "target_room": self.target_room,
            "distances": self.obstacle.get_distances(),
            "line_sensors": self.read_line_sensors() if self.mode != NavMode.IDLE else [],
        }

        # NearLink增强信息
        if self.nearlink and self.mode in (NavMode.NEARLINK_HYBRID, NavMode.NEARLINK_NAV):
            nl_status = self.nearlink.get_status()
            status["nearlink"] = nl_status
            status["distance_to_target"] = nl_status.get("distance_to_target")
            status["position"] = nl_status.get("position")

        # 双保险定位状态
        status["positioning"] = {
            "nearlink": self.nearlink is not None,
            "rfid": self.rfid is not None,
            "mode": "dual" if (self.nearlink and self.rfid) else
                    "nearlink_only" if self.nearlink else
                    "rfid_only" if self.rfid else "none"
        }

        return status

    # ─── 手动遥控 ───

    def manual_forward(self, speed=None):
        self.mode = NavMode.MANUAL
        self.motor.forward(speed)

    def manual_backward(self, speed=None):
        self.mode = NavMode.MANUAL
        self.motor.backward(speed)

    def manual_left(self, speed=None):
        self.mode = NavMode.MANUAL
        self.motor.turn_left(speed)

    def manual_right(self, speed=None):
        self.mode = NavMode.MANUAL
        self.motor.turn_right(speed)

    def manual_stop(self):
        self.motor.stop()

    def cleanup(self):
        self.stop()
        self.motor.cleanup()
        self.obstacle.cleanup()
        if self.rfid:
            self.rfid.cleanup()
        if self.nearlink:
            self.nearlink.stop()
