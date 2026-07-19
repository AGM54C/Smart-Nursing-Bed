#!/usr/bin/env python3
"""
智能护理病床 - AI自主决策引擎 v4.0 (Multi-Agent Swarm)

创新升级:
  v1.0: 8条硬编码规则
  v2.0: LLM Agent 自适应推理 + 安全沙箱 + 预测性护理 + 气囊减压
  v3.0: NearLink定位 + 语音双模式
  v4.0: Multi-Agent Nursing Swarm (借鉴 OpenHarness)
        - NursingCoordinator: 分诊路由 + 结果聚合 (对标 OpenHarness CoordinatorMode)
        - SpecialistLLMAgent: 专科Agent (对标 OpenHarness AgentDefinition)
        - ToolPermissionChecker: Agent工具权限沙箱 (对标 OpenHarness PermissionChecker)

架构:
  ┌─────────────────────────┐
  │ L0: 传统规则 (兜底)       │  ← 9条基础规则, 确保安全下界
  ├─────────────────────────┤
  │ L1: Multi-Agent Swarm    │  ← NursingCoordinator → 4专科Agent 并行决策
  │     ┌─ VitalsAgent       │
  │     ├─ PressureAgent     │
  │     ├─ EmergencyAgent    │
  │     └─ CompanionAgent    │
  ├─────────────────────────┤
  │ L2: 参数沙箱 (约束)       │  ← 硬编码物理上限 + Agent工具权限
  ├─────────────────────────┤
  │ L3: 人工审核 (高危)       │  ← critical级动作需护士确认
  └─────────────────────────┘

依赖: mqtt_bridge, bed_actuator, air_cushion, voice_client,
      agent_definitions, agent_mailbox, patient_memory
"""

import time
import json
import threading
import logging
import requests

logging.basicConfig(level=logging.INFO, format='[DecisionEngine] %(message)s')
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  安全沙箱: 动作白名单 + 参数边界
# ═══════════════════════════════════════════

# L1: 动作白名单 (LLM只能从中选择)
ALLOWED_ACTIONS = {
    "raise_bed",           # 抬高靠背
    "lower_bed",           # 降低靠背
    "bed_stop",            # 停止升降
    "voice_remind",        # 语音提醒
    "alert_info",          # 普通通知
    "alert_warning",       # 警告告警
    "alert_critical",      # 紧急告警 (需人工审核)
    "air_inflate",         # 气囊充气
    "air_deflate",         # 气囊放气
    "air_relief_cycle",    # 气囊减压循环
    "no_action",           # 不采取行动
}

# L2: 参数边界 (硬编码, LLM无法突破)
PARAM_BOUNDS = {
    "raise_bed": {"max_duration": 3.0, "max_speed": 70},
    "lower_bed": {"max_duration": 3.0, "max_speed": 70},
    "air_inflate": {"max_duration": 10.0},
    "voice_remind": {"max_length": 200},  # 语音文本最大字数
}


class DecisionRule:
    """单条决策规则 (传统规则引擎, 作为安全兜底)"""
    def __init__(self, name, condition_fn, action_fn, cooldown=300, priority=1):
        self.name = name
        self.condition = condition_fn
        self.action = action_fn
        self.cooldown = cooldown
        self.priority = priority
        self.last_triggered = 0

    def can_trigger(self):
        return time.time() - self.last_triggered > self.cooldown

    def trigger(self, context):
        self.last_triggered = time.time()
        return self.action(context)


# ═══════════════════════════════════════════
#  LLM 决策 Agent (核心创新)
# ═══════════════════════════════════════════

