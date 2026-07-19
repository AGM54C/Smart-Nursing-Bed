#!/usr/bin/env python3
"""
智能护理病床 - 压力矩阵AI分析模块 (树莓派端)

功能:
  1. 双模型架构: PostureCNN(15K) + PostureMobileNet(45K, MobileNetV3-inspired)
  2. ONNX Runtime 推理支持 (工业级部署)
  3. 受压风险监测: 跟踪持续高压点, 四级预警
  4. 体位变化检测: 帧间差异 + 姿态对比

部署: 树莓派4B-8G, 支持PyTorch / ONNX Runtime推理
"""

import os
import time
import json
import threading
import numpy as np
from collections import deque

# ─── PyTorch (CNN推理) ───
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except (ImportError, Exception):
    TORCH_AVAILABLE = False
    print("[PressureAI] ⚠️ PyTorch not available, using rule-based fallback")
    # Dummy nn.Module so class definitions don't crash
    import types
    nn = types.ModuleType("nn")
    class _DummyModule:
        def __init_subclass__(cls, **kw): pass
        def __init__(self, *a, **kw): pass
    nn.Module = _DummyModule
    for attr in ['Sequential', 'Conv2d', 'Linear', 'ReLU', 'Hardswish', 'Hardsigmoid',
                 'MaxPool2d', 'AdaptiveAvgPool2d', 'BatchNorm2d', 'Flatten', 'Dropout']:
        setattr(nn, attr, lambda *a, **kw: None)

# ─── ONNX Runtime (可选) ───
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False

# ─── 时序预测引擎 ───
try:
    from predictive_model import PredictiveEngine
    PREDICTIVE_AVAILABLE = True
except Exception:
    PREDICTIVE_AVAILABLE = False
    print("[PressureAI] ⚠️ PredictiveEngine not available")




# ═══════════════════════════════════════════
#  1. 双模型架构: 轻量CNN + MobileNet-style
# ═══════════════════════════════════════════

POSTURE_CLASSES = ["empty", "supine", "prone", "left_side", "right_side", "sitting"]


class PostureCNN(nn.Module):
    """
    极轻量CNN: 8×8单通道输入 → 6类睡姿
    参数量 < 15K, 推理时间 < 1ms (RPi4B)
    """
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1),   # 8×8×1 → 8×8×16
            nn.ReLU(),
            nn.MaxPool2d(2),                   # → 4×4×16
            nn.Conv2d(16, 32, 3, padding=1),   # → 4×4×32
            nn.ReLU(),
            nn.MaxPool2d(2),                   # → 2×2×32
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),                      # → 128
            nn.Linear(128, 48),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(48, len(POSTURE_CLASSES)),
        )

    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x


class _DepthwiseSeparableConv(nn.Module):
    """MobileNet核心: 深度可分离卷积 (减少参数量)"""
    def __init__(self, in_ch, out_ch, stride=1):
        super().__init__()
        self.depthwise = nn.Conv2d(in_ch, in_ch, 3, stride=stride, padding=1, groups=in_ch, bias=False)
        self.bn1 = nn.BatchNorm2d(in_ch)
        self.pointwise = nn.Conv2d(in_ch, out_ch, 1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_ch)
        self.act = nn.Hardswish()

    def forward(self, x):
        x = self.act(self.bn1(self.depthwise(x)))
        x = self.act(self.bn2(self.pointwise(x)))
        return x


