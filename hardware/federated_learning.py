#!/usr/bin/env python3
"""
智能护理病床 - 联邦学习 PoC 模块

实现隐私保护的多床位协作训练:
  - 各床位本地训练 → 上传模型梯度 → 聚合 → 分发
  - 压力矩阵睡姿分类模型的联邦训练
  - 支持 FedAvg 聚合策略

特点:
  - 患者压力数据不出本地设备
  - 仅共享模型参数 (梯度/权重差分)
  - 差分隐私 (添加噪声保护)
"""

import json
import time
import copy
import hashlib
import logging
import numpy as np

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[FedLearn] %(message)s')

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

if TORCH_AVAILABLE:
    from pressure_analyzer import PostureCNN, generate_synthetic_data, POSTURE_CLASSES


class FederatedClient:
    """
    联邦学习客户端 (每台病床一个)
    
    本地训练 → 差分 → 上传权重差
    """

    def __init__(self, client_id, model=None, dp_epsilon=1.0):
        self.client_id = client_id
        self.model = model or (PostureCNN() if TORCH_AVAILABLE else None)
        self.dp_epsilon = dp_epsilon  # 差分隐私参数
        self.round_count = 0
        self.local_data_size = 0
        self._base_weights = None  # 训练前的权重快照

        log.info("FedClient '%s' initialized (DP ε=%.1f)", client_id, dp_epsilon)

    def receive_global_model(self, global_weights):
        """接收全局模型权重"""
        if not TORCH_AVAILABLE or not self.model:
            return
        self.model.load_state_dict(copy.deepcopy(global_weights))
        self._base_weights = copy.deepcopy(global_weights)

    def local_train(self, X, y, epochs=5, lr=0.001):
        """
        本地训练 (数据不上传)
        
        X: numpy array (N, 8, 8)
        y: numpy array (N,)
        返回: 训练后的权重差 (用于上传)
        """
        if not TORCH_AVAILABLE or not self.model:
            return None

        self.local_data_size = len(X)

        # 归一化
        X_tensor = torch.FloatTensor(X / 4095.0).reshape(-1, 1, 8, 8)
        y_tensor = torch.LongTensor(y)

        optimizer = torch.optim.SGD(self.model.parameters(), lr=lr, momentum=0.9)
        criterion = nn.CrossEntropyLoss()

        self.model.train()
        for epoch in range(epochs):
            perm = torch.randperm(len(X_tensor))
            total_loss = 0
            for i in range(0, len(X_tensor), 32):
                idx = perm[i:i+32]
                out = self.model(X_tensor[idx])
                loss = criterion(out, y_tensor[idx])
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

        self.round_count += 1

        # 计算权重差 (本地训练后 - 训练前)
        weight_delta = {}
        current_weights = self.model.state_dict()
        for key in current_weights:
            if self._base_weights and key in self._base_weights:
                delta = current_weights[key] - self._base_weights[key]
                # 差分隐私: 添加高斯噪声
                if self.dp_epsilon < float('inf'):
                    noise_scale = 1.0 / self.dp_epsilon
                    noise = torch.randn_like(delta) * noise_scale * delta.abs().mean()
                    delta = delta + noise
                weight_delta[key] = delta
            else:
                weight_delta[key] = current_weights[key]

        return {
            'client_id': self.client_id,
            'weight_delta': weight_delta,
            'data_size': self.local_data_size,
            'round': self.round_count
        }


