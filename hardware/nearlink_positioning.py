#!/usr/bin/env python3
"""
智能护理病床 - NearLink星闪室内定位模块

基于Hi3863 SLE测距数据, 在树莓派端执行三边定位+卡尔曼滤波
提供实时2D坐标给导航模块

硬件架构:
  Hi3863 锚点 (固定在走廊) ──SLE测距──► Hi3863 床载标签
  Hi3863 锚点 ──WiFi/MQTT──► 树莓派 (本模块解算坐标)
"""

import math
import time
import json
import threading
from collections import deque

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None
    print("[NearLink] ⚠️ paho-mqtt not available")

from config import *


class KalmanFilter2D:
    """简易2D卡尔曼滤波器 - 平滑定位轨迹"""

    def __init__(self, process_noise=0.05, measure_noise=0.3):
        # 状态: [x, y, vx, vy]
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0

        # 协方差矩阵 (简化为对角)
        self.p_x = 1.0
        self.p_y = 1.0
        self.p_vx = 1.0
        self.p_vy = 1.0

        self.q = process_noise   # 过程噪声
        self.r = measure_noise   # 测量噪声

        self._initialized = False

    def predict(self, dt):
        """预测步骤"""
        if not self._initialized:
            return

        # 状态预测 (匀速模型)
        self.x += self.vx * dt
        self.y += self.vy * dt

        # 协方差预测
        self.p_x += self.p_vx * dt * dt + self.q
        self.p_y += self.p_vy * dt * dt + self.q
        self.p_vx += self.q
        self.p_vy += self.q

    def update(self, meas_x, meas_y):
        """更新步骤 (用测量值修正)"""
        if not self._initialized:
            self.x = meas_x
            self.y = meas_y
            self._initialized = True
            return

        # 卡尔曼增益
        k_x = self.p_x / (self.p_x + self.r)
        k_y = self.p_y / (self.p_y + self.r)

        # 速度估计 (从位置差推算)
        dx = meas_x - self.x
        dy = meas_y - self.y

        # 状态更新
        self.x += k_x * dx
        self.y += k_y * dy

        # 协方差更新
        self.p_x *= (1 - k_x)
        self.p_y *= (1 - k_y)

    def get_position(self):
        """获取滤波后的位置"""
        return self.x, self.y

    def is_initialized(self):
        return self._initialized


