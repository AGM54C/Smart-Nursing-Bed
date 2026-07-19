#!/usr/bin/env python3
"""
智能护理病床 - 患者个性化护理记忆 (借鉴 OpenHarness Memory)

让AI Agent具备跨会话学习能力, 不再"每次都是陌生人":
  - 记住患者习惯: 张爷爷每天5点起床, 凌晨5点离床不告警
  - 记住沟通偏好: 李奶奶对翻身抗拒, 用"帮您调整"替代"请翻身"
  - 个性化阈值: 王叔叔COPD, SpO2阈值设为88%而不是93%
  - 护理效果反馈: 上次气囊减压3小时前, 效果=有效

对标 OpenHarness 模式:
  ohmo/memory.py            → PatientMemory (文件持久化)
  memory/manager.py         → MemoryManager (增删查)
  MEMORY.md (索引文件)      → memory/patient_{id}/MEMORY.md
  add_memory_entry()        → record_preference()
  load_memory_prompt()      → get_context_for_prompt()
"""

import os
import json
import time
import logging
from collections import deque
from threading import Lock

logging.basicConfig(level=logging.INFO, format='[PatientMemory] %(message)s')
log = logging.getLogger(__name__)


class PatientMemory:
    """
    患者个性化护理记忆

    对标 OpenHarness ohmo/memory.py 的持久化记忆机制:
      - OpenHarness: .ohmo/memory/*.md 文件 + MEMORY.md 索引
      - 本项目: memory/patient_{id}.json (JSON格式, 便于程序读写)
      - 增加: 护理响应效果追踪, 个性化阈值学习, LLM prompt注入
    """

    def __init__(self, patient_id, memory_dir="memory"):
        self.patient_id = patient_id
        self._memory_dir = memory_dir
        self._memory_file = os.path.join(memory_dir, f"patient_{patient_id}.json")
        self._lock = Lock()

        # 内存数据结构
        self._data = {
            "patient_id": patient_id,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": "",

            # 患者偏好 (对标 OpenHarness MEMORY.md stable preferences)
            "preferences": {},
            # 例: {"wake_time": "05:00", "turn_reluctant": true,
            #       "preferred_name": "张爷爷", "communication_style": "温和"}

            # 个性化阈值 (从通用阈值根据病史调整)
            "custom_thresholds": {},
            # 例: {"blood_oxygen_min": 88, "heart_rate_max": 110}

            # 护理响应历史 (追踪效果)
            "care_responses": [],
            # 例: [{"time": "...", "action": "air_relief_cycle",
            #        "effectiveness": "effective", "note": "受压缓解"}]

            # 行为模式 (自动学习)
            "behavior_patterns": {},
            # 例: {"early_riser": true, "avg_wake_time": "05:15",
            #       "sleep_start": "21:30", "turn_frequency": 4.2}

            # 情绪基线 (陪伴Agent参考)
            "emotion_baseline": {},
            # 例: {"avg_valence": 0.3, "loneliness_risk": "medium",
            #       "preferred_topics": ["天气", "孙子"]}

            # 累计统计
            "stats": {
                "total_decisions": 0,
                "alerts_count": 0,
                "effective_interventions": 0,
                "total_interactions": 0,
            },
        }

        # 最近决策历史 (短期记忆, 对标原有 _decision_history[-20:])
        self._recent_decisions = deque(maxlen=50)

        # 加载已有记忆
        self._load()
        log.info("🧠 PatientMemory loaded for patient_%d (%d preferences, %d responses)",
                 patient_id,
                 len(self._data.get("preferences", {})),
                 len(self._data.get("care_responses", [])))

    # ═══════════════════════════════════════
    #  持久化 (对标 OpenHarness memory file I/O)
    # ═══════════════════════════════════════

    def _load(self):
        """加载持久化记忆 (对标 OpenHarness memory/scan.py 扫描)"""
        os.makedirs(self._memory_dir, exist_ok=True)
        if os.path.exists(self._memory_file):
            try:
                with open(self._memory_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # 合并加载的数据 (保留默认结构)
                for key in saved:
                    if key in self._data:
                        self._data[key] = saved[key]
                # 恢复最近决策
                for d in saved.get("recent_decisions", []):
                    self._recent_decisions.append(d)
            except (json.JSONDecodeError, Exception) as e:
                log.warning("Failed to load memory for patient_%d: %s",
                           self.patient_id, e)

    def save(self):
        """
        持久化到磁盘

        对标 OpenHarness add_memory_entry() 的文件写入
        (OpenHarness: path.write_text(content) + 更新 MEMORY.md 索引)
        """
        with self._lock:
            self._data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self._data["recent_decisions"] = list(self._recent_decisions)
            try:
                os.makedirs(self._memory_dir, exist_ok=True)
                tmp_file = self._memory_file + ".tmp"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_file, self._memory_file)  # 原子写入
            except Exception as e:
                log.error("Failed to save memory: %s", e)

    # ═══════════════════════════════════════
    #  记录API (对标 OpenHarness add_memory_entry)
    # ═══════════════════════════════════════

    def record_preference(self, key: str, value, note: str = ""):
        """
        记录患者偏好

        对标 OpenHarness add_memory_entry(workspace, title, content):
          - OpenHarness 写一个 .md 文件 + 追加到 MEMORY.md 索引
          - 本项目写入 JSON preferences 字段

        示例:
          record_preference("wake_time", "05:00", "每天5点准时起床")
          record_preference("turn_reluctant", True, "对翻身有抗拒")
          record_preference("preferred_name", "张爷爷")
        """
        with self._lock:
            self._data["preferences"][key] = {
                "value": value,
                "note": note,
                "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        self.save()
        log.info("📝 Preference recorded: %s=%s (%s)", key, value, note)

    def record_response(self, action: str, effectiveness: str,
                       note: str = "", context: dict = None):
        """
        记录护理响应效果 (本项目独创: OpenHarness没有效果反馈机制)

        effectiveness: "effective" / "partial" / "ineffective" / "unknown"
        """
        with self._lock:
            response = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "action": action,
                "effectiveness": effectiveness,
                "note": note,
            }
            if context:
                response["context_snapshot"] = {
                    k: context.get(k) for k in
                    ["posture", "heart_rate", "blood_oxygen", "ulcer_risk_level"]
                    if context.get(k) is not None
                }
            self._data["care_responses"].append(response)
            # 只保留最近100条
            self._data["care_responses"] = self._data["care_responses"][-100:]
            # 更新统计
            if effectiveness == "effective":
                self._data["stats"]["effective_interventions"] += 1
        self.save()

    def record_decision(self, decision: dict):
        """记录短期决策历史"""
        with self._lock:
            decision["time"] = time.strftime("%H:%M:%S")
            self._recent_decisions.append(decision)
            self._data["stats"]["total_decisions"] += 1

    def update_thresholds(self, metric: str, value: float):
        """
        个性化阈值学习

        示例: COPD患者 → update_thresholds("blood_oxygen_min", 88)
        """
        with self._lock:
            self._data["custom_thresholds"][metric] = {
                "value": value,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        self.save()
        log.info("📊 Threshold updated: %s=%.1f", metric, value)

    def update_behavior(self, key: str, value):
        """更新行为模式 (自动学习)"""
        with self._lock:
            self._data["behavior_patterns"][key] = value

    def update_emotion_baseline(self, **kwargs):
        """更新情绪基线"""
        with self._lock:
            self._data["emotion_baseline"].update(kwargs)

    # ═══════════════════════════════════════
    #  查询API
    # ═══════════════════════════════════════

    def get_preference(self, key: str, default=None):
        """获取患者偏好"""
        pref = self._data.get("preferences", {}).get(key)
        if pref:
            return pref.get("value", default)
        return default

    def get_custom_threshold(self, metric: str, default=None) -> float:
        """获取个性化阈值"""
        threshold = self._data.get("custom_thresholds", {}).get(metric)
        if threshold:
            return threshold.get("value", default)
        return default

    def get_recent_decisions(self, count: int = 10) -> list:
        """获取最近决策"""
        return list(self._recent_decisions)[-count:]

    def get_care_history(self, hours: int = 24) -> list:
        """获取最近N小时的护理响应历史"""
        cutoff = time.time() - hours * 3600
        results = []
        for resp in self._data.get("care_responses", []):
            try:
                resp_time = time.mktime(
                    time.strptime(resp["time"], "%Y-%m-%d %H:%M:%S"))
                if resp_time > cutoff:
                    results.append(resp)
            except (ValueError, KeyError):
                continue
        return results

    def get_last_action_time(self, action: str) -> float:
        """获取某动作上次执行时间 (秒 since epoch, 0=从未)"""
        for resp in reversed(self._data.get("care_responses", [])):
            if resp.get("action") == action:
                try:
                    return time.mktime(
                        time.strptime(resp["time"], "%Y-%m-%d %H:%M:%S"))
                except (ValueError, KeyError):
                    pass
        return 0

    # ═══════════════════════════════════════
    #  LLM Prompt 注入 (核心创新)
    # ═══════════════════════════════════════

    def get_context_for_prompt(self) -> str:
        """
        为LLM Agent构建记忆注入提示

        对标 OpenHarness load_memory_prompt(workspace):
          - OpenHarness: 读取 MEMORY.md + 各记忆文件内容, 拼接为 prompt
          - 本项目: 从JSON提取关键信息, 构建自然语言 prompt 段落

        返回的文本会被注入到各专科Agent的用户消息中
        """
        parts = []

        # 患者偏好
        prefs = self._data.get("preferences", {})
        if prefs:
            pref_texts = []
            for key, pref_data in prefs.items():
                val = pref_data.get("value", "")
                note = pref_data.get("note", "")
                if note:
                    pref_texts.append(f"  - {key}: {val} ({note})")
                else:
                    pref_texts.append(f"  - {key}: {val}")
            parts.append("患者偏好记忆:\n" + "\n".join(pref_texts))

        # 个性化阈值
        thresholds = self._data.get("custom_thresholds", {})
        if thresholds:
            th_texts = []
            for metric, th_data in thresholds.items():
                th_texts.append(f"  - {metric}: {th_data.get('value')}")
            parts.append("个性化阈值:\n" + "\n".join(th_texts))

        # 行为模式
        patterns = self._data.get("behavior_patterns", {})
        if patterns:
            pat_texts = []
            for key, val in patterns.items():
                pat_texts.append(f"  - {key}: {val}")
            parts.append("行为模式:\n" + "\n".join(pat_texts))

        # 最近护理效果 (只取最近5条)
        recent_care = self._data.get("care_responses", [])[-5:]
        if recent_care:
            care_texts = []
            for resp in recent_care:
                care_texts.append(
                    f"  - [{resp.get('time', '?')}] {resp.get('action')}: "
                    f"{resp.get('effectiveness', '?')} "
                    f"{'- ' + resp.get('note') if resp.get('note') else ''}"
                )
            parts.append("最近护理效果:\n" + "\n".join(care_texts))

        # 情绪基线
        emotion = self._data.get("emotion_baseline", {})
        if emotion:
            emo_texts = []
            for key, val in emotion.items():
                emo_texts.append(f"  - {key}: {val}")
            parts.append("情绪基线:\n" + "\n".join(emo_texts))

        if not parts:
            return ""

        return "\n\n[护理记忆 - 以下信息来自该患者的历史记录，请参考]\n" + "\n".join(parts)

    def get_full_data(self) -> dict:
        """获取完整记忆数据 (供API查询)"""
        with self._lock:
            data = dict(self._data)
            data["recent_decisions"] = list(self._recent_decisions)
            return data

    def get_stats(self) -> dict:
        """获取统计数据"""
        return dict(self._data.get("stats", {}))


# ═══════════════════════════════════════════
#  记忆索引管理 (对标 OpenHarness MEMORY.md)
# ═══════════════════════════════════════════

class MemoryIndex:
    """
    患者记忆索引管理器

    对标 OpenHarness 的 MEMORY.md 索引文件:
      - OpenHarness: 在 MEMORY.md 中维护 [title](filename.md) 链接列表
      - 本项目: 维护一个 memory/MEMORY.md 索引, 列出所有患者记忆文件
    """

    def __init__(self, memory_dir="memory"):
        self._memory_dir = memory_dir
        self._index_file = os.path.join(memory_dir, "MEMORY.md")

    def update_index(self):
        """更新记忆索引文件 (对标 OpenHarness add_memory_entry 中的索引更新)"""
        os.makedirs(self._memory_dir, exist_ok=True)
        lines = [
            "# 智能护理病床 - 患者护理记忆索引\n",
            f"_更新时间: {time.strftime('%Y-%m-%d %H:%M:%S')}_\n",
            "",
        ]

        # 扫描所有patient_*.json文件
        patient_files = sorted(
            f for f in os.listdir(self._memory_dir)
            if f.startswith("patient_") and f.endswith(".json")
        )

        for fname in patient_files:
            filepath = os.path.join(self._memory_dir, fname)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                patient_id = data.get("patient_id", "?")
                prefs_count = len(data.get("preferences", {}))
                responses_count = len(data.get("care_responses", []))
                updated = data.get("updated_at", "未知")
                lines.append(
                    f"- [患者{patient_id}]({fname}) — "
                    f"{prefs_count}项偏好, {responses_count}条护理记录, "
                    f"最后更新: {updated}"
                )
            except Exception:
                lines.append(f"- [{fname}]({fname}) — 读取失败")

        if not patient_files:
            lines.append("_暂无患者记忆记录_")

        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            log.error("Failed to update memory index: %s", e)

    def list_patients(self) -> list[int]:
        """列出所有有记忆的患者ID"""
        os.makedirs(self._memory_dir, exist_ok=True)
        patient_ids = []
        for fname in os.listdir(self._memory_dir):
            if fname.startswith("patient_") and fname.endswith(".json"):
                try:
                    pid = int(fname.replace("patient_", "").replace(".json", ""))
                    patient_ids.append(pid)
                except ValueError:
                    pass
        return sorted(patient_ids)
