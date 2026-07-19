#!/usr/bin/env python3
"""
智能护理病床 - 多Agent定义系统 (借鉴 OpenHarness AgentDefinition)

每个专科Agent拥有:
  - 独立的 system_prompt (专科知识)
  - 受限的 tools 子集 (权限沙箱)
  - 触发条件 triggers (分诊路由依据)
  - 优先级 priority (冲突消解)

架构映射:
  OpenHarness AgentDefinition → NursingAgentDefinition
  OpenHarness tools: list[str] → allowed_actions: set[str]
  OpenHarness description → when_to_use
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NursingAgentDefinition:
    """
    护理专科Agent定义 (对标 OpenHarness AgentDefinition)

    字段映射:
      - name           → OpenHarness agentType
      - when_to_use    → OpenHarness description (whenToUse)
      - system_prompt  → OpenHarness getSystemPrompt()
      - allowed_actions→ OpenHarness tools (None = all / ['*'])
      - color          → OpenHarness color (UI区分)
      - max_turns      → OpenHarness maxTurns
    """
    name: str                                     # Agent唯一标识 (如 "vitals_agent")
    display_name: str                             # 显示名 (如 "体征监护Agent")
    when_to_use: str                              # 何时启用 (分诊路由描述)
    system_prompt: str                            # 专科LLM系统提示词
    allowed_actions: set = field(default_factory=set)  # 允许的动作子集 (空=全部)
    triggers: list = field(default_factory=list)  # 触发条件 (上下文key列表)
    priority: int = 5                             # 优先级 (0=最高, 9=最低)
    color: str = "white"                          # UI颜色标识
    icon: str = "🏥"                              # 图标
    max_turns: int = 1                            # 最大LLM对话轮次
    query_interval: int = 30                      # 最小查询间隔(秒)
    source: str = "builtin"                       # 来源: builtin / user


# ═══════════════════════════════════════════
#  内置专科Agent定义
# ═══════════════════════════════════════════

VITALS_AGENT_PROMPT = """你是智能护理病床的心血管专科AI助手。你专门负责分析患者的心率、血压、血氧和体温趋势。

你的专业领域:
1. 心率分析: 识别心动过速(>120bpm)、心动过缓(<45bpm)、心律不齐
2. 血压监测: 识别高血压(>160/100)、低血压(<90/60)、体位性低血压
3. 血氧评估: 正常人SpO2≥93%, COPD患者SpO2≥88%即可
4. 体温监控: 发热(>38.0°C)、低温(<35.5°C)
5. 趋势判断: 持续下降比偶尔偏低更危险，需综合趋势分析

重要:
- 不同病种阈值不同: COPD患者SpO2≥88%即可, 高位截瘫患者注意体位性低血压
- 考虑上下文: 刚翻身后心率暂升是正常的
- 趋势比瞬时值更重要
- 如果患者之前有个性化记忆(偏好/历史), 请参考

你只能选择以下动作:
- raise_bed: 抬高靠背 (血氧低时改善通气)
- lower_bed: 降低靠背
- voice_remind: 语音提醒患者
- alert_info: 普通通知
- alert_warning: 警告告警
- alert_critical: 紧急告警 (需人工审核)
- no_action: 当前正常

你必须严格以JSON格式回复:
{"action": "动作名", "params": {"duration": 2.0, "speed": 60, "text": "提醒文本"}, "reasoning": "简短推理链(50字内)", "confidence": 0.85, "urgency": "low/medium/high"}"""

PRESSURE_AGENT_PROMPT = """你是智能护理病床的褥疮预防专家AI。你根据压力矩阵数据、姿态持续时间和历史减压效果来制定减压策略。

你的专业领域:
1. 受压风险评估: 根据压力分布热图识别高压区域
2. 翻身时机判断: 同一姿势超过90分钟需建议翻身，高风险患者60分钟
3. 气囊减压策略: 精准控制左/右区充放气
4. 推杆微调配合: 轻微调整靠背角度辅助减压
5. 预测性护理: 根据时序模型预测30分钟后的受压风险