class TrilatSolver:
    """三边定位解算器 (加权最小二乘法)"""

    @staticmethod
    def solve(anchors_with_distances):
        """
        三边定位: 从多个锚点到标签的距离计算标签位置

        输入: [(x1,y1,d1), (x2,y2,d2), (x3,y3,d3), ...]
              (xi,yi)=锚点坐标, di=到标签的测距值

        输出: (x, y) 标签坐标, 或 None 如果不可解

        注: 当锚点共线 (如全部安装在走廊同一侧墙壁, Y值相同) 时,
            Y维度不可解, 此时自动退化为1D定位 (仅解X坐标, Y取锚点Y)
        """
        if len(anchors_with_distances) < 3:
            return None

        # 加权最小二乘法 (WLS)
        # 以第一个锚点为参考, 构建线性方程组
        ref = anchors_with_distances[0]
        x1, y1, d1 = ref

        A_rows = []
        b_rows = []

        for i in range(1, len(anchors_with_distances)):
            xi, yi, di = anchors_with_distances[i]

            # 线性化: 2(xi-x1)*x + 2(yi-y1)*y = (di²-d1²) - (xi²-x1²) - (yi²-y1²)
            a_val = 2 * (xi - x1)
            b_val = 2 * (yi - y1)
            c_val = (d1**2 - di**2) + (xi**2 - x1**2) + (yi**2 - y1**2)

            # 权重: 距离越近测距越准, 权重越大
            w = 1.0 / max(di, 0.5)

            A_rows.append((a_val * w, b_val * w))
            b_rows.append(c_val * w)

        # 求解 Ax = b (最小二乘)
        n = len(A_rows)
        if n < 2:
            return None

        # 手动实现 2x2 最小二乘 (避免numpy依赖)
        # A^T A x = A^T b
        ata00 = sum(r[0] * r[0] for r in A_rows)
        ata01 = sum(r[0] * r[1] for r in A_rows)
        ata11 = sum(r[1] * r[1] for r in A_rows)
        atb0 = sum(A_rows[i][0] * b_rows[i] for i in range(n))
        atb1 = sum(A_rows[i][1] * b_rows[i] for i in range(n))

        det = ata00 * ata11 - ata01 * ata01

        if abs(det) < 1e-10:
            # 矩阵近似奇异: 锚点共线
            # 退化为1D定位: 只解X坐标
            if abs(ata00) > 1e-10:
                x = atb0 / ata00
                # Y取所有锚点Y的均值 (共线情况下基本相同)
                y_avg = sum(a[1] for a in anchors_with_distances) / len(anchors_with_distances)
                # 用最近锚点的距离估算Y偏移
                min_dist = min(a[2] for a in anchors_with_distances)
                min_anchor = min(anchors_with_distances, key=lambda a: a[2])
                dx = x - min_anchor[0]
                dy_sq = min_dist**2 - dx**2
                if dy_sq > 0:
                    # 标签在走廊中: 取走廊一侧 (Y < 锚点Y)
                    y = y_avg - math.sqrt(dy_sq)
                else:
                    y = y_avg
                return x, y
            return None

        x = (ata11 * atb0 - ata01 * atb1) / det
        y = (ata00 * atb1 - ata01 * atb0) / det

        return x, y