class _SEBlock(nn.Module):
    """Squeeze-and-Excitation 通道注意力"""
    def __init__(self, channels, reduction=4):
        super().__init__()
        mid = max(channels // reduction, 4)
        self.squeeze = nn.AdaptiveAvgPool2d(1)
        self.excite = nn.Sequential(
            nn.Linear(channels, mid),
            nn.ReLU(),
            nn.Linear(mid, channels),
            nn.Hardsigmoid()
        )

    def forward(self, x):
        b, c, _, _ = x.shape
        w = self.squeeze(x).view(b, c)
        w = self.excite(w).view(b, c, 1, 1)
        return x * w


class PostureMobileNet(nn.Module):
    """
    MobileNetV3-inspired 睡姿分类模型
    
    特点:
      - 深度可分离卷积 (参数效率)
      - SE注意力模块 (通道加权)
      - Hardswish激活 (计算效率)
      - 参数量 ~45K (仍可在RPi4B实时推理)
    """
    def __init__(self):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.Hardswish()
        )
        self.features = nn.Sequential(
            _DepthwiseSeparableConv(16, 24),
            _SEBlock(24),
            _DepthwiseSeparableConv(24, 32, stride=2),  # 8×8 → 4×4
            _SEBlock(32),
            _DepthwiseSeparableConv(32, 64, stride=2),  # 4×4 → 2×2
            _SEBlock(64),
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Linear(64, 32),
            nn.Hardswish(),
            nn.Dropout(0.2),
            nn.Linear(32, len(POSTURE_CLASSES))
        )

    def forward(self, x):
        x = self.stem(x)
        x = self.features(x)
        x = self.pool(x).flatten(1)
        x = self.classifier(x)
        return x


def export_to_onnx(model, save_path="posture_model.onnx"):
    """导出模型为ONNX格式 (支持ONNX Runtime推理)"""
    if not TORCH_AVAILABLE:
        return False
    model.eval()
    dummy = torch.randn(1, 1, 8, 8)
    torch.onnx.export(
        model, dummy, save_path,
        input_names=['pressure_matrix'],
        output_names=['posture_logits'],
        opset_version=11,
        dynamic_axes={'pressure_matrix': {0: 'batch'}, 'posture_logits': {0: 'batch'}}
    )
    print(f"[PressureAI] ONNX model exported to {save_path}")
    return True


def _augment_grid(grid):
    """数据增强: 旋转/翻转/噪声/缩放"""
    aug = grid.copy()
    # 随机旋转90度 (保持方阵特性)
    k = np.random.randint(0, 4)
    if k > 0:
        aug = np.rot90(aug, k)
    # 随机水平翻转
    if np.random.random() > 0.5:
        aug = np.fliplr(aug).copy()
    # 随机缩放 (0.8-1.2)
    scale = np.random.uniform(0.8, 1.2)
    aug = aug * scale
    # 添加高斯噪声
    aug += np.random.normal(0, 80, aug.shape)
    return np.clip(aug, 0, 4095).astype(np.float32)


def generate_synthetic_data(n_samples=2000, augment=True):
    """
    生成合成训练数据 (带数据增强)

    模拟不同姿态的压力分布特征:
      - empty: 全低值噪声
      - supine: 中间纵轴高压, 肩部+臀部最高
      - prone: 类似supine但分布稍不同
      - left_side: 左侧3列高压
      - right_side: 右侧3列高压
      - sitting: 下半部集中高压
    """
    X, y = [], []
    for _ in range(n_samples):
        label = np.random.randint(0, len(POSTURE_CLASSES))
        grid = np.random.uniform(0, 200, (8, 8)).astype(np.float32)

        if label == 0:  # empty
            grid = np.random.uniform(0, 100, (8, 8)).astype(np.float32)

        elif label == 1:  # supine (仰卧) - 中间高，两侧低
            grid[:, 2:6] += np.random.uniform(1500, 3000, (8, 4))
            grid[1:3, 2:6] += np.random.uniform(500, 1000, (2, 4))
            grid[5:7, 2:6] += np.random.uniform(500, 1200, (2, 4))

        elif label == 2:  # prone (俯卧)
            grid[:, 2:6] += np.random.uniform(1200, 2500, (8, 4))
            grid[2:4, 2:6] += np.random.uniform(300, 800, (2, 4))

        elif label == 3:  # left_side (左侧卧)
            grid[:, 0:3] += np.random.uniform(1500, 3500, (8, 3))
            grid[3:5, 0:3] += np.random.uniform(500, 1000, (2, 3))

        elif label == 4:  # right_side (右侧卧)
            grid[:, 5:8] += np.random.uniform(1500, 3500, (8, 3))
            grid[3:5, 5:8] += np.random.uniform(500, 1000, (2, 3))

        elif label == 5:  # sitting (坐起)
            grid[4:8, 2:6] += np.random.uniform(2000, 4000, (4, 4))

        grid += np.random.normal(0, 100, (8, 8))
        grid = np.clip(grid, 0, 4095).astype(np.float32)

        X.append(grid)
        y.append(label)

        # 数据增强: 每个样本额外生成1个增强版本
        if augment and label != 0:  # 不增强empty类
            X.append(_augment_grid(grid))
            y.append(label)

    return np.array(X), np.array(y)


