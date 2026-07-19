#!/usr/bin/env python3
"""
智能护理病床 - 区块链健康数据存证模块

实现轻量级区块链存证:
  - SHA-256 链式哈希确保数据不可篡改
  - 关键体征数据自动上链存证
  - 支持存证验证和审计追溯
  
设计理念:
  - 不使用复杂的共识机制 (单节点场景)
  - 重点展示不可篡改的数据完整性保护
  - 链数据持久化为JSON文件
"""

import os
import json
import time
import hashlib
import threading
import logging

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[Blockchain] %(message)s')


class Block:
    """区块结构"""

    def __init__(self, index, timestamp, data, previous_hash, nonce=0):
        self.index = index
        self.timestamp = timestamp
        self.data = data
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self.compute_hash()

    def compute_hash(self):
        block_string = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(block_string.encode('utf-8')).hexdigest()

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash
        }

    @classmethod
    def from_dict(cls, d):
        block = cls(d['index'], d['timestamp'], d['data'], d['previous_hash'], d['nonce'])
        block.hash = d['hash']
        return block


class HealthBlockchain:
    """
    健康数据区块链
    
    存证类型:
      - vital_record: 关键体征记录
      - alert_record: 告警事件存证
      - ai_report: AI诊断报告摘要存证
      - decision_record: AI自主决策记录存证
    """

    DIFFICULTY = 2  # 工作量证明难度 (前N个字符为0)

    def __init__(self, chain_file="health_chain.json"):
        self.chain_file = chain_file
        self.chain = []
        self._lock = threading.Lock()
        self._stats = {"total_blocks": 0, "vital_records": 0, "alert_records": 0, "ai_reports": 0}

        # 加载或创建创世区块
        if os.path.exists(chain_file):
            self._load_chain()
        else:
            self._create_genesis()

        log.info("✅ HealthBlockchain initialized (%d blocks)", len(self.chain))

    def _create_genesis(self):
        """创建创世区块"""
        genesis = Block(
            index=0,
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
            data={
                "type": "genesis",
                "message": "智能护理病床健康数据链 - 创世区块",
                "version": "1.0",
                "created_by": "Smart Nursing Bed System"
            },
            previous_hash="0" * 64
        )
        self.chain.append(genesis)
        self._save_chain()

    def _proof_of_work(self, block):
        """简化的工作量证明"""
        target = "0" * self.DIFFICULTY
        while not block.hash.startswith(target):
            block.nonce += 1
            block.hash = block.compute_hash()
        return block

    def add_vital_record(self, patient_id, vitals, posture=None, anomalies=None):
        """
        体征数据存证
        
        仅存证关键指标的哈希摘要, 不存原始数据
        """
        data = {
            "type": "vital_record",
            "patient_id": patient_id,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "vital_hash": hashlib.sha256(json.dumps(vitals, sort_keys=True).encode()).hexdigest()[:16],
            "summary": {
                "hr": vitals.get("heart_rate"),
                "spo2": vitals.get("blood_oxygen"),
                "temp": vitals.get("temperature"),
                "bp": f"{vitals.get('blood_pressure_sys', '--')}/{vitals.get('blood_pressure_dia', '--')}",
                "posture": posture
            },
            "anomalies": anomalies or [],
            "data_integrity": "sha256_verified"
        }
        self._add_block(data)
        self._stats["vital_records"] += 1

    def add_alert_record(self, patient_id, alert_type, metric, value, message):
        """告警事件存证"""
        data = {
            "type": "alert_record",
            "patient_id": patient_id,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "alert_type": alert_type,
            "metric": metric,
            "value": value,
            "message": message
        }
        self._add_block(data)
        self._stats["alert_records"] += 1

    def add_ai_report(self, patient_id, report_summary, model_name="kimi-k2.5"):
        """AI诊断报告存证"""
        data = {
            "type": "ai_report",
            "patient_id": patient_id,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "report_hash": hashlib.sha256(report_summary.encode()).hexdigest()[:16],
            "model": model_name,
            "summary_preview": report_summary[:100] + "..." if len(report_summary) > 100 else report_summary
        }
        self._add_block(data)
        self._stats["ai_reports"] += 1

    def add_decision_record(self, rule_name, action, reason, value=None):
        """AI自主决策存证"""
        data = {
            "type": "decision_record",
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "rule": rule_name,
            "action": action,
            "reason": reason,
            "value": value
        }
        self._add_block(data)

    def _add_block(self, data):
        """添加新区块"""
        with self._lock:
            prev = self.chain[-1]
            new_block = Block(
                index=len(self.chain),
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                data=data,
                previous_hash=prev.hash
            )
            new_block = self._proof_of_work(new_block)
            self.chain.append(new_block)
            self._stats["total_blocks"] = len(self.chain)
            self._save_chain()

    def verify_chain(self):
        """验证区块链完整性"""
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            # 验证当前区块哈希
            if current.hash != current.compute_hash():
                return {"valid": False, "error": f"Block {i} hash mismatch", "block_index": i}

            # 验证链接
            if current.previous_hash != previous.hash:
                return {"valid": False, "error": f"Block {i} chain broken", "block_index": i}

        return {"valid": True, "blocks": len(self.chain), "message": "区块链完整性验证通过"}

    def get_chain_info(self):
        return {
            "length": len(self.chain),
            "latest_hash": self.chain[-1].hash if self.chain else None,
            "stats": self._stats.copy(),
            "integrity": self.verify_chain()
        }

    def get_recent_blocks(self, n=10):
        return [b.to_dict() for b in self.chain[-n:]]

    def _save_chain(self):
        try:
            chain_data = [b.to_dict() for b in self.chain]
            with open(self.chain_file, 'w', encoding='utf-8') as f:
                json.dump(chain_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error("Save chain failed: %s", e)

    def _load_chain(self):
        try:
            with open(self.chain_file, 'r', encoding='utf-8') as f:
                chain_data = json.load(f)
            self.chain = [Block.from_dict(d) for d in chain_data]
            self._stats["total_blocks"] = len(self.chain)
            # 统计各类型数量
            for block in self.chain:
                t = block.data.get("type", "")
                if t == "vital_record": self._stats["vital_records"] += 1
                elif t == "alert_record": self._stats["alert_records"] += 1
                elif t == "ai_report": self._stats["ai_reports"] += 1
        except Exception as e:
            log.error("Load chain failed: %s, creating new", e)
            self._create_genesis()


if __name__ == "__main__":
    # Demo
    bc = HealthBlockchain("demo_chain.json")

    # 存证体征数据
    bc.add_vital_record(1, {
        "heart_rate": 72, "blood_oxygen": 96, "temperature": 36.5,
        "blood_pressure_sys": 120, "blood_pressure_dia": 75
    }, posture="supine")

    bc.add_alert_record(1, "warning", "heart_rate", 125, "心率偏快")
    bc.add_ai_report(1, "患者张建国今日体征总体平稳,心率偶有波动...")
    bc.add_decision_record("低血氧自动抬高靠背", "raise_bed", "low_spo2", 88)

    # 验证
    result = bc.verify_chain()
    print(f"\n验证结果: {result}")
    print(f"链信息: {bc.get_chain_info()}")

    # 清理demo文件
    os.remove("demo_chain.json")
