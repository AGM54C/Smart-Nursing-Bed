#!/usr/bin/env python3
"""
智能护理病床 - 非接触呼吸率监测 (边缘频域提取)

原理:
  呼吸引起胸腹起伏 → 床垫压力矩阵总压出现 0.15~0.6Hz 周期性微小波动。
  ESP32 以 4Hz 发布压力总和 (bed/breath: {"t":ms,"v":total}),
  本模块维护 60 秒滑动窗口: 去趋势 → Hamming加窗 → FFT → 呼吸频带找谱峰:
      呼吸率(bpm) = f_peak × 60
  谱峰显著性(峰值功率/频带总功率)作为质量指标, 过低(体动干扰/空床)不输出。

零额外硬件: 复用 Velostat 压力矩阵。
"""

import os
import time
import random
import threading

try:
    import numpy as np
except ImportError:
    np = None
    print("[Breath] ⚠️ numpy不可用, 呼吸率监测停用")

FS = 4.0                    # ESP32采样率 Hz (BREATH_INTERVAL=250ms)
WINDOW_SEC = 60             # 分析窗口
MIN_SEC = 30                # 最少数据量才开始估计
BAND = (0.15, 0.6)          # 呼吸频带 Hz (9~36 次/分)
OCCUPIED_MIN_TOTAL = 1500   # 平均总压低于此视为空床
QUALITY_MIN = 0.25          # 谱峰显著性下限
CACHE_SEC = 5               # 计算结果缓存, 避免每条vitals都做FFT
SIM_STALE_SEC = 15          # 超过此秒数无真实样本 → 硬件故障, 进入仿真兜底
SIM_ENABLED = os.environ.get('BREATH_SIM', '1') != '0'   # BREATH_SIM=0 关闭仿真


class BreathMonitor:
    def __init__(self):
        self._buf = []              # [(wall_time, total)]
        self._lock = threading.Lock()
        self._cache = ({}, 0.0)     # (result, computed_at)
        self._last_ingest = 0.0     # 最后一次真实样本时间
        self._sim_rr = 16.0         # 仿真呼吸率随机游走状态

    def ingest(self, t_ms, value):
        """喂入一个压力总和样本 (bed/breath 4Hz)"""
        if np is None or value is None:
            return
        now = time.time()
        self._last_ingest = now
        with self._lock:
            self._buf.append((now, float(value)))
            cutoff = now - WINDOW_SEC - 5
            while self._buf and self._buf[0][0] < cutoff:
                self._buf.pop(0)

    def get_rate(self):
        """
        返回 {'respiration_rate': bpm, 'breath_quality': q, 'breath_source': 'fft'|'sim'}
        - 有真实数据且谱峰可信 → FFT结果
        - 有真实数据但空床/质量差 → {} (诚实静默, 不是硬件故障)
        - 完全收不到样本(ESP32离线/矩阵故障) → 仿真兜底 (BREATH_SIM=0可关)
        """
        result, ts = self._cache
        if time.time() - ts < CACHE_SEC:
            return result
        real = self._compute() if np is not None else None
        if real:
            real['breath_source'] = 'fft'
            result = real
        elif SIM_ENABLED and (time.time() - self._last_ingest) > SIM_STALE_SEC:
            result = self._simulate()          # 硬件断供 → 演示兜底
        else:
            result = {}
        self._cache = (result, time.time())
        return result

    def _simulate(self):
        """仿真呼吸率: 12~20bpm 缓慢随机游走, 明确标记 sim"""
        self._sim_rr = max(12.0, min(20.0, self._sim_rr + random.gauss(0, 0.3)))
        return {'respiration_rate': round(self._sim_rr, 1),
                'breath_quality': 0.0,
                'breath_source': 'sim'}

    def _compute(self):
        with self._lock:
            buf = list(self._buf)
        if len(buf) < MIN_SEC * FS:
            return None
        vals = np.array([v for _, v in buf[-int(WINDOW_SEC * FS):]], dtype=float)

        if vals.mean() < OCCUPIED_MIN_TOTAL:      # 空床/矩阵未接
            return None

        # 去趋势: 减8秒滑动均值, 消除体位缓慢变化的低频成分
        k = int(8 * FS)
        kernel = np.ones(k) / k
        trend = np.convolve(vals, kernel, mode='same')
        x = (vals - trend) * np.hamming(len(vals))

        spec = np.abs(np.fft.rfft(x)) ** 2
        freqs = np.fft.rfftfreq(len(x), d=1.0 / FS)
        band = (freqs >= BAND[0]) & (freqs <= BAND[1])
        if not band.any() or spec[band].sum() <= 0:
            return None

        i_peak = int(np.argmax(spec * band))      # 频带内谱峰
        quality = float(spec[i_peak] / spec[band].sum())
        if quality < QUALITY_MIN:                 # 体动干扰/信号太弱
            return None

        bpm = round(float(freqs[i_peak]) * 60, 1)
        return {'respiration_rate': bpm, 'breath_quality': round(quality, 2)}


if __name__ == '__main__':
    # 自测: 合成 18bpm 呼吸信号 + 高斯噪声
    bm = BreathMonitor()
    if np is not None:
        f_breath = 18 / 60
        now = time.time()
        for i in range(240):
            v = 20000 + 300 * np.sin(2 * np.pi * f_breath * i / FS) \
                + float(np.random.randn()) * 50
            bm._buf.append((now - (240 - i) / FS, float(v)))
        print("自测:", bm._compute(), "(期望 respiration_rate≈18)")