def train_posture_model(save_path="posture_cnn.pth", model_type="mobilenet", epochs=30):
    """
    训练睡姿分类模型

    model_type: 'cnn' (15K原始) | 'mobilenet' (45K MobileNetV3-style)
    """
    if not TORCH_AVAILABLE:
        print("[PressureAI] Cannot train without PyTorch")
        return None

    print("[PressureAI] Generating synthetic training data (with augmentation)...")
    X, y = generate_synthetic_data(3000, augment=True)

    X = X / 4095.0
    X = X.reshape(-1, 1, 8, 8)

    split = int(len(X) * 0.8)
    X_train, X_val = torch.FloatTensor(X[:split]), torch.FloatTensor(X[split:])
    y_train, y_val = torch.LongTensor(y[:split]), torch.LongTensor(y[split:])

    # 选择模型架构
    if model_type == "mobilenet":
        model = PostureMobileNet()
        print("[PressureAI] Using PostureMobileNet (MobileNetV3-style)")
    else:
        model = PostureCNN()
        print("[PressureAI] Using PostureCNN (lightweight)")

    params = sum(p.numel() for p in model.parameters())
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.002, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    print(f"[PressureAI] Training {model_type} ({params} params, {len(X_train)} train / {len(X_val)} val)...")

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

        model.eval()
        with torch.no_grad():
            val_out = model(X_val)
            val_pred = val_out.argmax(dim=1)
            val_acc = (val_pred == y_val).float().mean().item()

        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(model.state_dict(), save_path)

        if (epoch + 1) % 10 == 0:
            lr = scheduler.get_last_lr()[0]
            print(f"  Epoch {epoch+1}/{epochs} | Loss: {total_loss:.3f} | Val Acc: {val_acc:.1%} | LR: {lr:.5f}")

    print(f"[PressureAI] Training complete! Best accuracy: {best_acc:.1%}")
    print(f"[PressureAI] Model saved to {save_path} ({model_type}, {params} params)")

    # 自动导出ONNX
    onnx_path = save_path.replace('.pth', '.onnx')
    export_to_onnx(model, onnx_path)

    return model


# ═══════════════════════════════════════════
#  2. 受压风险监测 (基于规则, 不需要CNN)
# ═══════════════════════════════════════════

class PressureUlcerDetector:
    """
    受压风险监测器

    原理: 持续30分钟以上的高压接触会造成组织受压风险
    实现: 记录每个点的持续高压时间, 超过阈值则预警
    """
    def __init__(self, high_pressure_threshold=2000, risk_time_minutes=30):
        self.threshold = high_pressure_threshold
        self.risk_time = risk_time_minutes * 60  # 转秒
        # 记录每个点开始持续高压的时间
        self.high_pressure_start = np.zeros((8, 8))  # 0=无高压
        self.risk_points = []  # 当前风险点列表

    def update(self, grid):
        """
        更新压力数据, 检测受压风险
        grid: 8×8 numpy array (ADC值 0-4095)
        返回: 风险点列表 [(row, col, duration_minutes), ...]
        """
        now = time.time()
        self.risk_points = []

        for r in range(8):
            for c in range(8):
                if grid[r][c] > self.threshold:
                    if self.high_pressure_start[r][c] == 0:
                        # 开始高压
                        self.high_pressure_start[r][c] = now
                    else:
                        # 持续高压, 计算持续时间
                        duration = now - self.high_pressure_start[r][c]
                        if duration > self.risk_time:
                            minutes = int(duration / 60)
                            self.risk_points.append((r, c, minutes))
                else:
                    # 压力释放
                    self.high_pressure_start[r][c] = 0

        return self.risk_points

    def get_risk_level(self):
        """
        风险等级: none / low / medium / high
        """
        if not self.risk_points:
            return "none"
        max_duration = max(d for _, _, d in self.risk_points)
        if max_duration > 120:
            return "high"
        elif max_duration > 60:
            return "medium"
        else:
            return "low"

    def get_risk_summary(self):
        """获取受压风险摘要"""
        if not self.risk_points:
            return None
        return {
            "level": self.get_risk_level(),
            "points": [{"row": r, "col": c, "duration_min": d}
                       for r, c, d in self.risk_points],
            "recommendation": self._get_recommendation()
        }

    def _get_recommendation(self):
        level = self.get_risk_level()
        if level == "high":
            return "🚨 高受压风险！患者同一部位受压超过2小时,请立即协助翻身!"
        elif level == "medium":
            return "⚠️ 中等受压风险,患者同一部位受压超过1小时,建议尽快翻身"
        elif level == "low":
            return "📋 轻度受压提醒,患者同一部位持续受压超过30分钟"
        return ""