class LLMDecisionAgent:
    """
    大模型驱动的护理决策 Agent

    特点:
      - 理解多维上下文 (体征+压力+病史+趋势)
      - 输出结构化 JSON 决策
      - 附带推理链 (可解释)
      - 安全沙箱约束 (白名单+参数边界)
    """

    SYSTEM_PROMPT = """你是一个智能护理病床的AI决策助手。根据患者的实时体征和环境数据，判断是否需要执行护理动作。

你只能选择以下动作之一:
- raise_bed: 抬高靠背 (适用于: 呼吸困难、低血氧、进食)
- lower_bed: 降低靠背 (适用于: 需要平躺休息)
- bed_stop: 停止升降
- voice_remind: 语音提醒患者 (适用于: 翻身提醒、喝水、吃药)
- alert_info: 普通通知护士 (适用于: 一般异常)
- alert_warning: 警告告警 (适用于: 体征明显异常)
- alert_critical: 紧急告警 (适用于: 跌倒、严重生命体征异常)
- air_inflate: 气囊充气减压 (适用于: 受压风险, zone可选left/right/both)
- air_deflate: 气囊放气
- air_relief_cycle: 气囊自动减压循环 (适用于: 长时间受压)
- no_action: 当前状况正常,不需要采取行动

重要:
1. 不同病种的阈值不同: COPD患者SpO2≥88%即可, 普通人需≥93%
2. 考虑上下文: 刚翻身后心率暂升是正常的
3. 趋势比瞬时值更重要: 持续下降比偶尔偏低更危险

你必须严格以JSON格式回复:
{"action": "动作名", "params": {"duration": 2.0, "speed": 60, "zone": "left", "text": "提醒文本"}, "reasoning": "简短推理链(50字内)", "confidence": 0.85, "urgency": "low/medium/high"}

params中只包含该动作需要的参数。如果选择no_action,params为空对象{}。"""

    def __init__(self, cloud_server, api_key):
        self.cloud_server = cloud_server
        self.api_key = api_key
        self._last_query_time = 0
        self._query_interval = 30       # 最少30秒查询一次LLM
        self._llm_timeout = 40          # 初始超时40s（kimi-k2.5大模型响应较慢）
        self._decision_history = []     # 最近决策历史

        log.info("🧠 LLMDecisionAgent initialized")

    def should_query(self):
        """判断是否应该查询LLM (避免过于频繁；超时后间隔自动加大)"""
        return time.time() - self._last_query_time > self._query_interval

    def build_prompt(self, context, patient_info=None):
        """
        构建上下文 Prompt

        context: 多维感知数据 dict
        patient_info: 患者基本信息 dict (病种/年龄/体重)
        """
        prompt_parts = []

        # 患者信息
        if patient_info:
            prompt_parts.append(f"患者: {patient_info.get('name', '未知')}, "
                               f"{patient_info.get('age', '?')}岁, "
                               f"病种: {patient_info.get('disease_type', '通用')}")

        # 实时体征
        vitals = []
        if context.get('heart_rate'):
            vitals.append(f"心率{context['heart_rate']}bpm")
        if context.get('blood_oxygen'):
            vitals.append(f"血氧{context['blood_oxygen']}%")
        if context.get('temperature'):
            vitals.append(f"体温{context['temperature']}°C")
        if context.get('blood_pressure_sys'):
            vitals.append(f"血压{context['blood_pressure_sys']}/{context.get('blood_pressure_dia', '?')}mmHg")
        if vitals:
            prompt_parts.append("实时体征: " + ", ".join(vitals))

        # 睡姿与受压
        if context.get('posture'):
            mins = context.get('posture_unchanged_minutes', 0)
            prompt_parts.append(f"当前姿态: {context['posture']} (持续{mins:.0f}分钟)")
        if context.get('ulcer_risk_level'):
            prompt_parts.append(f"受压风险: {context['ulcer_risk_level']}")

        # 预测性数据
        if context.get('predicted_risk') is not None:
            risk = context['predicted_risk']
            prompt_parts.append(f"30min受压风险预测: {risk:.0%}")

        # 体征趋势
        if context.get('vitals_trend'):
            trend = context['vitals_trend']
            trend_parts = []
            if trend.get('hr_trend'):
                trend_parts.append(f"心率趋势: {trend['hr_trend']}")
            if trend.get('spo2_trend'):
                trend_parts.append(f"血氧趋势: {trend['spo2_trend']}")
            if trend_parts:
                prompt_parts.append("趋势: " + ", ".join(trend_parts))

        # 最近动作 (避免重复)
        if self._decision_history:
            last = self._decision_history[-1]
            prompt_parts.append(f"最近动作: {last.get('action')} ({last.get('time', '?')})")

        return "\n".join(prompt_parts)

    def query(self, context, patient_info=None):
        """
        查询 LLM 获取决策

        返回: {
            "action": str,
            "params": dict,
            "reasoning": str,
            "confidence": float,
            "urgency": str,
            "source": "llm"
        } 或 None (查询失败时)
        """
        if not self.should_query():
            return None

        # ── 空上下文守卫: 无任何体征数据时跳过LLM ──
        has_vitals = any(context.get(k) is not None for k in
                         ('heart_rate', 'blood_oxygen', 'temperature', 'blood_pressure_sys'))
        if not has_vitals:
            log.info("[LLM] Skipped: no sensor context (all vitals are None)")
            return None

        prompt = self.build_prompt(context, patient_info)
        self._last_query_time = time.time()

        try:
            resp = requests.post(
                f"{self.cloud_server}/api/agents/consult",
                json={
                    "agent_name": "decision_agent",
                    "question": prompt,
                    "system_prompt": self.SYSTEM_PROMPT
                },
                headers={"X-API-Key": self.api_key},
                timeout=self._llm_timeout
            )

            if resp.status_code != 200:
                log.warning("LLM query failed: HTTP %d", resp.status_code)
                return None

            ai_text = resp.json().get("response", "")
            decision = self._parse_response(ai_text)

            if decision:
                decision["source"] = "llm"
                decision["time"] = time.strftime("%H:%M:%S")
                self._decision_history.append(decision)
                self._decision_history = self._decision_history[-20:]
                # 成功：重置超时和间隔
                self._llm_timeout = 15
                self._query_interval = 30
                log.info("[LLM] Success, timeout reset to %ds", self._llm_timeout)

            return decision

        except requests.exceptions.Timeout:
            # 自适应退避：超时时加大超时时间和查询间隔
            self._llm_timeout = min(self._llm_timeout * 1.5, 120)
            self._query_interval = min(self._query_interval * 2, 600)
            log.warning("[LLM] Timeout! Backing off: timeout→%.0fs, interval→%ds",
                        self._llm_timeout, self._query_interval)
            return None
        except requests.exceptions.RequestException as e:
            log.warning("LLM query error: %s", e)
            return None
        except Exception as e:
            log.error("LLM decision error: %s", e)
            return None

    def _parse_response(self, text):
        """解析 LLM JSON 响应, 用安全沙箱校验"""
        try:
            json_match = None
            # 尝试提取 JSON
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                json_match = json.loads(match.group(0))
        except (json.JSONDecodeError, Exception):
            log.warning("LLM response parse failed: %s", text[:100])
            return None

        if not json_match:
            return None

        action = json_match.get("action", "no_action")
        params = json_match.get("params", {})
        reasoning = json_match.get("reasoning", "")
        confidence = json_match.get("confidence", 0.5)
        urgency = json_match.get("urgency", "low")

        # ─── L1: 白名单校验 ───
        if action not in ALLOWED_ACTIONS:
            log.warning("🚫 LLM tried invalid action '%s', blocked", action)
            return None

        # ─── L2: 参数边界裁剪 ───
        if action in PARAM_BOUNDS:
            bounds = PARAM_BOUNDS[action]
            if "max_duration" in bounds and params.get("duration"):
                params["duration"] = min(float(params["duration"]), bounds["max_duration"])
            if "max_speed" in bounds and params.get("speed"):
                params["speed"] = min(int(params["speed"]), bounds["max_speed"])
            if "max_length" in bounds and params.get("text"):
                params["text"] = str(params["text"])[:bounds["max_length"]]

        return {
            "action": action,
            "params": params,
            "reasoning": reasoning,
            "confidence": confidence,
            "urgency": urgency,
        }


# ═══════════════════════════════════════════
#  决策引擎主类
# ═══════════════════════════════════════════

