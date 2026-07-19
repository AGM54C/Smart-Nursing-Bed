#!/usr/bin/env python3
"""
智能护理病床 - 时序预测模型 (受压风险预测)

创新点: 从"事后告警"升级为"事前预防"
  - 用时序模型预测未来30min的受压风险概率
  - 高召回优先策略 (阈值30%, 宁可多报不漏报)
  - 三级预警: info(30-50%) / warning(50-70%) / critical(>70%)
  - 轻量1D-CNN, 参数 < 10K, 推理 < 5ms (RPi4B)

输入: 过去1小时数据 (12个时间步, 每5min一帧)
  - Channel 0: 压力总值 (归一化)
  - Channel 1: 最大压力点值 (归一化)
  - Channel 2: 姿态持续时间 (分钟/120归一化)

输出: 未来30min受压风险概率 [0, 1]
"""

import os
import time
import numpy as np
from collections import deque

# ─── PyTorch ───
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("[Predictive] ⚠️ PyTorch not available, prediction disabled")


# ═══════════════════════════════════════════
#  1. 轻量1D-CNN模型
# ═══════════════════════════════════════════

if TORCH_AVAILABLE:
    class PressureRisk1DCNN(nn.Module):
        """
        受压风险预测 1D-CNN

        参数量约 8K, 推理 < 5ms on RPi4B
        输入: (batch, 3, 12) — 3通道 × 12时间步
        输出: (batch, 1) — 未来30min受压风险概率
        """
        def __init__(self, in_channels=3, seq_len=12):
            super().__init__()
            self.features = nn.Sequential(
                # Conv Block 1: (3, 12) → (16, 12)
                nn.Conv1d(in_channels, 16, kernel_size=3, padding=1),
                nn.BatchNorm1d(16),
                nn.ReLU(),
                # Conv Block 2: (16, 12) → (32, 6)
                nn.Conv1d(16, 32, kernel_size=3, padding=1),
                nn.BatchNorm1d(32),
                nn.ReLU(),
                nn.MaxPool1d(2),
                # Conv Block 3: (32, 6) → (32, 3)
                nn.Conv1d(32, 32, kernel_size=3, padding=1),
                nn.BatchNorm1d(32),
                nn.ReLU(),
                nn.MaxPool1d(2),
            )
            self.classifier = nn.Sequential(
                nn.Flatten(),           # 32 × 3 = 96
                nn.Linear(96, 32),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(32, 1),
                nn.Sigmoid()            # 输出概率 [0, 1]
            )

        def forward(self, x):
            x = self.features(x)
            x = self.classifier(x)
            return x


# ═══════════════════════════════════════════
#  2. 预测引擎 (对外接口)
# ═══════════════════════════════════════════