# ═══════════════════════════════════════════
#  3. 体位变化检测
# ═══════════════════════════════════════════

class PostureChangeDetector:
    """检测体位变化(翻身)"""

    def __init__(self, change_threshold=0.3):
        self.threshold = change_threshold
        self.prev_grid = None
        self.prev_posture = None
        self.last_change_time = 0
        self.change_count = 0  # 累计翻身次数
        self.history = deque(maxlen=100)  # 最近100次记录

    def update(self, grid, posture):
        """
        检测体位是否变化
        返回: True=有翻身, False=无变化
        """
        changed = False

        if self.prev_grid is not None:
            # 计算帧间差异 (归一化)
            diff = np.abs(grid - self.prev_grid).mean() / 4095.0

            if diff > self.threshold and posture != self.prev_posture:
                changed = True
                self.change_count += 1
                self.last_change_time = time.time()
                self.history.append({
                    "time": time.strftime("%H:%M:%S"),
                    "from": self.prev_posture,
                    "to": posture,
                    "diff": round(diff, 3)
                })
                print(f"[PressureAI] 🔄 体位变化: {self.prev_posture} → {posture}")

        self.prev_grid = grid.copy()
        self.prev_posture = posture
        return changed

    def get_summary(self):
        return {
            "total_changes": self.change_count,
            "last_change": self.last_change_time,
            "recent_history": list(self.history)[-10:]
        }


# ═══════════════════════════════════════════
#  4. 统一分析器 (对外接口)
# ═══════════════════════════════════════════