class DecisionEngine:
    """
    AI-in-the-Loop 自主决策引擎 v2.0

    双层决策:
      1. 传统规则 (安全兜底, 即时响应)
      2. LLM Agent (上下文推理, 智能决策)
    """

    def __init__(self, actuator=None, voice_fn=None, alert_fn=None,
                 air_cushion=None, cloud_server=None, api_key=None):
        """
        actuator: BedActuator 实例 (推杆控制)
        voice_fn: 语音提醒回调 fn(text)
        alert_fn: 告警回调 fn(level, message, metric, value)
        air_cushion: AirCushionController 实例 (气囊控制)
        cloud_server: 云端API地址
        api_key: 设备API密钥
        """
        self.actuator = actuator
        self.voice_fn = voice_fn
        self.alert_fn = alert_fn
        self.air_cushion = air_cushion

        self.rules = []
        self._running = False
        self._thread = None
        self._context = {}
        self._lock = threading.Lock()
        self._action_log = []

        # LLM 决策 Agent (原有单Agent, 作为 Coordinator 不可用时的回退)
        self.llm_agent = None
        if cloud_server and api_key:
            self.llm_agent = LLMDecisionAgent(cloud_server, api_key)

        # ─── Multi-Agent Swarm: NursingCoordinator (v4.0 新增) ───
        # 如果 coordinator 已从外部注入 (由 mqtt_bridge.init_decision_engine 创建),
        # 则 evaluate() 优先使用 coordinator; 否则回退到单 llm_agent
        self.coordinator = None    # 由外部注入: init_decision_engine()
        self.patient_memory = None # 由外部注入

        # 注册传统规则 (安全兜底)
        self._register_default_rules()
        log.info("✅ DecisionEngine v4.0 initialized (%d rules, LLM=%s, AirCushion=%s)",
                 len(self.rules),
                 "enabled" if self.llm_agent else "disabled",
                 "enabled" if self.air_cushion else "disabled")

    def _register_default_rules(self):
        """注册默认决策规则集 (传统规则, 安全兜底)"""

        # ── 1. 血氧过低 → 自动抬高靠背 + 语音提醒 ──
        self.rules.append(DecisionRule(
            name="低血氧自动抬高靠背",
            condition_fn=lambda ctx: ctx.get('blood_oxygen') and ctx['blood_oxygen'] < 90,
            action_fn=self._action_raise_for_spo2,
            cooldown=600,
            priority=1
        ))

        # ── 2. 心率异常 → 语音提醒 + 告警 ──
        self.rules.append(DecisionRule(
            name="心率异常告警",
            condition_fn=lambda ctx: ctx.get('heart_rate') and (
                ctx['heart_rate'] > 120 or ctx['heart_rate'] < 45
            ),
            action_fn=self._action_heart_rate_alert,
            cooldown=300,
            priority=1
        ))

        # ── 3. 高体温 → 语音提醒 ──
        self.rules.append(DecisionRule(
            name="发热提醒",
            condition_fn=lambda ctx: ctx.get('temperature') and ctx['temperature'] > 38.0,
            action_fn=self._action_fever_alert,
            cooldown=900,
            priority=2
        ))

        # ── 4. 受压超时 → 气囊减压 + 推杆微调 + 语音翻身提醒 ──
        self.rules.append(DecisionRule(
            name="受压超时翻身提醒",
            condition_fn=lambda ctx: ctx.get('ulcer_risk_level') in ('medium', 'high'),
            action_fn=self._action_pressure_relief,
            cooldown=1800,
            priority=1
        ))

        # ── 5. 跌倒/离床检测 → 紧急告警 ──
        self.rules.append(DecisionRule(
            name="跌倒离床告警",
            condition_fn=lambda ctx: ctx.get('fall_detected') is True or (
                ctx.get('posture') == 'empty' and ctx.get('was_occupied', False)
            ),
            action_fn=self._action_fall_alert,
            cooldown=120,
            priority=0
        ))

        # ── 6. 多模态融合确认跌倒 ──
        self.rules.append(DecisionRule(
            name="多模态跌倒融合确认",
            condition_fn=lambda ctx: (
                ctx.get('pressure_empty', False) and ctx.get('vision_fall', False)
            ),
            action_fn=self._action_multimodal_fall,
            cooldown=60,
            priority=0
        ))

        # ── 7. 长时间未翻身 → 智能建议 ──
        self.rules.append(DecisionRule(
            name="长时间体位不变建议",
            condition_fn=lambda ctx: (
                ctx.get('posture_unchanged_minutes', 0) > 90 and
                ctx.get('posture') not in ('empty', 'sitting')
            ),
            action_fn=self._action_posture_suggestion,
            cooldown=3600,
            priority=3
        ))

        # ── 8. 血压异常 → 语音提醒 ──
        self.rules.append(DecisionRule(
            name="血压异常提醒",
            condition_fn=lambda ctx: ctx.get('blood_pressure_sys') and (
                ctx['blood_pressure_sys'] > 160 or ctx['blood_pressure_sys'] < 80
            ),
            action_fn=self._action_bp_alert,
            cooldown=600,
            priority=2
        ))

        # ── 9. [创新] 预测性受压预防 → 提前干预 ──
        self.rules.append(DecisionRule(
            name="预测性受压预防",
            condition_fn=lambda ctx: ctx.get('predicted_risk', 0) > 0.30,
            action_fn=self._action_predictive_relief,
            cooldown=600,
            priority=2
        ))

    # ═══════════════════════════════════════
    #  决策动作实现
    # ═══════════════════════════════════════

    def _action_raise_for_spo2(self, ctx):
        log.info("🫁 Action: 血氧%.0f%%过低, 自动抬高靠背", ctx.get('blood_oxygen', 0))
        if self.actuator:
            self.actuator.raise_bed(duration=1.5, speed=60)
        self._voice_remind("检测到您的血氧偏低,已为您自动抬高靠背,帮助呼吸。请放松深呼吸。")
        self._send_alert('warning', f"血氧{ctx['blood_oxygen']:.0f}%偏低,已自动抬高靠背", 'blood_oxygen', ctx['blood_oxygen'])
        return {"action": "raise_bed", "reason": "low_spo2", "value": ctx['blood_oxygen']}

    def _action_heart_rate_alert(self, ctx):
        hr = ctx['heart_rate']
        status = "过快" if hr > 120 else "过慢"
        log.info("❤️ Action: 心率%.0f bpm %s", hr, status)
        self._voice_remind(f"提醒您,检测到心率{hr:.0f},有些{status},请注意休息,必要时呼叫护士。")
        level = 'critical' if (hr > 150 or hr < 40) else 'warning'
        self._send_alert(level, f"心率{hr:.0f}bpm{status}", 'heart_rate', hr)
        return {"action": "alert", "reason": "abnormal_hr", "value": hr}

    def _action_fever_alert(self, ctx):
        temp = ctx['temperature']
        log.info("🌡️ Action: 体温%.1f°C偏高", temp)
        self._voice_remind(f"检测到体温{temp:.1f}度,有些偏高,请多喝水休息,如果不舒服请告诉护士。")
        self._send_alert('warning', f"体温{temp:.1f}°C偏高", 'temperature', temp)
        return {"action": "alert", "reason": "fever", "value": temp}

    def _action_pressure_relief(self, ctx):
        """受压超时 → 气囊减压循环 + 推杆微调 + 语音翻身提醒"""
        level = ctx.get('ulcer_risk_level', 'medium')
        log.info("🛡️ Action: 受压风险[%s], 执行减压操作", level)

        # 气囊减压 (创新点: 自动充放气)
        if self.air_cushion:
            self.air_cushion.pressure_relief_cycle()
            log.info("  → 气囊减压循环已启动")

        # 推杆微调
        if self.actuator:
            self.actuator.raise_bed(duration=1.0, speed=50)
            threading.Timer(3.0, lambda: self.actuator.lower_bed(duration=1.0, speed=50)).start()

        if level == 'high':
            self._voice_remind("您已经在同一位置躺了很久了,为了预防受压,请尝试翻个身,我已经启动了气囊减压并调整了靠背角度。")
        else:
            self._voice_remind("温馨提醒,建议您适当变换一下体位,预防受压。")

        self._send_alert('warning' if level == 'high' else 'info',
                        f"受压风险[{level}],已执行自动减压(气囊+推杆)", 'pressure_ulcer', 0)
        return {"action": "pressure_relief", "reason": "ulcer_risk", "level": level,
                "air_cushion": self.air_cushion is not None}

    def _action_fall_alert(self, ctx):
        log.info("🚨 Action: 检测到跌倒/离床!")
        self._voice_remind("注意安全!检测到您可能离开了病床,请小心。已通知护士站。")
        self._send_alert('critical', "检测到患者跌倒或离床,请立即查看!", 'fall_detection', 1)
        return {"action": "fall_alert", "reason": "fall_detected"}

    def _action_multimodal_fall(self, ctx):
        log.info("🚨🚨 Action: 多模态融合确认跌倒! (压力+视觉)")
        self._voice_remind("紧急情况!多重传感器确认您已离开病床,护士正在赶来,请保持冷静!")
        self._send_alert('critical', "多模态融合确认: 患者跌倒! 压力矩阵+视觉同时检测到异常", 'multimodal_fall', 1)
        return {"action": "multimodal_fall_alert", "reason": "confirmed_fall", "confidence": "high"}

    def _action_posture_suggestion(self, ctx):
        mins = ctx.get('posture_unchanged_minutes', 0)
        log.info("💤 Action: 体位不变%d分钟, 建议调整", mins)
        self._voice_remind(f"您已经保持同一姿势{mins:.0f}分钟了,适当翻身对身体更好哦。")
        return {"action": "posture_suggestion", "minutes": mins}

    def _action_bp_alert(self, ctx):
        bp_sys = ctx['blood_pressure_sys']
        bp_dia = ctx.get('blood_pressure_dia', 0)
        status = "偏高" if bp_sys > 160 else "偏低"
        log.info("🩸 Action: 血压%d/%d %s", bp_sys, bp_dia, status)
        self._voice_remind(f"检测到血压{bp_sys}/{bp_dia},{status},请注意休息,必要时联系医生。")
        self._send_alert('warning', f"血压{bp_sys}/{bp_dia}mmHg{status}", 'blood_pressure', bp_sys)
        return {"action": "alert", "reason": "abnormal_bp", "value": bp_sys}

    def _action_predictive_relief(self, ctx):
        """[创新] 预测性受压预防 → 风险概率分级干预"""
        risk = ctx.get('predicted_risk', 0)
        risk_level = ctx.get('predicted_risk_level', 'info')

        log.info("🔮 Action: 预测性护理, 风险=%.0f%% [%s]", risk * 100, risk_level)

        if risk_level == 'critical' and self.air_cushion:
            # 高风险: 气囊减压 + 告警
            self.air_cushion.pressure_relief_cycle()
            self._voice_remind("根据数据分析,预测到您可能即将出现受压风险,已自动启动气囊减压。")
            self._send_alert('warning', f"预测性护理: 30min受压风险{risk:.0%},已启动气囊减压",
                           'predictive_risk', risk)

        elif risk_level == 'warning':
            # 中风险: 语音建议
            self._voice_remind("温馨提醒,根据数据分析,建议您适当变换一下体位,预防受压。")
            self._send_alert('info', f"预测性护理: 30min受压风险{risk:.0%},建议翻身",
                           'predictive_risk', risk)

        else:
            # 低风险: 静默记录
            log.info("  → 低风险提示已记录 (risk=%.0f%%)", risk * 100)

        return {"action": "predictive_relief", "risk": risk, "level": risk_level,
                "air_cushion_activated": risk_level == 'critical' and self.air_cushion is not None}

    # ═══════════════════════════════════════
    #  LLM 决策执行
    # ═══════════════════════════════════════

    def _execute_llm_decision(self, decision):
        """执行 LLM Agent 的决策 (经过安全校验后)"""
        action = decision.get("action", "no_action")
        params = decision.get("params", {})
        reasoning = decision.get("reasoning", "")

        log.info("🧠 LLM Decision: %s (confidence=%.0f%%, reasoning=%s)",
                 action, decision.get('confidence', 0) * 100, reasoning)

        # ─── L3: 高危动作需人工审核 ───
        if action == "alert_critical":
            # 不直接执行, 而是标记为待审核
            log.info("  → L3: Critical action pending human review")
            self._send_alert('warning',
                           f"[AI建议] {params.get('text', '需要紧急关注')} (推理: {reasoning})",
                           'ai_decision', 0)
            return {"action": action, "status": "pending_review", "reasoning": reasoning}

        # 执行动作
        if action == "raise_bed" and self.actuator:
            duration = params.get("duration", 1.5)
            speed = params.get("speed", 60)
            self.actuator.raise_bed(duration=duration, speed=speed)
            self._voice_remind(params.get("text", "已为您调整靠背角度。"))

        elif action == "lower_bed" and self.actuator:
            duration = params.get("duration", 1.5)
            speed = params.get("speed", 60)
            self.actuator.lower_bed(duration=duration, speed=speed)

        elif action == "voice_remind":
            text = params.get("text", "")
            if text:
                self._voice_remind(text)

        elif action == "alert_info":
            self._send_alert('info', params.get("text", reasoning), 'ai_decision', 0)

        elif action == "alert_warning":
            self._send_alert('warning', params.get("text", reasoning), 'ai_decision', 0)

        elif action == "air_inflate" and self.air_cushion:
            zone = params.get("zone", "both")
            duration = params.get("duration", 5.0)
            self.air_cushion.inflate(zone=zone, duration=duration)

        elif action == "air_deflate" and self.air_cushion:
            zone = params.get("zone", "both")
            self.air_cushion.deflate(zone=zone)

        elif action == "air_relief_cycle" and self.air_cushion:
            self.air_cushion.pressure_relief_cycle()

        elif action == "no_action":
            pass

        return {"action": action, "status": "executed", "reasoning": reasoning}

    # ═══════════════════════════════════════
    #  工具方法
    # ═══════════════════════════════════════

    def _voice_remind(self, text):
        if self.voice_fn:
            try:
                self.voice_fn(text)
            except Exception as e:
                log.error("Voice remind failed: %s", e)

    def _send_alert(self, level, message, metric, value):
        if self.alert_fn:
            try:
                self.alert_fn(level, message, metric, value)
            except Exception as e:
                log.error("Alert send failed: %s", e)

    # ═══════════════════════════════════════
    #  主循环与上下文更新
    # ═══════════════════════════════════════

    def update_context(self, **kwargs):
        """更新决策上下文 (由mqtt_bridge等模块调用)"""
        with self._lock:
            self._context.update(kwargs)
            self._context['last_context_update'] = time.time()

    def evaluate(self):
        """
        评估所有规则 + LLM Agent, 执行匹配的动作

        执行顺序:
          1. 传统规则 (即时响应, 安全兜底)
          2. LLM Agent (上下文推理, 可补充/覆盖低优先级规则)
        """
        with self._lock:
            ctx = self._context.copy()

        triggered = []

        # ── Step 1: 传统规则评估 ──
        for rule in sorted(self.rules, key=lambda r: r.priority):
            try:
                if rule.can_trigger() and rule.condition(ctx):
                    result = rule.trigger(ctx)
                    triggered.append({
                        "rule": rule.name,
                        "time": time.strftime("%H:%M:%S"),
                        "result": result,
                        "source": "rule"
                    })
                    log.info("✅ Rule triggered: %s", rule.name)
            except Exception as e:
                log.error("Rule '%s' error: %s", rule.name, e)

        # ── Step 2: Multi-Agent Swarm 评估 (v4.0: Coordinator优先, LLM回退) ──
        has_critical = any(t.get('result', {}).get('action') in ('fall_alert', 'multimodal_fall_alert')
                         for t in triggered)

        if not has_critical:
            if self.coordinator:
                # ✨ v4.0 路径: NursingCoordinator 多Agent协作
                try:
                    coord_result = self.coordinator.coordinate(ctx)
                    if coord_result and coord_result.get('final_action'):
                        final = coord_result['final_action']
                        if final.get('action') != 'no_action':
                            exec_result = self._execute_llm_decision(final)
                            triggered.append({
                                "rule": f"Coordinator[{final.get('agent_name', '?')}]",
                                "time": time.strftime("%H:%M:%S"),
                                "result": exec_result,
                                "source": "coordinator",
                                "agents_consulted": coord_result.get('agents_consulted', []),
                                "reasoning": final.get('reasoning', '')
                            })
                            log.info("🏥 Coordinator action executed: %s (by %s)",
                                     exec_result.get('action'), final.get('agent_name'))
                except Exception as e:
                    log.error("Coordinator evaluation error: %s", e)

            elif self.llm_agent and self.llm_agent.should_query():
                # 🔄 回退路径: 原有单LLM Agent
                try:
                    llm_decision = self.llm_agent.query(ctx)
                    if llm_decision and llm_decision.get('action') != 'no_action':
                        result = self._execute_llm_decision(llm_decision)
                        triggered.append({
                            "rule": "LLM_Agent",
                            "time": time.strftime("%H:%M:%S"),
                            "result": result,
                            "source": "llm",
                            "reasoning": llm_decision.get('reasoning', '')
                        })
                        log.info("🧠 LLM action executed: %s", result.get('action'))
                except Exception as e:
                    log.error("LLM evaluation error: %s", e)

        if triggered:
            self._action_log.extend(triggered)
            self._action_log = self._action_log[-100:]

        return triggered

    def start(self, interval=10):
        """启动决策循环"""
        if self._running:
            return
        self._running = True

        def loop():
            log.info("Decision loop started (interval=%ds)", interval)
            while self._running:
                self.evaluate()
                time.sleep(interval)
            log.info("Decision loop stopped")

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def get_action_log(self):
        return list(self._action_log)

    def get_status(self):
        status = {
            "running": self._running,
            "rules_count": len(self.rules),
            "llm_enabled": self.llm_agent is not None,
            "air_cushion_enabled": self.air_cushion is not None,
            "context_keys": list(self._context.keys()),
            "last_update": self._context.get('last_context_update', 0),
            "action_log_count": len(self._action_log),
            "recent_actions": self._action_log[-5:] if self._action_log else [],
        }
        # Multi-Agent Swarm 状态
        if hasattr(self, 'coordinator') and self.coordinator:
            status["coordinator_enabled"] = True
            status["swarm_status"] = self.coordinator.get_status()
        else:
            status["coordinator_enabled"] = False
        return status