class PredictiveEngine:
    """
    时序预测引擎

    使用滑动窗口收集过去1小时数据, 用1D-CNN预测未来30min受压风险。
    高召回优先: 阈值30% (>30% 即预警)
    """

    # 预警阈值 (高召回策略)
    THRESHOLD_INFO = 0.30      # 30% → 轻度提示
    THRESHOLD_WARNING = 0.50   # 50% → 建议翻身
    THRESHOLD_CRITICAL = 0.70  # 70% → 紧急告警 + 气囊介入

    def __init__(self, model_path="predictive_risk.pth", window_size=12):
        """
        window_size: 滑动窗口大小 (12 × 5min = 1小时)
        """
        self.window_size = window_size
        self.model_path = model_path

        # 滑动窗口 (每帧3个特征)
        self._window = deque(maxlen=window_size)
        self._last_update = 0
        self._latest_risk = 0.0
        self._latest_level = "none"

        # 加载模型
        self.model = None
        if TORCH_AVAILABLE:
            self._load_model()

        print(f"[Predictive] Engine initialized (window={window_size}, "
              f"model={'loaded' if self.model else 'unavailable'})")

    def _load_model(self):
        """加载训练好的模型"""
        if not TORCH_AVAILABLE:
            return
        if os.path.exists(self.model_path):
            try:
                self.model = PressureRisk1DCNN()
                self.model.load_state_dict(torch.load(self.model_path, map_location="cpu"))
                self.model.eval()
                params = sum(p.numel() for p in self.model.parameters())
                print(f"[Predictive] ✅ Model loaded ({params} params)")
            except Exception as e:
                print(f"[Predictive] Model load failed: {e}")
                self.model = None
        else:
            print(f"[Predictive] No model at {self.model_path}, run: python3 predictive_model.py train")

    def update(self, pressure_total, max_pressure, posture_duration_min):
        """
        更新滑动窗口 (每次压力分析后调用)

        pressure_total: 压力矩阵总值 (0-262140 for 8×8×4095)
        max_pressure: 最大压力点值 (0-4095)
        posture_duration_min: 当前姿态持续时间 (分钟)
        """
        # 归一化
        feat = [
            min(pressure_total / 262140.0, 1.0),    # 总压力
            min(max_pressure / 4095.0, 1.0),         # 最大压力
            min(posture_duration_min / 120.0, 1.0),  # 姿态持续 (120min封顶)
        ]
        self._window.append(feat)
        self._last_update = time.time()

    def predict(self):
        """
        执行预测 (窗口满时)

        返回: {
            "risk": 0.0-1.0,
            "level": "none" | "info" | "warning" | "critical",
            "window_filled": True/False,
            "method": "cnn" | "heuristic"
        }
        """
        # 窗口未满 → 基于启发式规则做粗略预估
        if len(self._window) < self.window_size:
            risk = self._heuristic_predict()
            level = self._risk_to_level(risk)
            self._latest_risk = risk
            self._latest_level = level
            return {
                "risk": round(risk, 3),
                "level": level,
                "window_filled": False,
                "window_progress": f"{len(self._window)}/{self.window_size}",
                "method": "heuristic"
            }

        # CNN 推理
        if self.model and TORCH_AVAILABLE:
            risk = self._cnn_predict()
            method = "cnn"
        else:
            risk = self._heuristic_predict()
            method = "heuristic"

        level = self._risk_to_level(risk)
        self._latest_risk = risk
        self._latest_level = level

        return {
            "risk": round(risk, 3),
            "level": level,
            "window_filled": True,
            "method": method
        }

    def _cnn_predict(self):
        """1D-CNN推理"""
        data = np.array(list(self._window), dtype=np.float32)  # (12, 3)
        x = torch.FloatTensor(data.T).unsqueeze(0)  # (1, 3, 12)

        with torch.no_grad():
            output = self.model(x)
            risk = float(output.item())

        return risk

    def _heuristic_predict(self):
        """
        启发式预测 (模型不可用时的回退方案)

        逻辑: 如果最近几帧的最大压力持续偏高 + 姿态不变, 则风险上升
        """
        if len(self._window) == 0:
            return 0.0

        recent = list(self._window)
        n = len(recent)

        # 平均最大压力 (channel 1)
        avg_max_pressure = sum(f[1] for f in recent) / n
        # 最新姿态持续时间 (channel 2)
        latest_duration = recent[-1][2]
        # 压力趋势 (最后3帧 vs 前3帧)
        if n >= 6:
            early_avg = sum(f[0] for f in recent[:3]) / 3
            late_avg = sum(f[0] for f in recent[-3:]) / 3
            trend = max(0, (late_avg - early_avg) / (early_avg + 1e-6))
        else:
            trend = 0

        # 风险 = 加权组合
        risk = (
            avg_max_pressure * 0.4 +     # 持续高压
            latest_duration * 0.4 +       # 长时间不动
            min(trend, 0.5) * 0.2         # 压力上升趋势
        )

        return min(max(risk, 0.0), 1.0)

    def _risk_to_level(self, risk):
        """风险值 → 预警等级"""
        if risk >= self.THRESHOLD_CRITICAL:
            return "critical"
        elif risk >= self.THRESHOLD_WARNING:
            return "warning"
        elif risk >= self.THRESHOLD_INFO:
            return "info"
        return "none"

    def get_latest(self):
        return {"risk": self._latest_risk, "level": self._latest_level}


# ═══════════════════════════════════════════
#  3. 训练 (合成数据)
# ═══════════════════════════════════════════