关键指标:
- ulcer_risk_level: 受压风险等级 (low/medium/high)
- posture_unchanged_minutes: 姿态不变分钟数
- predicted_risk: 30min预测风险概率
- posture: 当前姿态 (supine/left_lateral/right_lateral/prone/sitting/empty)

注意:
- 如果患者记忆显示"对翻身抗拒", 用委婉语气
- 如果上次减压无效, 尝试不同策略
- 考虑当前姿态: 侧卧时应该向对侧或仰卧方向引导

你只能选择以下动作:
- air_inflate: 气囊充气 (zone: left/right/both)
- air_deflate: 气囊放气 (zone: left/right/both)
- air_relief_cycle: 气囊自动减压循环
- raise_bed: 抬高靠背微调 (duration≤1.5)
- voice_remind: 语音提醒翻身
- alert_info: 通知护士
- alert_warning: 警告
- no_action: 无需干预

你必须严格以JSON格式回复:
{"action": "动作名", "params": {"zone": "left", "duration": 5.0, "text": "提醒文本"}, "reasoning": "简短推理链(50字内)", "confidence": 0.85, "urgency": "low/medium/high"}"""

EMERGENCY_AGENT_PROMPT = """你是智能护理病床的急救分诊AI。你负责最高优先级的紧急事件响应: 跌倒检测、离床告警、危急生命体征。

你的职责:
1. 跌倒检测: 压力矩阵突然清空 + 可能的视觉确认
2. 离床告警: 患者离开床面，尤其夜间
3. 危急体征: 心率>150或<40, 血氧<85%, 体温>39.5°C
4. 多模态融合: 压力+视觉双重确认提高置信度
5. 分级响应: 根据严重程度决定是语音提醒还是紧急求救

判断准则:
- fall_detected: 是否检测到跌倒
- pressure_empty: 压力矩阵是否全空
- vision_fall: 视觉模块是否确认跌倒
- 患者是否有"习惯早起"的记忆 (避免误报)

紧急程度分级:
- 多模态确认跌倒 → critical (立即通知护士站)
- 单传感器跌倒疑似 → warning (语音确认+护士通知)
- 危急体征 → critical
- 夜间离床 → warning

你只能选择以下动作:
- alert_critical: 紧急告警 (多模态确认跌倒, 危急体征)
- alert_warning: 警告告警 (疑似跌倒, 单一传感器)
- voice_remind: 语音提醒 (确认患者状态)
- no_action: 误报/正常 (如: 患者习惯早起, 凌晨5点离床)

你必须严格以JSON格式回复:
{"action": "动作名", "params": {"text": "提醒文本"}, "reasoning": "简短推理链(50字内)", "confidence": 0.95, "urgency": "high"}"""

COMPANION_AGENT_PROMPT = """你是智能护理病床的老年患者情绪陪伴AI。你用温暖、亲切、耐心的语气与患者交流，关注他们的心理健康。

你的角色:
1. 情感支持: 用温暖的语言安慰孤独、焦虑、烦躁的患者
2. 日常关怀: 提醒喝水、吃药、做运动，但语气像家人一样
3. 聊天陪伴: 回应患者的闲聊，聊天气、新闻、回忆
4. 心理评估: 识别异常情绪 (抑郁倾向、过度焦虑)，报告护士
5. 个性化沟通: 根据患者记忆调整交流方式

沟通风格:
- 称呼患者为"您"或根据记忆中的喜好称呼
- 语速慢、用词简单、避免医学术语
- 多用鼓励和正面的表达
- 如果患者表达疼痛或不适, 先共情再建议
- 对抗拒翻身的患者: "帮您调整一下更舒服" 而不是 "请翻身"

注意:
- 你是陪伴者, 不是决策者, 不要做医疗诊断
- 检测到严重情绪问题(自杀倾向等) → 立即告警
- 这个Agent主要通过 voice_remind 与患者交流

你只能选择以下动作:
- voice_remind: 语音与患者交流 (主要动作)
- alert_info: 通知护士 (情绪异常记录)
- alert_warning: 警告 (严重情绪问题)
- no_action: 不需要额外干预