# ═══════════════════════════════════════════════════════════════════════════
#
#                    Multi-Agent Nursing Swarm v4.0
#
#  以下为新增模块, 完全不修改上方任何已有类 (DecisionRule, LLMDecisionAgent, DecisionEngine)
#  借鉴 OpenHarness 核心范式:
#    - AgentDefinition      → agent_definitions.py
#    - TeammateMailbox       → agent_mailbox.py
#    - CoordinatorMode       → NursingCoordinator (本文件)
#    - PermissionChecker     → ToolPermissionChecker (本文件)
#    - Memory               → patient_memory.py
#
# ═══════════════════════════════════════════════════════════════════════════


class ToolPermissionChecker:
    """
    Agent 工具权限沙箱 (对标 OpenHarness permissions/checker.py PermissionChecker)

    每个专科Agent只能使用被授权的动作子集:
      - VitalsAgent: raise_bed, lower_bed, voice_remind, alert_*
      - PressureAgent: air_*, raise_bed, voice_remind, alert_*
      - EmergencyAgent: alert_critical, alert_warning, voice_remind
      - CompanionAgent: voice_remind, alert_info

    OpenHarness 映射:
      PermissionChecker.evaluate(tool_name, is_read_only, file_path)
        → ToolPermissionChecker.check(agent_name, action)
      PermissionDecision(allowed, requires_confirmation, reason)
        → 相同结构
      SENSITIVE_PATH_PATTERNS → critical_actions (需二次确认的高危动作)
    """

    # 高危动作 (对标 OpenHarness SENSITIVE_PATH_PATTERNS — 永远需要确认)
    CRITICAL_ACTIONS = {"alert_critical"}

    def __init__(self, agent_definitions=None):
        """
        agent_definitions: dict[agent_name → NursingAgentDefinition]
        """
        self._permissions = {}
        if agent_definitions:
            for agent_def in agent_definitions:
                self._permissions[agent_def.name] = agent_def.allowed_actions

    def check(self, agent_name, action):
        """
        检查Agent是否有权执行某动作

        对标 OpenHarness PermissionChecker.evaluate():
          - 白名单校验 (allowed_actions)
          - 高危动作标记 (requires_confirmation)
          - 全局动作白名单 (ALLOWED_ACTIONS)

        返回: {"allowed": bool, "requires_confirmation": bool, "reason": str}
        """
        # 全局白名单校验 (L1层)
        if action not in ALLOWED_ACTIONS:
            return {
                "allowed": False,
                "requires_confirmation": False,
                "reason": f"Action '{action}' not in global ALLOWED_ACTIONS"
            }

        # Agent 专属权限校验 (L2层: 对标 OpenHarness Agent.tools)
        allowed_actions = self._permissions.get(agent_name, set())
        if allowed_actions and action not in allowed_actions:
            return {
                "allowed": False,
                "requires_confirmation": False,
                "reason": f"Agent '{agent_name}' not authorized for '{action}'"
            }

        # 高危动作检查 (L3层: 对标 OpenHarness SENSITIVE_PATH_PATTERNS)
        if action in self.CRITICAL_ACTIONS:
            return {
                "allowed": True,
                "requires_confirmation": True,
                "reason": f"Critical action '{action}' requires coordinator confirmation"
            }

        return {"allowed": True, "requires_confirmation": False, "reason": "OK"}