class FederatedServer:
    """
    联邦学习服务端 (云端聚合器)
    
    聚合多个客户端的权重差 → 更新全局模型
    支持 FedAvg (加权平均) 策略
    """

    def __init__(self):
        self.global_model = PostureCNN() if TORCH_AVAILABLE else None
        self.global_round = 0
        self.client_contributions = []
        self.history = []  # 训练历史

        log.info("FedServer initialized")

    def get_global_weights(self):
        if not self.global_model:
            return {}
        return copy.deepcopy(self.global_model.state_dict())

    def aggregate(self, client_updates):
        """
        FedAvg 聚合: 按数据量加权平均各客户端的权重差
        
        client_updates: [{ 'client_id': str, 'weight_delta': dict, 'data_size': int }, ...]
        """
        if not TORCH_AVAILABLE or not self.global_model or not client_updates:
            return

        total_data = sum(u['data_size'] for u in client_updates)
        if total_data == 0:
            return

        # 加权聚合
        aggregated_delta = {}
        for key in client_updates[0]['weight_delta']:
            weighted_sum = None
            for update in client_updates:
                weight = update['data_size'] / total_data
                delta = update['weight_delta'].get(key)
                if delta is not None:
                    if weighted_sum is None:
                        weighted_sum = delta * weight
                    else:
                        weighted_sum = weighted_sum + delta * weight

            if weighted_sum is not None:
                aggregated_delta[key] = weighted_sum

        # 应用聚合后的差到全局模型
        global_weights = self.global_model.state_dict()
        for key in aggregated_delta:
            if key in global_weights:
                global_weights[key] = global_weights[key] + aggregated_delta[key]

        self.global_model.load_state_dict(global_weights)
        self.global_round += 1

        # 记录历史
        self.history.append({
            'round': self.global_round,
            'clients': len(client_updates),
            'total_data': total_data,
            'client_ids': [u['client_id'] for u in client_updates],
            'time': time.strftime('%Y-%m-%d %H:%M:%S')
        })

        self.client_contributions = client_updates
        log.info("Round %d: Aggregated %d clients (%d samples)",
                 self.global_round, len(client_updates), total_data)

        return self.get_global_weights()

    def evaluate(self, X_test, y_test):
        """评估全局模型"""
        if not TORCH_AVAILABLE or not self.global_model:
            return {'accuracy': 0}

        X_tensor = torch.FloatTensor(X_test / 4095.0).reshape(-1, 1, 8, 8)
        y_tensor = torch.LongTensor(y_test)

        self.global_model.eval()
        with torch.no_grad():
            out = self.global_model(X_tensor)
            pred = out.argmax(dim=1)
            acc = (pred == y_tensor).float().mean().item()

        return {
            'accuracy': round(acc, 4),
            'round': self.global_round,
            'test_samples': len(y_test)
        }

    def get_status(self):
        return {
            'global_round': self.global_round,
            'history': self.history[-10:],
            'model_params': sum(p.numel() for p in self.global_model.parameters()) if self.global_model else 0
        }


def run_federated_demo(n_clients=3, n_rounds=5):
    """
    联邦学习 Demo: 模拟多台病床协作训练
    """
    if not TORCH_AVAILABLE:
        log.error("PyTorch not available, cannot run federated demo")
        return

    log.info("=" * 50)
    log.info("  联邦学习Demo: %d客户端, %d轮", n_clients, n_rounds)
    log.info("=" * 50)

    # 初始化
    server = FederatedServer()
    clients = [FederatedClient(f"bed_{i+1}", dp_epsilon=2.0) for i in range(n_clients)]

    # 生成各客户端的本地数据 (模拟不同病床的数据分布)
    client_data = []
    for i in range(n_clients):
        X, y = generate_synthetic_data(500 + i * 100)  # 各床位数据量不同
        client_data.append((X, y))

    # 全局测试集
    X_test, y_test = generate_synthetic_data(300)

    # 训练前评估
    pre_eval = server.evaluate(X_test, y_test)
    log.info("Pre-training accuracy: %.1f%%", pre_eval['accuracy'] * 100)

    # 联邦训练轮次
    for round_idx in range(n_rounds):
        log.info("--- Round %d/%d ---", round_idx + 1, n_rounds)

        # 1. 分发全局模型
        global_weights = server.get_global_weights()
        for client in clients:
            client.receive_global_model(global_weights)

        # 2. 各客户端本地训练
        updates = []
        for i, client in enumerate(clients):
            X, y = client_data[i]
            update = client.local_train(X, y, epochs=3)
            if update:
                updates.append(update)
                log.info("  Client %s: trained on %d samples", client.client_id, len(X))

        # 3. 服务端聚合
        server.aggregate(updates)

        # 4. 评估
        eval_result = server.evaluate(X_test, y_test)
        log.info("  Global accuracy: %.1f%%", eval_result['accuracy'] * 100)

    log.info("=" * 50)
    log.info("  Final accuracy: %.1f%%", eval_result['accuracy'] * 100)
    log.info("  Privacy: DP ε=2.0 (each client)")
    log.info("=" * 50)

    return server.get_status()


if __name__ == "__main__":
    run_federated_demo()