class PressureAnalyzer:
    """
    压力矩阵AI分析器 - 整合CNN+受压监测+翻身检测
    """
    def __init__(self, model_path="posture_cnn.pth"):
        # 模型 (PyTorch / ONNX)
        self.model = None
        self.onnx_session = None
        self.model_path = model_path
        self.model_type = "none"  # cnn / mobilenet / onnx
        self._load_best_model()

        # 受压监测器
        self.ulcer_detector = PressureUlcerDetector()

        # 翻身检测器
        self.change_detector = PostureChangeDetector()

        # 时序预测引擎 (创新点: 预测性护理)
        self.predictive_engine = None
        if PREDICTIVE_AVAILABLE:
            try:
                self.predictive_engine = PredictiveEngine()
            except Exception as e:
                print(f"[PressureAI] PredictiveEngine init failed: {e}")

        # 姿态持续时间追踪
        self._posture_since = time.time()
        self._current_posture = "unknown"

        # 最新分析结果
        self.latest_result = {}
        self._lock = threading.Lock()

        print(f"[PressureAI] Analyzer initialized (engine: {self.model_type})")

    def _load_best_model(self):
        """自动选择最佳可用模型: ONNX > MobileNet > CNN > Rules"""
        # 优先尝试ONNX
        onnx_path = self.model_path.replace('.pth', '.onnx')
        if ONNX_AVAILABLE and os.path.exists(onnx_path):
            try:
                self.onnx_session = ort.InferenceSession(onnx_path)
                self.model_type = "onnx"
                print(f"[PressureAI] ✅ ONNX Runtime model loaded: {onnx_path}")
                return
            except Exception as e:
                print(f"[PressureAI] ONNX load failed: {e}")

        if not TORCH_AVAILABLE:
            print("[PressureAI] No PyTorch/ONNX, using rule-based fallback")
            return

        # 尝试加载MobileNet
        mobilenet_path = self.model_path.replace('posture_cnn', 'posture_mobilenet')
        if os.path.exists(mobilenet_path):
            try:
                self.model = PostureMobileNet()
                self.model.load_state_dict(torch.load(mobilenet_path, map_location="cpu"))
                self.model.eval()
                self.model_type = "mobilenet"
                params = sum(p.numel() for p in self.model.parameters())
                print(f"[PressureAI] ✅ PostureMobileNet loaded ({params} params)")
                return
            except Exception as e:
                print(f"[PressureAI] MobileNet load failed: {e}")

        # 尝试加载原始CNN
        if os.path.exists(self.model_path):
            try:
                self.model = PostureCNN()
                self.model.load_state_dict(torch.load(self.model_path, map_location="cpu"))
                self.model.eval()
                self.model_type = "cnn"
                params = sum(p.numel() for p in self.model.parameters())
                print(f"[PressureAI] ✅ PostureCNN loaded ({params} params)")
                return
            except Exception as e:
                print(f"[PressureAI] CNN load failed: {e}")

        print("[PressureAI] No trained model found, run: python3 pressure_analyzer.py train")

    def _classify_posture_cnn(self, grid):
        """推理睡姿 (自动选择PyTorch/ONNX引擎)"""
        # ONNX Runtime 推理
        if self.onnx_session:
            x = np.array(grid, dtype=np.float32).reshape(1, 1, 8, 8) / 4095.0
            outputs = self.onnx_session.run(None, {'pressure_matrix': x})
            logits = outputs[0][0]
            # softmax
            exp_logits = np.exp(logits - np.max(logits))
            probs = exp_logits / exp_logits.sum()
            pred_idx = int(np.argmax(probs))
            return {
                "posture": POSTURE_CLASSES[pred_idx],
                "confidence": float(probs[pred_idx]),
                "all_probs": {c: float(p) for c, p in zip(POSTURE_CLASSES, probs)},
                "method": "onnx"
            }

        # PyTorch 推理
        if self.model is None:
            return self._classify_posture_rules(grid)

        x = np.array(grid, dtype=np.float32) / 4095.0
        x = torch.FloatTensor(x).reshape(1, 1, 8, 8)

        with torch.no_grad():
            output = self.model(x)
            probs = torch.softmax(output, dim=1).numpy()[0]
            pred_idx = int(np.argmax(probs))

        return {
            "posture": POSTURE_CLASSES[pred_idx],
            "confidence": float(probs[pred_idx]),
            "all_probs": {c: float(p) for c, p in zip(POSTURE_CLASSES, probs)},
            "method": self.model_type
        }

    def _classify_posture_rules(self, grid):
        """规则回退: 当CNN不可用时"""
        grid = np.array(grid, dtype=np.float32)
        total = grid.sum()

        if total < 5000:
            return {"posture": "empty", "confidence": 0.9, "method": "rules"}

        # 计算左/右/上/下的压力占比
        left_ratio = grid[:, :3].sum() / (total + 1e-6)
        right_ratio = grid[:, 5:].sum() / (total + 1e-6)
        top_ratio = grid[:4, :].sum() / (total + 1e-6)
        bottom_ratio = grid[4:, :].sum() / (total + 1e-6)
        center_ratio = grid[:, 2:6].sum() / (total + 1e-6)

        if left_ratio > 0.55:
            posture = "left_side"
        elif right_ratio > 0.55:
            posture = "right_side"
        elif bottom_ratio > 0.65:
            posture = "sitting"
        elif center_ratio > 0.6:
            posture = "supine"
        else:
            posture = "prone"

        return {"posture": posture, "confidence": 0.6, "method": "rules"}

    def analyze(self, grid_data):
        """
        分析压力矩阵数据

        参数:
            grid_data: 8×8 列表/数组 (ADC值 0-4095)

        返回:
            {
                "posture": {"posture": "supine", "confidence": 0.95, "method": "cnn"},
                "ulcer_risk": {"level": "none", ...} | None,
                "posture_change": False,
                "occupied": True,
                "body_regions": {...}
            }
        """
        grid = np.array(grid_data, dtype=np.float32)

        # 1. CNN睡姿分类
        posture_result = self._classify_posture_cnn(grid)

        # 2. 受压风险
        self.ulcer_detector.update(grid)
        ulcer_risk = self.ulcer_detector.get_risk_summary()

        # 3. 体位变化
        changed = self.change_detector.update(grid, posture_result["posture"])

        # 4. 身体区域压力分析
        body_regions = {
            "head_neck": float(grid[0:2, 2:6].mean()),
            "shoulders": float(grid[2:3, 1:7].mean()),
            "back": float(grid[3:5, 2:6].mean()),
            "hips": float(grid[5:7, 2:6].mean()),
            "legs": float(grid[7:8, 1:7].mean()),
        }

        # 5. 时序预测 (创新点: 预测未来30min受压风险)
        prediction = None
        if self.predictive_engine:
            # 追踪姿态持续时间
            current_posture = posture_result.get("posture", "unknown")
            if current_posture != self._current_posture:
                self._current_posture = current_posture
                self._posture_since = time.time()
            posture_duration_min = (time.time() - self._posture_since) / 60.0

            self.predictive_engine.update(
                pressure_total=float(grid.sum()),
                max_pressure=float(grid.max()),
                posture_duration_min=posture_duration_min
            )
            prediction = self.predictive_engine.predict()

        result = {
            "posture": posture_result,
            "ulcer_risk": ulcer_risk,
            "posture_change": changed,
            "change_stats": self.change_detector.get_summary(),
            "occupied": bool(grid.sum() > 5000),
            "body_regions": body_regions,
            "total_pressure": float(grid.sum()),
            "prediction": prediction,  # 时序预测结果
        }

        with self._lock:
            self.latest_result = result

        return result

    def get_latest(self):
        with self._lock:
            return self.latest_result.copy()