def generate_training_data(n_samples=3000):
    """
    生成合成训练数据

    正样本 (有受压风险): 压力持续高 + 姿态不变 → label=1
    负样本 (无风险): 压力变化/低 + 姿态变化 → label=0
    """
    X, y = [], []

    for _ in range(n_samples):
        label = np.random.randint(0, 2)
        seq = np.zeros((12, 3), dtype=np.float32)

        if label == 1:  # 高风险: 持续高压 + 不翻身
            base_pressure = np.random.uniform(0.4, 0.8)
            base_max = np.random.uniform(0.5, 0.9)

            for t in range(12):
                # 压力缓慢上升
                seq[t, 0] = base_pressure + t * np.random.uniform(0.01, 0.03)
                seq[t, 1] = base_max + t * np.random.uniform(0.005, 0.02)
                # 姿态持续时间递增
                seq[t, 2] = min((t + 1) * 5 / 120.0 + np.random.uniform(0, 0.1), 1.0)

            # 添加噪声
            seq += np.random.normal(0, 0.03, seq.shape)

        else:  # 低风险: 压力变化 / 翻身
            for t in range(12):
                seq[t, 0] = np.random.uniform(0.05, 0.4)
                seq[t, 1] = np.random.uniform(0.05, 0.4)
                # 姿态会重置 (翻身)
                if t > 0 and np.random.random() > 0.7:
                    seq[t, 2] = np.random.uniform(0, 0.1)  # 刚翻身
                else:
                    seq[t, 2] = min(seq[t-1, 2] + 5/120.0 if t > 0 else 0.05, 0.5)

            seq += np.random.normal(0, 0.02, seq.shape)

        seq = np.clip(seq, 0, 1)
        X.append(seq)
        y.append(float(label))

    return np.array(X), np.array(y)


def train_model(save_path="predictive_risk.pth", epochs=30):
    """训练受压风险预测模型"""
    if not TORCH_AVAILABLE:
        print("[Predictive] Cannot train without PyTorch")
        return None

    print("[Predictive] Generating training data...")
    X, y = generate_training_data(5000)

    # (N, 12, 3) → (N, 3, 12) for Conv1d
    X = X.transpose(0, 2, 1)

    split = int(len(X) * 0.8)
    X_train = torch.FloatTensor(X[:split])
    y_train = torch.FloatTensor(y[:split]).unsqueeze(1)
    X_val = torch.FloatTensor(X[split:])
    y_val = torch.FloatTensor(y[split:]).unsqueeze(1)

    model = PressureRisk1DCNN()
    params = sum(p.numel() for p in model.parameters())
    print(f"[Predictive] Model: PressureRisk1DCNN ({params} params)")

    optimizer = torch.optim.AdamW(model.parameters(), lr=0.003, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.BCELoss()

    best_acc = 0
    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(len(X_train))
        total_loss = 0

        for i in range(0, len(X_train), 64):
            idx = perm[i:i+64]
            out = model(X_train[idx])
            loss = criterion(out, y_train[idx])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        scheduler.step()

        # Validation
        model.eval()
        with torch.no_grad():
            val_out = model(X_val)
            val_pred = (val_out > 0.5).float()
            val_acc = (val_pred == y_val).float().mean().item()

            # 计算召回率 (最重要的指标)
            tp = ((val_pred == 1) & (y_val == 1)).sum().item()
            fn = ((val_pred == 0) & (y_val == 1)).sum().item()
            recall = tp / (tp + fn + 1e-6)

        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(model.state_dict(), save_path)

        if (epoch + 1) % 10 == 0:
            print(f"  Epoch {epoch+1}/{epochs} | Loss: {total_loss:.3f} | "
                  f"Acc: {val_acc:.1%} | Recall: {recall:.1%}")

    print(f"[Predictive] Training complete! Best accuracy: {best_acc:.1%}")
    print(f"[Predictive] Model saved to {save_path} ({params} params)")
    return model


# ═══════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "train":
        model = train_model()
        if model:
            # 测试推理
            engine = PredictiveEngine()
            # 模拟高风险序列
            for i in range(12):
                engine.update(
                    pressure_total=150000 + i * 5000,
                    max_pressure=3000 + i * 50,
                    posture_duration_min=i * 5
                )
            result = engine.predict()
            print(f"\nHigh-risk test: {result}")

            # 模拟低风险序列
            engine2 = PredictiveEngine()
            for i in range(12):
                engine2.update(
                    pressure_total=50000 + np.random.randint(-10000, 10000),
                    max_pressure=1000 + np.random.randint(-200, 200),
                    posture_duration_min=max(0, (i % 4) * 5)  # 频繁翻身
                )
            result2 = engine2.predict()
            print(f"Low-risk test:  {result2}")

    elif len(sys.argv) > 1 and sys.argv[1] == "benchmark":
        if TORCH_AVAILABLE:
            model = PressureRisk1DCNN()
            params = sum(p.numel() for p in model.parameters())
            x = torch.randn(1, 3, 12)
            import timeit
            t = timeit.timeit(lambda: model(x), number=1000) / 1000 * 1000
            print(f"PressureRisk1DCNN: {params:,} params, {t:.2f}ms/inference")
    else:
        print("用法:")
        print("  python3 predictive_model.py train       # 训练模型")
        print("  python3 predictive_model.py benchmark   # 推理性能测试")