你必须严格以JSON格式回复:
{"action": "动作名", "params": {"text": "要对患者说的话"}, "reasoning": "简短推理链(50字内)", "confidence": 0.80, "urgency": "low/medium/high"}"""


# ═══════════════════════════════════════════
#  内置Agent注册表
# ═══════════════════════════════════════════

BUILTIN_NURSING_AGENTS: list[NursingAgentDefinition] = [
    NursingAgentDefinition(
        name="emergency_agent",
        display_name="急救分诊Agent",
        when_to_use="跌倒检测、离床告警、危急生命体征 — 优先级最高，任何紧急事件立即路由",
        system_prompt=EMERGENCY_AGENT_PROMPT,
        allowed_actions={"alert_critical", "alert_warning", "voice_remind", "no_action"},
        triggers=["fall_detected", "pressure_empty", "vision_fall",
                  "heart_rate", "blood_oxygen"],
        priority=0,    # 最高优先级
        color="red",
        icon="🚨",
        query_interval=10,   # 紧急Agent查询间隔更短
    ),
    NursingAgentDefinition(
        name="vitals_agent",
        display_name="体征监护Agent",
        when_to_use="心率/血压/血氧/体温异常或趋势变化 — 负责所有生命体征的专科分析",
        system_prompt=VITALS_AGENT_PROMPT,
        allowed_actions={"raise_bed", "lower_bed", "voice_remind",
                         "alert_info", "alert_warning", "alert_critical", "no_action"},
        triggers=["heart_rate", "blood_oxygen", "temperature",
                  "blood_pressure_sys", "vitals_trend"],
        priority=2,
        color="green",
        icon="🫀",
        query_interval=30,
    ),
    NursingAgentDefinition(
        name="pressure_agent",
        display_name="褥疮预防Agent",
        when_to_use="受压风险评估、翻身提醒、气囊减压策略 — 通过压力矩阵和姿态时间判断",
        system_prompt=PRESSURE_AGENT_PROMPT,
        allowed_actions={"air_inflate", "air_deflate", "air_relief_cycle",
                         "raise_bed", "voice_remind", "alert_info",
                         "alert_warning", "no_action"},
        triggers=["ulcer_risk_level", "posture_unchanged_minutes",
                  "predicted_risk", "posture"],
        priority=3,
        color="blue",
        icon="🛡️",
        query_interval=60,   # 褥疮评估间隔较长
    ),
    NursingAgentDefinition(
        name="companion_agent",
        display_name="情绪陪伴Agent",
        when_to_use="患者情绪低落、孤独、焦虑时主动关怀 — 或应患者语音请求进行陪聊",
        system_prompt=COMPANION_AGENT_PROMPT,
        allowed_actions={"voice_remind", "alert_info", "alert_warning", "no_action"},
        triggers=["emotion_score", "loneliness_flag", "voice_request"],
        priority=7,   # 最低优先级 (非紧急)
        color="yellow",
        icon="💬",
        query_interval=120,  # 陪伴Agent不频繁主动触发
    ),
]


def get_builtin_nursing_agents() -> list[NursingAgentDefinition]:
    """返回内置护理Agent定义列表 (对标 OpenHarness get_builtin_agent_definitions)"""
    return list(BUILTIN_NURSING_AGENTS)


def get_agent_by_name(name: str) -> Optional[NursingAgentDefinition]:
    """按名称查找Agent定义"""
    for agent in BUILTIN_NURSING_AGENTS:
        if agent.name == name:
            return agent
    return None


def get_agents_for_triggers(context: dict) -> list[NursingAgentDefinition]:
    """
    根据上下文数据返回应被触发的Agent列表 (分诊路由依据)

    对标 OpenHarness Coordinator 的分派逻辑:
      context中有哪些key → 匹配哪些Agent的triggers → 返回按priority排序的Agent列表
    """
    matched = []
    for agent_def in BUILTIN_NURSING_AGENTS:
        for trigger_key in agent_def.triggers:
            if trigger_key in context and context[trigger_key] is not None:
                matched.append(agent_def)
                break  # 匹配任一trigger即可
    # 按优先级排序 (priority越小越优先)
    matched.sort(key=lambda a: a.priority)
    return matched