class SpecialistLLMAgent:
    """
    专科LLM Agent (对标 OpenHarness AgentDefinition + InProcessBackend)

    与原有 LLMDecisionAgent 的关系:
      - LLMDecisionAgent: 单一Agent, 固定SYSTEM_PROMPT, 所有任务通吃
      - SpecialistLLMAgent: 专科Agent, 从AgentDefinition加载专属prompt和tools
                            继承 LLMDecisionAgent 的 build_prompt/_parse_response 逻辑

    对标 OpenHarness:
      - AgentDefinition.system_prompt → self.definition.system_prompt
      - AgentDefinition.tools         → self.definition.allowed_actions
      - start_in_process_teammate()   → self.query()
      - TeammateContext.tool_use_count → self._stats["query_count"]
    """

    def __init__(self, definition, cloud_server, api_key):
        """
        definition: NursingAgentDefinition 实例
        cloud_server: 云端API地址
        api_key: 设备API密钥
        """
        self.definition = definition
        self.cloud_server = cloud_server
        self.api_key = api_key
        self._last_query_time = 0
        self._llm_timeout = 40
        self._decision_history = []
        self._stats = {"query_count": 0, "success_count": 0, "error_count": 0}

        log.info("  🔧 SpecialistAgent[%s] initialized (%s)",
                 definition.name, definition.display_name)

    def should_query(self):
        """检查是否应查询 (使用Agent专属间隔)"""
        return time.time() - self._last_query_time > self.definition.query_interval

    def build_prompt(self, context, patient_info=None, memory_prompt=""):
        """
        构建专科Agent的prompt (复用LLMDecisionAgent.build_prompt逻辑, 增加记忆注入)
        """
        prompt_parts = []

        # 患者信息
        if patient_info:
            prompt_parts.append(f"患者: {patient_info.get('name', '未知')}, "
                               f"{patient_info.get('age', '?')}岁, "
                               f"病种: {patient_info.get('disease_type', '通用')}")

        # 实时体征 (只提取该Agent关注的trigger相关数据)
        vitals = []
        for key in self.definition.triggers:
            val = context.get(key)
            if val is not None:
                label = {
                    "heart_rate": "心率", "blood_oxygen": "血氧",
                    "temperature": "体温", "blood_pressure_sys": "收缩压",
                    "ulcer_risk_level": "受压风险", "posture_unchanged_minutes": "姿态不变时间",
                    "predicted_risk": "预测风险", "posture": "姿态",
                    "fall_detected": "跌倒检测", "pressure_empty": "压力矩阵空",
                    "vision_fall": "视觉跌倒", "emotion_score": "情绪分",
                }.get(key, key)
                vitals.append(f"{label}={val}")
        if vitals:
            prompt_parts.append("关注指标: " + ", ".join(vitals))

        # 完整体征概览
        all_vitals = []
        if context.get('heart_rate'):
            all_vitals.append(f"心率{context['heart_rate']}bpm")
        if context.get('blood_oxygen'):
            all_vitals.append(f"血氧{context['blood_oxygen']}%")
        if context.get('temperature'):
            all_vitals.append(f"体温{context['temperature']}°C")
        if context.get('blood_pressure_sys'):
            all_vitals.append(f"血压{context['blood_pressure_sys']}/{context.get('blood_pressure_dia', '?')}mmHg")
        if all_vitals:
            prompt_parts.append("全部体征: " + ", ".join(all_vitals))

        # 姿态信息
        if context.get('posture'):
            mins = context.get('posture_unchanged_minutes', 0)
            prompt_parts.append(f"当前姿态: {context['posture']} (持续{mins:.0f}分钟)")

        # 预测数据
        if context.get('predicted_risk') is not None:
            prompt_parts.append(f"30min受压风险预测: {context['predicted_risk']:.0%}")

        # 趋势
        if context.get('vitals_trend'):
            trend = context['vitals_trend']
            trend_parts = []
            if trend.get('hr_trend'):
                trend_parts.append(f"心率趋势: {trend['hr_trend']}")
            if trend.get('spo2_trend'):
                trend_parts.append(f"血氧趋势: {trend['spo2_trend']}")
            if trend_parts:
                prompt_parts.append("趋势: " + ", ".join(trend_parts))

        # 最近动作
        if self._decision_history:
            last = self._decision_history[-1]
            prompt_parts.append(f"本Agent最近动作: {last.get('action')} ({last.get('time', '?')})")

        # 患者记忆注入 (核心创新: 对标 OpenHarness load_memory_prompt)
        if memory_prompt:
            prompt_parts.append(memory_prompt)

        return "\n".join(prompt_parts)

    def query(self, context, patient_info=None, memory_prompt=""):
        """
        查询专科LLM (对标 OpenHarness start_in_process_teammate)

        与 LLMDecisionAgent.query() 的区别:
          - 使用 Agent 专属 system_prompt (而非全局)
          - 注入患者记忆
          - 使用 Agent 专属查询间隔
          - 返回带 agent_name 标记的决策
        """
        if not self.should_query():
            return None

        has_relevant = any(context.get(k) is not None for k in self.definition.triggers)
        if not has_relevant:
            return None

        prompt = self.build_prompt(context, patient_info, memory_prompt)
        self._last_query_time = time.time()
        self._stats["query_count"] += 1

        try:
            resp = requests.post(
                f"{self.cloud_server}/api/agents/consult",
                json={
                    "agent_name": self.definition.name,
                    "question": prompt,
                    "system_prompt": self.definition.system_prompt
                },
                headers={"X-API-Key": self.api_key},
                timeout=self._llm_timeout
            )

            if resp.status_code != 200:
                log.warning("[%s] LLM query failed: HTTP %d",
                           self.definition.name, resp.status_code)
                self._stats["error_count"] += 1
                return None

            ai_text = resp.json().get("response", "")
            decision = self._parse_response(ai_text)

            if decision:
                decision["source"] = "specialist_llm"
                decision["agent_name"] = self.definition.name
                decision["time"] = time.strftime("%H:%M:%S")
                self._decision_history.append(decision)
                self._decision_history = self._decision_history[-20:]
                self._stats["success_count"] += 1
                # 成功后调整超时
                self._llm_timeout = 15
                log.info("[%s] ✅ Decision: %s (confidence=%.0f%%)",
                         self.definition.name, decision.get('action'),
                         decision.get('confidence', 0) * 100)

            return decision

        except requests.exceptions.Timeout:
            self._llm_timeout = min(self._llm_timeout * 1.5, 120)
            self._stats["error_count"] += 1
            log.warning("[%s] Timeout, backing off to %.0fs",
                       self.definition.name, self._llm_timeout)
            return None
        except Exception as e:
            self._stats["error_count"] += 1
            log.error("[%s] Query error: %s", self.definition.name, e)
            return None

    def _parse_response(self, text):
        """解析LLM JSON响应 (复用 LLMDecisionAgent._parse_response 逻辑 + Agent权限校验)"""
        import re as _re
        try:
            match = _re.search(r'\{[\s\S]*\}', text)
            if not match:
                return None
            json_match = json.loads(match.group(0))
        except (json.JSONDecodeError, Exception):
            log.warning("[%s] Parse failed: %s", self.definition.name, text[:100])
            return None

        action = json_match.get("action", "no_action")
        params = json_match.get("params", {})
        reasoning = json_match.get("reasoning", "")
        confidence = json_match.get("confidence", 0.5)
        urgency = json_match.get("urgency", "low")

        # L1: 全局白名单
        if action not in ALLOWED_ACTIONS:
            log.warning("[%s] 🚫 Blocked invalid action '%s'",
                       self.definition.name, action)
            return None

        # L1.5: Agent专属权限检查 (对标 OpenHarness Agent.tools)
        if self.definition.allowed_actions and action not in self.definition.allowed_actions:
            log.warning("[%s] 🚫 Action '%s' not in agent tools: %s",
                       self.definition.name, action,
                       list(self.definition.allowed_actions))
            return None

        # L2: 参数边界
        if action in PARAM_BOUNDS:
            bounds = PARAM_BOUNDS[action]
            if "max_duration" in bounds and params.get("duration"):
                params["duration"] = min(float(params["duration"]), bounds["max_duration"])
            if "max_speed" in bounds and params.get("speed"):
                params["speed"] = min(int(params["speed"]), bounds["max_speed"])
            if "max_length" in bounds and params.get("text"):
                params["text"] = str(params["text"])[:bounds["max_length"]]

        return {
            "action": action,
            "params": params,
            "reasoning": reasoning,
            "confidence": confidence,
            "urgency": urgency,
        }

    def get_stats(self):
        return dict(self._stats)