class NearLinkPositioning:
    """NearLink星闪定位系统 - 树莓派端"""

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False

        # 卡尔曼滤波
        self._kalman = KalmanFilter2D(
            process_noise=NL_KALMAN_PROCESS_NOISE,
            measure_noise=NL_KALMAN_MEASURE_NOISE
        )

        # 最新测距数据 {anchor_id: {"distance": m, "rssi": dBm, "ts": epoch}}
        self._ranging_data = {}

        # 当前位置
        self._position = {"x": 0.0, "y": 0.0, "valid": False, "ts": 0}
        self._last_calc_time = 0

        # 历史轨迹 (最近100个点, 用于可视化)
        self._trajectory = deque(maxlen=100)

        # 到达判定状态
        self._target_room = NEARLINK_TARGET_ROOM
        self._distance_to_target = float('inf')

        # MQTT客户端 (接收锚点测距数据)
        self._mqtt_client = None
        self._position_publisher = None  # 发布解算后坐标

        # 锚点坐标缓存
        self._anchor_coords = {}
        for aid, info in NEARLINK_ANCHORS.items():
            self._anchor_coords[aid] = (info["x"], info["y"])

        print(f"[NearLink] Initialized with {len(NEARLINK_ANCHORS)} anchors")
        for aid, info in NEARLINK_ANCHORS.items():
            print(f"  📍 {aid}: ({info['x']}, {info['y']}) - {info['desc']}")

    # ═══════════════════════════════════════════
    #  MQTT 接收测距数据
    # ═══════════════════════════════════════════

    def _on_ranging_message(self, client, userdata, msg):
        """
        处理锚点上报的SLE测距数据

        消息格式 (JSON):
        {
            "anchor_id": "anchor_01",
            "tag_id": "bed_tag_01",
            "distance": 3.42,      // 米
            "rssi": -65,           // dBm
            "channel": 37,         // SLE信道
            "ts": 1712345678.123   // 时间戳
        }
        """
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            anchor_id = data.get("anchor_id")
            distance = data.get("distance")

            if not anchor_id or distance is None:
                return

            if anchor_id not in self._anchor_coords:
                print(f"[NearLink] ⚠️ Unknown anchor: {anchor_id}")
                return

            # 距离合理性校验 (排除异常值)
            if distance < 0.1 or distance > 50.0:
                return

            with self._lock:
                self._ranging_data[anchor_id] = {
                    "distance": float(distance),
                    "rssi": data.get("rssi", 0),
                    "ts": data.get("ts", time.time())
                }

        except (json.JSONDecodeError, Exception) as e:
            print(f"[NearLink] Ranging parse error: {e}")

    def _connect_mqtt(self):
        """连接MQTT, 订阅测距topic"""
        if mqtt is None:
            return False

        try:
            self._mqtt_client = mqtt.Client(client_id="nearlink-positioning")
            self._mqtt_client.on_message = self._on_ranging_message

            self._mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self._mqtt_client.subscribe(TOPIC_NL_RANGING)
            self._mqtt_client.loop_start()

            print(f"[NearLink] MQTT connected, subscribed to {TOPIC_NL_RANGING}")
            return True
        except Exception as e:
            print(f"[NearLink] MQTT connect failed: {e}")
            return False

    # ═══════════════════════════════════════════
    #  位置解算
    # ═══════════════════════════════════════════

    def _calculate_position(self):
        """
        从测距数据计算位置 (三边定位 + 卡尔曼滤波)
        """
        with self._lock:
            now = time.time()

            # 收集有效的测距数据 (1秒内的)
            valid_ranges = []
            for aid, rdata in self._ranging_data.items():
                age = now - rdata["ts"]
                if age < 1.0 and aid in self._anchor_coords:
                    ax, ay = self._anchor_coords[aid]
                    valid_ranges.append((ax, ay, rdata["distance"]))

            if len(valid_ranges) < NL_MIN_ANCHORS:
                # 锚点不足, 用卡尔曼预测推演
                if self._kalman.is_initialized():
                    dt = now - self._last_calc_time if self._last_calc_time else 0.2
                    self._kalman.predict(dt)
                    x, y = self._kalman.get_position()
                    self._position = {"x": x, "y": y, "valid": True,
                                      "quality": "predicted", "ts": now,
                                      "anchors": len(valid_ranges)}
                    self._last_calc_time = now
                return

        # 三边定位解算
        result = TrilatSolver.solve(valid_ranges)
        if result is None:
            return

        raw_x, raw_y = result

        # 卡尔曼滤波平滑
        now = time.time()
        dt = now - self._last_calc_time if self._last_calc_time else 0.2
        self._kalman.predict(dt)
        self._kalman.update(raw_x, raw_y)
        filtered_x, filtered_y = self._kalman.get_position()

        with self._lock:
            self._position = {
                "x": round(filtered_x, 3),
                "y": round(filtered_y, 3),
                "raw_x": round(raw_x, 3),
                "raw_y": round(raw_y, 3),
                "valid": True,
                "quality": "filtered",
                "anchors": len(valid_ranges),
                "ts": now
            }
            self._last_calc_time = now
            self._trajectory.append((filtered_x, filtered_y, now))

            # 更新到目标距离
            self._update_distance_to_target()

        # 发布坐标到MQTT
        self._publish_position()

    def _update_distance_to_target(self):
        """计算到目标病房的距离"""
        target = NEARLINK_ROOM_WAYPOINTS.get(self._target_room)
        if target and self._position.get("valid"):
            dx = self._position["x"] - target["x"]
            dy = self._position["y"] - target["y"]
            self._distance_to_target = math.sqrt(dx*dx + dy*dy)

    def _publish_position(self):
        """发布解算后的坐标到MQTT"""
        if self._mqtt_client and self._position.get("valid"):
            try:
                payload = {
                    "x": self._position["x"],
                    "y": self._position["y"],
                    "quality": self._position.get("quality", "unknown"),
                    "target_room": self._target_room,
                    "distance_to_target": round(self._distance_to_target, 2),
                    "ts": self._position["ts"]
                }
                self._mqtt_client.publish(
                    TOPIC_NL_POSITION,
                    json.dumps(payload)
                )
            except Exception:
                pass

    # ═══════════════════════════════════════════
    #  位置解算主循环
    # ═══════════════════════════════════════════

    def _positioning_loop(self):
        """后台定位解算循环"""
        interval = 1.0 / NL_POSITION_UPDATE_HZ
        print(f"[NearLink] Positioning loop started @ {NL_POSITION_UPDATE_HZ}Hz")

        while self._running:
            self._calculate_position()
            time.sleep(interval)

    # ═══════════════════════════════════════════
    #  公开接口
    # ═══════════════════════════════════════════

    def start(self):
        """启动NearLink定位系统"""
        if self._running:
            return

        self._connect_mqtt()
        self._running = True

        t = threading.Thread(target=self._positioning_loop, daemon=True,
                             name="NearLinkPositioning")
        t.start()
        print("[NearLink] ✅ Positioning system started")

    def stop(self):
        """停止定位系统"""
        self._running = False
        if self._mqtt_client:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
        print("[NearLink] Positioning system stopped")

    def get_position(self):
        """获取当前位置 (滤波后)"""
        with self._lock:
            return self._position.copy()

    def get_distance_to_target(self):
        """获取到目标病房的距离 (米)"""
        with self._lock:
            return self._distance_to_target

    def get_distance_to_room(self, room_id):
        """获取到指定病房的距离 (米)"""
        target = NEARLINK_ROOM_WAYPOINTS.get(str(room_id))
        if not target or not self._position.get("valid"):
            return float('inf')

        with self._lock:
            dx = self._position["x"] - target["x"]
            dy = self._position["y"] - target["y"]
            return math.sqrt(dx * dx + dy * dy)

    def set_target_room(self, room_id):
        """设置目标病房"""
        room_id = str(room_id)
        if room_id not in NEARLINK_ROOM_WAYPOINTS:
            print(f"[NearLink] ⚠️ Unknown room: {room_id}")
            return False
        with self._lock:
            self._target_room = room_id
            self._update_distance_to_target()
        print(f"[NearLink] Target room set to {room_id}")
        return True

    def check_arrived(self, room_id=None):
        """
        检查是否到达目标病房 (替代RFID的check_room)

        返回: True/False/None
          True  = 距离 < NL_ARRIVE_THRESHOLD (到达)
          False = 尚未到达
          None  = 定位数据无效
        """
        room = str(room_id) if room_id else self._target_room
        dist = self.get_distance_to_room(room)

        if dist == float('inf'):
            return None

        if dist < NL_ARRIVE_THRESHOLD:
            print(f"[NearLink] ✅ Arrived at room {room}! (distance={dist:.2f}m)")
            return True
        return False

    def should_slow_down(self, room_id=None):
        """检查是否应该减速 (接近目标)"""
        room = str(room_id) if room_id else self._target_room
        dist = self.get_distance_to_room(room)
        return dist < NL_SLOWDOWN_THRESHOLD

    def get_trajectory(self):
        """获取历史轨迹 (用于可视化)"""
        with self._lock:
            return list(self._trajectory)

    def get_ranging_status(self):
        """获取各锚点测距状态"""
        with self._lock:
            now = time.time()
            status = {}
            for aid, rdata in self._ranging_data.items():
                age = now - rdata.get("ts", 0)
                status[aid] = {
                    "distance": round(rdata["distance"], 2),
                    "rssi": rdata.get("rssi", 0),
                    "age_ms": round(age * 1000),
                    "online": age < 2.0
                }
            return status

    def get_status(self):
        """获取完整定位系统状态"""
        pos = self.get_position()
        return {
            "enabled": NEARLINK_ENABLED,
            "running": self._running,
            "position": pos,
            "target_room": self._target_room,
            "distance_to_target": round(self._distance_to_target, 2),
            "anchors": self.get_ranging_status(),
            "is_arrived": self.check_arrived(),
        }

    # ═══════════════════════════════════════════
    #  方案A接口预留: 纯坐标导航
    # ═══════════════════════════════════════════

    def get_heading_to_target(self, room_id=None):
        """
        [方案A预留] 计算到目标的航向角 (度, 北=0, 顺时针)
        用于未来纯坐标导航时的航向PID控制
        """
        room = str(room_id) if room_id else self._target_room
        target = NEARLINK_ROOM_WAYPOINTS.get(room)
        if not target or not self._position.get("valid"):
            return None

        with self._lock:
            dx = target["x"] - self._position["x"]
            dy = target["y"] - self._position["y"]

        angle_rad = math.atan2(dx, -dy)  # 走廊坐标系: X沿走廊, Y垂直
        angle_deg = math.degrees(angle_rad) % 360
        return round(angle_deg, 1)

    def plan_path_to_room(self, room_id):
        """
        [方案A预留] 路径规划 (当前返回直线路径)
        未来升级: A*/Dijkstra + 地图
        """
        room = str(room_id)
        target = NEARLINK_ROOM_WAYPOINTS.get(room)
        if not target or not self._position.get("valid"):
            return None

        with self._lock:
            start = (self._position["x"], self._position["y"])

        # 简单直线路径 (方案A完善时替换为A*规划)
        waypoints = [
            start,
            (target["x"], 0.0),      # 先走到目标X轴位置 (沿走廊)
            (target["x"], target["y"])  # 再转向病房
        ]

        return {
            "room": room,
            "waypoints": waypoints,
            "total_distance": self.get_distance_to_room(room),
            "algorithm": "linear"  # 未来: "a_star"
        }

    # ═══════════════════════════════════════════
    #  模拟数据注入 (开发/测试用)
    # ═══════════════════════════════════════════

    def inject_ranging(self, anchor_id, distance, rssi=-60):
        """
        手动注入测距数据 (用于无硬件时的开发调试)

        用法:
            pos = NearLinkPositioning()
            pos.start()
            pos.inject_ranging("anchor_01", 3.5)
            pos.inject_ranging("anchor_02", 4.2)
            pos.inject_ranging("anchor_03", 7.1)
        """
        with self._lock:
            self._ranging_data[anchor_id] = {
                "distance": float(distance),
                "rssi": rssi,
                "ts": time.time()
            }