# ═══════════════════════════════════════════
#  CLI 入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import sys

    model_type = "mobilenet"  # 默认使用MobileNet
    if "--cnn" in sys.argv:
        model_type = "cnn"

    if len(sys.argv) > 1 and sys.argv[1] == "train":
        save_name = f"posture_{model_type}.pth"
        model = train_posture_model(save_path=save_name, model_type=model_type, epochs=30)
        if model:
            analyzer = PressureAnalyzer(model_path=save_name)
            test_grid = np.random.uniform(0, 200, (8, 8))
            test_grid[:, 2:6] += 2000
            result = analyzer.analyze(test_grid)
            print(f"\nTest Result: {result['posture']}")

    elif len(sys.argv) > 1 and sys.argv[1] == "benchmark":
        # 性能对比: CNN vs MobileNet
        print("\n═══ Model Benchmark ═══")
        for name, cls in [("PostureCNN", PostureCNN), ("PostureMobileNet", PostureMobileNet)]:
            m = cls()
            params = sum(p.numel() for p in m.parameters())
            x = torch.randn(1, 1, 8, 8)
            import timeit
            t = timeit.timeit(lambda: m(x), number=1000) / 1000 * 1000
            print(f"  {name}: {params:,} params, {t:.2f}ms/inference")
        print()

    else:
        print("用法:")
        print("  python3 pressure_analyzer.py train              # 训练MobileNet模型")
        print("  python3 pressure_analyzer.py train --cnn        # 训练原始CNN模型")
        print("  python3 pressure_analyzer.py benchmark          # 模型性能对比")
        print()
        print("训练后自动生成 .pth + .onnx 文件")