class NursingCoordinator:
    """
    护理协调中枢 (对标 OpenHarness coordinator/coordinator_mode.py CoordinatorMode)

    核心职责:
      1. 分诊路由 (triage) — 根据上下文决定哪些Agent应该被激活
      2. 并行查询 — 同时查询多个专科Agent
      3. 冲突消解 — 多Agent给出矛盾建议时的仲裁
      4. 结果聚合 — 合并多Agent决策为最终执行方案

    OpenHarness 映射:
      CoordinatorMode.get_coordinator_system_prompt() → NursingCoordinator.COORDINATOR_PROMPT
      "spawn workers"                                 → triage() + parallel query
      "synthesize results"                           → resolve_conflicts() + aggregate()
      TaskNotification                               → decision response messages
      AgentToolName                                  → SpecialistLLMAgent.definition.name

    与 DecisionEngine 的关系:
      - DecisionEngine 仍是主引擎, 拥有 actuator/voice/alert 回调
      - NursingCoordinator 替代 LLMDecisionAgent, 作为 L1 层的决策源
      - DecisionEngine.evaluate() 调用 coordinator.coordinate()
    """

    def __init__(self, cloud_server, api_key, patient_memory=None, mailbox=None):
        """
        cloud_server: 云端API地址
        api_key: 设备API密钥
        patient_memory: PatientMemory 实例 (可选)
        mailbox: AgentMailbox 实例 (可选)
        """
        self.cloud_server = cloud_server
        self.api_key = api_key
        self.patient_memory = patient_memory
        self.mailbox = mailbox

        # 加载Agent定义并创建SpecialistAgent实例
        self.agents = {}        # name → SpecialistLLMAgent
        self.definitions = {}   # name → NursingAgentDefinition
        self.permission_checker = None

        self._init_agents()
        self._coordination_count = 0
        self._last_coordination = 0

        log.info("🏥 NursingCoordinator initialized with %d specialist agents",
                 len(self.agents))

    def _init_agents(self):
        """初始化所有专科Agent (对标 OpenHarness BackendRegistry._register_defaults)"""
        try:
            from agent_definitions import get_builtin_nursing_agents
            agent_defs = get_builtin_nursing_agents()
        except ImportError:
            log.warning("agent_definitions not available, coordinator running without specialists")
            return

        for agent_def in agent_defs:
            self.definitions[agent_def.name] = agent_def
            self.agents[agent_def.name] = SpecialistLLMAgent(
                definition=agent_def,
                cloud_server=self.cloud_server,
                api_key=self.api_key,
            )

        # 初始化权限检查器
        self.permission_checker = ToolPermissionChecker(agent_defs)

        log.info("  📋 Registered agents: %s",
                 ", ".join(f"{d.icon}{d.name}" for d in agent_defs))

    def triage(self, context):
        """
        分诊路由: 决定哪些Agent应被激活

        对标 OpenHarness Coordinator 的 "spawn workers" 逻辑:
          - Coordinator 不直接做决策, 而是分派给合适的Worker
          - 这里根据 context 中的数据匹配 Agent.triggers

        返回: 按优先级排序的 Agent 名称列表
        """
        try:
            from agent_definitions import get_agents_for_triggers
            matched_defs = get_agents_for_triggers(context)
            return [d.name for d in matched_defs if d.name in self.agents]
        except ImportError:
            return list(self.agents.keys())

    def coordinate(self, context, patient_info=None):
        """
        多Agent协作决策 (核心方法)

        对标 OpenHarness Coordinator 的任务流:
          1. Research (triage) — 确定哪些Agent需要参与
          2. Execute (parallel query) — 并行查询被激活的Agent
          3. Synthesize (resolve + aggregate) — 合并结果

        返回: {
            "decisions": [{agent_name, action, params, reasoning, ...}, ...],
            "final_action": {action, params, reasoning, source},
            "agents_consulted": [str],
            "coordination_id": str
        }
        """
        # 获取患者记忆注入 (对标 OpenHarness load_memory_prompt)
        memory_prompt = ""
        if self.patient_memory:
            memory_prompt = self.patient_memory.get_context_for_prompt()

        # Step 1: 分诊路由
        active_agents = self.triage(context)
        if not active_agents:
            return None

        # Step 2: 查询被激活的Agent (当前串行, 未来可并行)
        decisions = []
        for agent_name in active_agents:
            agent = self.agents.get(agent_name)
            if not agent:
                continue

            try:
                decision = agent.query(context, patient_info, memory_prompt)
                if decision and decision.get("action") != "no_action":
                    # 权限检查 (对标 OpenHarness PermissionChecker.evaluate)
                    if self.permission_checker:
                        perm = self.permission_checker.check(agent_name, decision["action"])
                        if not perm["allowed"]:
                            log.warning("[Coordinator] 🚫 %s blocked: %s",
                                       agent_name, perm["reason"])
                            continue
                        decision["requires_confirmation"] = perm["requires_confirmation"]

                    decisions.append(decision)

                    # 发送决策到 Mailbox (可审计, 对标 OpenHarness mailbox.write)
                    if self.mailbox:
                        try:
                            from agent_mailbox import create_decision_response
                            msg = create_decision_response(agent_name, decision)
                            self.mailbox.send(msg)
                        except ImportError:
                            pass

            except Exception as e:
                log.error("[Coordinator] Agent '%s' error: %s", agent_name, e)

        if not decisions:
            return None

        # Step 3: 冲突消解 + 结果聚合
        final = self.resolve_conflicts(decisions)

        # 记录到患者记忆
        if self.patient_memory and final:
            self.patient_memory.record_decision(final)

        self._coordination_count += 1
        self._last_coordination = time.time()

        result = {
            "decisions": decisions,
            "final_action": final,
            "agents_consulted": active_agents,
            "coordination_id": f"coord_{self._coordination_count}",
        }

        log.info("🏥 Coordination #%d: %d agents → final=%s",
                 self._coordination_count,
                 len(active_agents),
                 final.get("action") if final else "none")

        return result

    def resolve_conflicts(self, decisions):
        """
        冲突消解: 多Agent给出不同建议时的仲裁

        对标 OpenHarness Coordinator "synthesize results" 逻辑:
          - Coordinator 读取 worker 结果, 综合判断

        仲裁策略:
          1. 紧急优先: alert_critical > alert_warning > 其他
          2. 高置信度优先
          3. 高优先级Agent优先 (emergency > vitals > pressure > companion)
        """
        if not decisions:
            return None

        if len(decisions) == 1:
            return decisions[0]

        # 按紧急程度分组
        urgency_order = {"high": 0, "medium": 1, "low": 2}
        action_priority = {
            "alert_critical": 0, "alert_warning": 1,
            "air_relief_cycle": 2, "air_inflate": 3,
            "raise_bed": 4, "lower_bed": 5,
            "voice_remind": 6, "alert_info": 7,
            "no_action": 99
        }

        def decision_score(d):
            urgency_score = urgency_order.get(d.get("urgency", "low"), 2)
            action_score = action_priority.get(d.get("action", "no_action"), 50)
            confidence = d.get("confidence", 0.5)
            return (urgency_score, action_score, -confidence)

        sorted_decisions = sorted(decisions, key=decision_score)
        winner = sorted_decisions[0]

        # 记录冲突消解过程
        if len(decisions) > 1:
            log.info("  ⚖️ Conflict resolved: %d decisions, winner=%s[%s] (urgency=%s, conf=%.0f%%)",
                     len(decisions),
                     winner.get("agent_name", "?"),
                     winner.get("action"),
                     winner.get("urgency", "?"),
                     winner.get("confidence", 0) * 100)

        return winner

    def get_status(self):
        """获取Coordinator状态 (供API查询)"""
        agent_stats = {}
        for name, agent in self.agents.items():
            defn = self.definitions.get(name)
            agent_stats[name] = {
                "display_name": defn.display_name if defn else name,
                "icon": defn.icon if defn else "?",
                "priority": defn.priority if defn else 5,
                "color": defn.color if defn else "white",
                "stats": agent.get_stats(),
            }

        return {
            "agents": agent_stats,
            "agent_count": len(self.agents),
            "coordination_count": self._coordination_count,
            "last_coordination": self._last_coordination,
            "memory_enabled": self.patient_memory is not None,
            "mailbox_enabled": self.mailbox is not None,
        }

    def get_agent_for_voice(self, intent="chat"):
        """
        语音路由: 根据意图返回对应Agent定义

        供 voice_client.py 使用:
          - "chat" / "companion" → companion_agent
          - "control" / "nlc"   → None (走原有NLC路径)
          - "emergency"         → emergency_agent
        """
        intent_map = {
            "chat": "companion_agent",
            "companion": "companion_agent",
            "emergency": "emergency_agent",
        }
        agent_name = intent_map.get(intent)
        if agent_name and agent_name in self.definitions:
            return self.definitions[agent_name]
        return None