# ═══════════════════════════════════════════
#  独立测试
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("═══ NearLink 定位系统测试 ═══\n")

    pos = NearLinkPositioning()

    # 模拟测距数据 (床在302门口附近)
    print("注入模拟测距数据...")
    pos.inject_ranging("anchor_01", 4.5)   # 距锚点1约4.5m
    pos.inject_ranging("anchor_02", 0.8)   # 距锚点2约0.8m (最近)
    pos.inject_ranging("anchor_03", 4.2)   # 距锚点3约4.2m

    pos._calculate_position()

    result = pos.get_position()
    print(f"\n📍 计算位置: x={result.get('x')}, y={result.get('y')}")
    print(f"   质量: {result.get('quality')}, 锚点数: {result.get('anchors')}")

    # 到达判定测试
    for room in ["301", "302", "303"]:
        dist = pos.get_distance_to_room(room)
        arrived = pos.check_arrived(room)
        heading = pos.get_heading_to_target(room)
        print(f"\n🏥 {room}号病房:")
        print(f"   距离: {dist:.2f}m")
        print(f"   到达: {'✅ YES' if arrived else '❌ NO'}")
        print(f"   航向: {heading}°")

    # 方案A预留: 路径规划
    print("\n─── 方案A预留: 路径规划测试 ───")
    path = pos.plan_path_to_room("303")
    if path:
        print(f"  目标: {path['room']}号")
        print(f"  路径: {path['waypoints']}")
        print(f"  总距离: {path['total_distance']:.2f}m")
        print(f"  算法: {path['algorithm']}")

    print("\n═══ 测试完成 ═══")
