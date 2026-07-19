#!/usr/bin/env python3
"""
智能护理病床 - 多模态融合告警模块

融合多种传感器信号进行联合判断:
  - 视觉 (摄像头): MediaPipe Pose 跌倒检测
  - 压力矩阵: 离床/体位检测
  - 体征数据: 异常波动关联
  
融合策略:
  - Dempster-Shafer证据理论简化版
  - 多源一致 → 高置信告警
  - 单源异常 → 待确认告警
"""

import time
import threading
import logging
import numpy as np

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[MultiModal] %(message)s')

# ─── 视觉跌倒检测 (MediaPipe Pose) ───
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import mediapipe as mp
    MP_AVAILABLE = True
except ImportError:
    MP_AVAILABLE = False


class VisionFallDetector:
    """
    基于 MediaPipe Pose 的跌倒/离床检测
    通过关键点位置变化+身体倾角判断跌倒
    """

    def __init__(self):
        self.pose = None
        if MP_AVAILABLE:
            self.pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=0,  # 轻量模式
                min_detection_confidence=0.5,
                min_tracking_confidence=0.3
            )
        self.prev_hip_y = None
        self.fall_detected = False
        self.person_present = False
        self.last_detection_time = 0
        self.confidence = 0.0

        # 跌倒判断参数
        self.FALL_Y_THRESHOLD = 0.4    # 臀部Y坐标突变阈值
        self.ANGLE_THRESHOLD = 60      # 身体倾斜角度阈值(度)
        self.ABSENCE_FRAMES = 10       # 连续N帧无人 → 判定离床
        self._no_person_count = 0

        log.info("VisionFallDetector initialized (MediaPipe: %s, OpenCV: %s)",
                 MP_AVAILABLE, CV2_AVAILABLE)

    def analyze_frame(self, frame):
        """
        分析单帧图像
        frame: BGR numpy array (来自摄像头)
        返回: { 'person_present': bool, 'fall_detected': bool, 'confidence': float, 'body_angle': float }
        """
        if not self.pose or frame is None:
            return self._default_result()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb)

        if not results.pose_landmarks:
            self._no_person_count += 1
            if self._no_person_count > self.ABSENCE_FRAMES:
                self.person_present = False
            return {
                'person_present': self.person_present,
                'fall_detected': False,
                'confidence': 0.3,
                'body_angle': 0,
                'absence_frames': self._no_person_count
            }

        self._no_person_count = 0
        self.person_present = True
        landmarks = results.pose_landmarks.landmark

        # 关键点
        left_hip = landmarks[mp.solutions.pose.PoseLandmark.LEFT_HIP]
        right_hip = landmarks[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
        left_shoulder = landmarks[mp.solutions.pose.PoseLandmark.LEFT_SHOULDER]
        right_shoulder = landmarks[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]
        nose = landmarks[mp.solutions.pose.PoseLandmark.NOSE]

        # 臀部中心Y坐标
        hip_y = (left_hip.y + right_hip.y) / 2
        shoulder_y = (left_shoulder.y + right_shoulder.y) / 2

        # 身体倾斜角: 肩-臀连线与垂直方向的夹角
        dx = (left_shoulder.x + right_shoulder.x) / 2 - (left_hip.x + right_hip.x) / 2
        dy = shoulder_y - hip_y
        body_angle = abs(np.degrees(np.arctan2(abs(dx), abs(dy))))

        # 跌倒判断
        fall = False
        confidence = 0.0

        # 判据1: 臀部Y坐标突然下降(在画面中Y轴向下为正)
        if self.prev_hip_y is not None:
            y_change = hip_y - self.prev_hip_y
            if y_change > self.FALL_Y_THRESHOLD:
                fall = True
                confidence += 0.4

        # 判据2: 身体倾斜角过大
        if body_angle > self.ANGLE_THRESHOLD:
            fall = True
            confidence += 0.3

        # 判据3: 头部低于臀部(正常躺床上不会出现)
        if nose.y > hip_y + 0.1:
            confidence += 0.2

        # 判据4: 臀部接近画面底部(掉落)
        if hip_y > 0.85:
            confidence += 0.1

        self.prev_hip_y = hip_y
        self.fall_detected = fall
        self.confidence = min(confidence, 1.0)
        self.last_detection_time = time.time()

        return {
            'person_present': True,
            'fall_detected': fall,
            'confidence': self.confidence,
            'body_angle': round(body_angle, 1),
            'hip_y': round(hip_y, 3)
        }

    def _default_result(self):
        return {'person_present': False, 'fall_detected': False, 'confidence': 0, 'body_angle': 0}

    def cleanup(self):
        if self.pose:
            self.pose.close()


class MultiModalFusion:
    """
    多模态融合引擎

    基于标准Dempster-Shafer证据组合规则的多源融合:
      - 辨识框架 Θ = {danger(危险), safe(安全)}
      - 每个证据源输出质量函数 m(danger)/m(safe)/m(Θ不确定)
      - Dempster组合规则计算联合信度, 冲突系数K量化源间矛盾
      - 视觉证据 (摄像头) / 压力证据 (压力矩阵) / 体征证据 (传感器)
    """

    def __init__(self):
        self.vision_detector = VisionFallDetector()
        self._evidence = {
            'vision': {'fall': 0, 'present': True, 'time': 0},
            'pressure': {'empty': False, 'posture': 'unknown', 'risk': 'none', 'time': 0},
            'vitals': {'anomaly': False, 'details': {}, 'time': 0}
        }
        self._fusion_result = {}
        self._lock = threading.Lock()
        self._alert_history = []

        log.info("✅ MultiModalFusion engine initialized")

    def update_vision(self, frame):
        """更新视觉证据 (传入摄像头帧)"""
        result = self.vision_detector.analyze_frame(frame)
        with self._lock:
            self._evidence['vision'] = {
                'fall': result['confidence'] if result['fall_detected'] else 0,
                'present': result['person_present'],
                'angle': result.get('body_angle', 0),
                'time': time.time()
            }
        return result

    def update_pressure(self, analysis_result):
        """更新压力证据 (传入PressureAnalyzer的结果)"""
        if not analysis_result:
            return
        with self._lock:
            posture = analysis_result.get('posture', {})
            self._evidence['pressure'] = {
                'empty': not analysis_result.get('occupied', True),
                'posture': posture.get('posture', 'unknown'),
                'posture_confidence': posture.get('confidence', 0),
                'risk': (analysis_result.get('ulcer_risk') or {}).get('level', 'none'),
                'time': time.time()
            }

    def update_vitals(self, vitals_data):
        """更新体征证据"""
        if not vitals_data:
            return
        anomalies = []
        hr = vitals_data.get('heart_rate')
        spo2 = vitals_data.get('blood_oxygen')
        temp = vitals_data.get('temperature')
        bp = vitals_data.get('blood_pressure_sys')

        if hr and (hr > 130 or hr < 40): anomalies.append(f'HR={hr}')
        if spo2 and spo2 < 88: anomalies.append(f'SpO2={spo2}')
        if temp and temp > 39: anomalies.append(f'T={temp}')
        if bp and (bp > 170 or bp < 70): anomalies.append(f'BP={bp}')

        with self._lock:
            self._evidence['vitals'] = {
                'anomaly': len(anomalies) > 0,
                'anomaly_count': len(anomalies),
                'details': anomalies,
                'time': time.time()
            }

    # ─── Dempster-Shafer 证据组合 ───

    @staticmethod
    def _ds_combine(m1, m2):
        """
        标准Dempster组合规则 (辨识框架 Θ={danger, safe})
        m = (m_danger, m_safe, m_theta)
        K = Σ m1(A)·m2(B), A∩B=∅  (冲突质量)
        m12(C) = Σ_{A∩B=C} m1(A)·m2(B) / (1-K)
        返回: (组合质量函数, 冲突系数K)
        """
        d1, s1, t1 = m1
        d2, s2, t2 = m2
        K = d1 * s2 + s1 * d2               # danger∩safe = ∅
        if K >= 0.999:                       # 完全冲突 → 退化为完全不确定
            return (0.0, 0.0, 1.0), K
        norm = 1.0 - K
        d = (d1 * d2 + d1 * t2 + t1 * d2) / norm
        s = (s1 * s2 + s1 * t2 + t1 * s2) / norm
        t = (t1 * t2) / norm
        return (d, s, t), K

    def fuse(self):
        """
        执行多模态融合, 生成综合判断

        流程:
          1. 三个证据源各自构造质量函数 (失效证据 → 全部质量归入Θ)
          2. Dempster规则两两组合: (视觉 ⊕ 压力) ⊕ 体征
          3. Belief(danger)=m(d), Plausibility(danger)=m(d)+m(Θ)
          4. 依据Bel/Pl与源一致数映射四级告警

        返回: {
            'alert_level': 'none'|'info'|'warning'|'critical',
            'confidence': float,        # Belief(danger)
            'belief': float, 'plausibility': float, 'conflict_k': float,
            'events': [...],
            'source_agreement': int
        }
        """
        with self._lock:
            v = self._evidence['vision'].copy()
            p = self._evidence['pressure'].copy()
            vit = self._evidence['vitals'].copy()

        now = time.time()
        events = []
        source_count = 0  # 多少个源检测到异常 (兼容旧接口)

        # 时效性检查 (超过30秒的证据 → 质量全部归入不确定Θ)
        v_fresh = (now - v['time']) < 30
        p_fresh = (now - p['time']) < 30
        vit_fresh = (now - vit['time']) < 30

        # ── 1. 视觉质量函数 ──
        if v_fresh:
            c = min(max(v.get('fall', 0), 0.0), 1.0)
            m_vision = (0.85 * c, 0.85 * (1 - c), 0.15)
            if c > 0.3:
                source_count += 1
                events.append('vision_fall')
        else:
            m_vision = (0.0, 0.0, 1.0)

        # ── 2. 压力质量函数 ──
        ulcer_risk = p.get('risk', 'none') if p_fresh else 'none'
        if p_fresh:
            md = 0.0
            if p.get('empty'):
                md = max(md, 0.60)           # 应卧床却空床 → 离床/跌落嫌疑
                source_count += 1
                events.append('pressure_empty')
            md = max(md, {'high': 0.50, 'medium': 0.30}.get(ulcer_risk, 0.0))
            if ulcer_risk in ('medium', 'high'):
                events.append(f'ulcer_{ulcer_risk}')
            ms = 0.2 if p.get('empty') else 0.7 * (1 - md)
            m_pressure = (md, ms, max(0.0, 1 - md - ms))
        else:
            m_pressure = (0.0, 0.0, 1.0)

        # ── 3. 体征质量函数 ──
        if vit_fresh:
            n = vit.get('anomaly_count', 0)
            md = min(0.25 * n, 0.75)
            ms = 0.7 if n == 0 else max(0.05, 0.4 - 0.15 * n)
            m_vitals = (md, ms, max(0.0, 1 - md - ms))
            if vit.get('anomaly'):
                source_count += 1
                events.append('vitals_anomaly')
        else:
            m_vitals = (0.0, 0.0, 1.0)

        # ── Dempster 组合: (视觉 ⊕ 压力) ⊕ 体征 ──
        m_vp, k1 = self._ds_combine(m_vision, m_pressure)
        m_all, k2 = self._ds_combine(m_vp, m_vitals)
        conflict_k = round(1 - (1 - k1) * (1 - k2), 3)   # 累积冲突

        belief = m_all[0]                     # Bel(danger)
        plausibility = m_all[0] + m_all[2]    # Pl(danger) = Bel + 不确定

        # ── 告警级别映射 ──
        if belief > 0.55 and source_count >= 2:
            alert_level = 'critical'
        elif belief > 0.30 or ulcer_risk in ('medium', 'high') or (vit_fresh and vit.get('anomaly')):
            alert_level = 'warning'
        elif belief > 0.15 or plausibility > 0.6:
            alert_level = 'info'
        else:
            alert_level = 'none'

        result = {
            'alert_level': alert_level,
            'confidence': round(belief, 2),
            'belief': round(belief, 3),
            'plausibility': round(plausibility, 3),
            'conflict_k': conflict_k,
            'events': events,
            'source_agreement': source_count,
            'fall_detected': belief > 0.3 and ('vision_fall' in events or 'pressure_empty' in events),
            'person_present': v.get('present', True) if v_fresh else p.get('posture') != 'empty',
            'ulcer_risk': ulcer_risk,
            'vitals_anomaly': vit.get('details', []),
            'timestamp': now
        }

        with self._lock:
            self._fusion_result = result

        if alert_level != 'none':
            self._alert_history.append({
                'time': time.strftime('%H:%M:%S'),
                'level': alert_level,
                'events': events,
                'confidence': result['confidence']
            })
            self._alert_history = self._alert_history[-50:]

        return result

    def inject_demo(self, event='fall'):
        """
        演示注入 (bed/demo/fusion): 无摄像头/压力矩阵硬件时模拟证据源,
        驱动真实的D-S组合与告警链路 — 算法真实, 仅证据来源为模拟。
          event: 'fall'(跌倒) | 'ulcer'(高受压) | 'vitals'(体征异常) | 'clear'(复位)
        """
        now = time.time()
        with self._lock:
            if event == 'fall':
                self._evidence['vision'] = {'fall': 0.92, 'present': False,
                                            'angle': 78, 'time': now}
                self._evidence['pressure'] = {'empty': True, 'posture': 'empty',
                                              'risk': 'none', 'time': now}
            elif event == 'ulcer':
                self._evidence['pressure'] = {'empty': False, 'posture': 'supine',
                                              'risk': 'high', 'time': now}
            elif event == 'vitals':
                self._evidence['vitals'] = {'anomaly': True, 'anomaly_count': 2,
                                            'details': ['HR=132', 'SpO2=87'], 'time': now}
            else:  # clear
                self._evidence['vision'] = {'fall': 0, 'present': True, 'time': now}
                self._evidence['pressure'] = {'empty': False, 'posture': 'supine',
                                              'risk': 'none', 'time': now}
                self._evidence['vitals'] = {'anomaly': False, 'anomaly_count': 0,
                                            'details': [], 'time': now}
        return self.fuse()

    def get_latest_fusion(self):
        with self._lock:
            return self._fusion_result.copy()

    def get_evidence(self):
        with self._lock:
            return {k: v.copy() for k, v in self._evidence.items()}

    def get_alert_history(self):
        return list(self._alert_history)
