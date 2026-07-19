const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../middleware/auth');
const { chat } = require('../services/llm');   // 统一 LLM 网关 (LLM_PROVIDER 切换 openai/涂鸦智能体)

// 设备 + JWT 双认证中间件 (树莓派用X-API-Key，Web前端用JWT)
function deviceOrAuth(req, res, next) {
    const apiKey = req.headers['x-api-key'] || req.headers['x-device-key'];
    if (apiKey && apiKey === process.env.DEVICE_API_KEY) {
        req.user = { role: 'device', id: 0 };  // 设备身份
        return next();
    }
    // 否则走JWT认证
    return authMiddleware(req, res, next);
}

// GET /api/agents - List all agents
router.get('/', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const agents = db.prepare('SELECT id, agent_name, display_name, disease_type, description, icon FROM agent_configs').all();
    res.json(agents);
});

// GET /api/agents/:name
router.get('/:name', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const agent = db.prepare('SELECT * FROM agent_configs WHERE agent_name = ?').get(req.params.name);
    if (!agent) return res.status(404).json({ error: 'Agent不存在' });
    res.json(agent);
});

// LLM 超时封装：30s内没回来就返回 no_action（大模型响应较慢）
const LLM_TIMEOUT_MS = 30000;
const NO_ACTION_FALLBACK = '{"action":"no_action","params":{},"reasoning":"LLM server timeout","confidence":0,"urgency":"low"}';
function callKimiWithTimeout(systemPrompt, question, agentKey) {
    return chat([
        { role: 'system', content: systemPrompt },
        { role: 'user', content: question },
    ], { timeoutMs: LLM_TIMEOUT_MS, fallback: NO_ACTION_FALLBACK, agentKey });
}

// 多轮对话 — 直接透传消息数组给统一网关 (openai 走 stream+SSE 解析, tuya 走智能体 API)
function callKimiMessages(messages, timeoutMs = 30000, agentKey) {
    return chat(messages, { timeoutMs, agentKey });
}

// POST /api/agents/consult - Consult with AI agent (设备+JWT双认证)
router.post('/consult', deviceOrAuth, async (req, res) => {
    console.log('[DEBUG /consult] body:', JSON.stringify(req.body).slice(0, 200));
    const db = req.app.locals.db;
    const { patient_id, question, system_prompt: deviceSystemPrompt } = req.body;

    try {
        // 设备直连模式: 有 system_prompt (设备可发送空question，表示定时巡检)
        if (deviceSystemPrompt && !patient_id) {
            const q = question || '当前没有异常数据，请回复no_action';
            const response = await callKimiWithTimeout(deviceSystemPrompt, q);
            return res.json({ response, source: 'device_direct' });
        }

        if (!question) {
            return res.status(400).json({ error: '请提供问题 (question)' });
        }

        // Web 模式: 需要 patient_id
        if (!patient_id) {
            return res.status(400).json({ error: '请提供患者ID' });
        }

        const patient = db.prepare('SELECT * FROM patients WHERE id = ?').get(patient_id);
        if (!patient) return res.status(404).json({ error: '患者不存在' });

        const agent = db.prepare('SELECT * FROM agent_configs WHERE agent_name = ?').get(patient.assigned_agent);
        if (!agent) return res.status(404).json({ error: '未找到对应的护理Agent' });

        const latestVitals = db.prepare(
            'SELECT * FROM vitals WHERE patient_id = ? ORDER BY recorded_at DESC LIMIT 5'
        ).all(patient_id);

        const context = `
## 当前患者信息
- 姓名：${patient.name}，${patient.age}岁${patient.gender}
- 疾病：${patient.disease_type} - ${patient.disease_detail}
- 床位：${patient.room_number}房 ${patient.bed_number}号床
- 入院时间：${patient.admission_date}

## 最近生命体征
${latestVitals.map(v => {
            return `[${v.recorded_at}] 心率:${v.heart_rate}bpm 血压:${v.blood_pressure_sys}/${v.blood_pressure_dia}mmHg 血氧:${v.blood_oxygen}% 血糖:${v.blood_glucose}mmol/L 体温:${v.temperature}°C 睡姿:${v.sleep_posture}`;
        }).join('\n')}

## 医护人员/家属提问
${question}

请根据患者的具体情况和最新生命体征数据，提供专业、详细的回答。`;

        const response = await callKimiWithTimeout(agent.system_prompt, context, agent.agent_name);
        res.json({
            agent: agent.display_name,
            agent_icon: agent.icon,
            response: response,
            patient_name: patient.name
        });
    } catch (err) {
        console.error('Agent consult error:', err.message);
        res.status(500).json({ error: 'AI咨询失败: ' + err.message });
    }
});
// POST /api/agents/stream-chat - 非流式获取 + 模拟打字效果 (SSE)
router.post('/stream-chat', deviceOrAuth, async (req, res) => {
    const db = req.app.locals.db;
    const { patient_id, messages } = req.body;

    if (!messages || !Array.isArray(messages) || messages.length === 0)
        return res.status(400).json({ error: '请提供消息历史' });

    // Get agent system prompt
    let systemPrompt = '你是一位专业的临床医学AI助手，为护理团队提供专业、准确的中文回答。';
    let agentName = 'AI护理助手', agentIcon = '🤖', agentKey = null;
    if (patient_id) {
        const patient = db.prepare('SELECT * FROM patients WHERE id = ?').get(patient_id);
        if (patient) {
            const agent = db.prepare('SELECT * FROM agent_configs WHERE agent_name = ?').get(patient.assigned_agent);
            if (agent) { systemPrompt = agent.system_prompt; agentName = agent.display_name; agentIcon = agent.icon || '🤖'; agentKey = agent.agent_name; }
        }
    }

    // SSE headers
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    res.write(`data: ${JSON.stringify({ type: 'meta', agent: agentName, icon: agentIcon })}\n\n`);

    try {
        // 非流式获取完整响应（避免 kimi-k2.5 streaming 的 socket hang up 问题）
        const fullMessages = [{ role: 'system', content: systemPrompt }, ...messages];
        const fullText = await callKimiMessages(fullMessages, 30000, agentKey);

        if (!fullText) {
            res.write(`data: ${JSON.stringify({ type: 'error', message: 'AI响应超时，请稍后重试' })}\n\n`);
        } else {
            // 模拟打字效果：每次发送 8 个字符
            const CHUNK = 8;
            for (let i = 0; i < fullText.length; i += CHUNK) {
                res.write(`data: ${JSON.stringify({ type: 'delta', content: fullText.slice(i, i + CHUNK) })}\n\n`);
            }
        }
    } catch (err) {
        res.write(`data: ${JSON.stringify({ type: 'error', message: err.message })}\n\n`);
    }

    res.write('data: {"type":"done"}\n\n');
    res.end();
});

// ═══════════════════════════════════════════
//  Multi-Agent Swarm API (v4.0 新增)
// ═══════════════════════════════════════════

// POST /api/agents/coordinate - 触发多Agent协作决策
// 由前端仪表盘或外部系统调用, 模拟 Coordinator 的手动触发
router.post('/coordinate', deviceOrAuth, async (req, res) => {
    const { patient_id, context, question } = req.body;

    if (!context && !question) {
        return res.status(400).json({ error: '请提供上下文(context)或问题(question)' });
    }

    try {
        const db = req.app.locals.db;
        let patient = null;
        if (patient_id) {
            patient = db.prepare('SELECT * FROM patients WHERE id = ?').get(patient_id);
        }

        // 获取所有可用的专科Agent定义
        const agentDefs = [
            { name: 'emergency_agent', display_name: '急救分诊Agent', icon: '🚨', priority: 0 },
            { name: 'vitals_agent', display_name: '体征监护Agent', icon: '🫀', priority: 2 },
            { name: 'pressure_agent', display_name: '褥疮预防Agent', icon: '🛡️', priority: 3 },
            { name: 'companion_agent', display_name: '情绪陪伴Agent', icon: '💬', priority: 7 },
        ];

        // 构建查询提示
        const queryPrompt = question || JSON.stringify(context);

        // 查询每个Agent (串行, 避免API限流)
        const decisions = [];
        for (const agentDef of agentDefs) {
            try {
                const dbAgent = db.prepare('SELECT * FROM agent_configs WHERE agent_name = ?').get(agentDef.name);
                const systemPrompt = dbAgent ? dbAgent.system_prompt :
                    `你是智能护理病床的${agentDef.display_name}。根据患者数据给出护理建议。以JSON格式回复: {"action":"动作","params":{},"reasoning":"推理","confidence":0.8,"urgency":"low/medium/high"}`;

                const response = await callKimiWithTimeout(systemPrompt, queryPrompt, agentDef.name);
                if (response) {
                    decisions.push({
                        agent_name: agentDef.name,
                        display_name: agentDef.display_name,
                        icon: agentDef.icon,
                        priority: agentDef.priority,
                        response: response,
                    });
                }
            } catch (agentErr) {
                console.error(`[Coordinate] ${agentDef.name} error:`, agentErr.message);
            }
        }

        res.json({
            coordination_id: `coord_${Date.now()}`,
            agents_consulted: agentDefs.map(a => a.name),
            decisions: decisions,
            patient_name: patient ? patient.name : null,
            timestamp: new Date().toISOString(),
        });

    } catch (err) {
        console.error('Coordinate error:', err.message);
        res.status(500).json({ error: 'Multi-Agent协作失败: ' + err.message });
    }
});

// GET /api/agents/swarm/status - 获取Agent Swarm运行状态
router.get('/swarm/status', deviceOrAuth, (req, res) => {
    res.json({
        version: '4.0',
        architecture: 'Multi-Agent Nursing Swarm',
        framework_ref: 'OpenHarness',
        agents: [
            { name: 'emergency_agent', display_name: '急救分诊Agent', icon: '🚨', status: 'active', priority: 0, color: 'red' },
            { name: 'vitals_agent', display_name: '体征监护Agent', icon: '🫀', status: 'active', priority: 2, color: 'green' },
            { name: 'pressure_agent', display_name: '褥疮预防Agent', icon: '🛡️', status: 'active', priority: 3, color: 'blue' },
            { name: 'companion_agent', display_name: '情绪陪伴Agent', icon: '💬', status: 'active', priority: 7, color: 'yellow' },
        ],
        capabilities: {
            coordinator: 'NursingCoordinator — 分诊路由 + 冲突消解 + 结果聚合',
            mailbox: 'AgentMailbox — 线程安全异步消息总线',
            memory: 'PatientMemory — 跨会话患者个性化记忆',
            permission: 'ToolPermissionChecker — Agent工具权限沙箱',
        },
        safety: {
            L0: '传统规则兜底 (9条硬编码规则)',
            L1: 'Multi-Agent Swarm (4专科Agent并行决策)',
            L2: '参数沙箱 (PARAM_BOUNDS + Agent工具权限)',
            L3: '人工审核 (critical级动作需护士确认)',
        },
        timestamp: new Date().toISOString(),
    });
});

// GET /api/agents/swarm/agents - 列出所有专科Agent定义 (详细)
router.get('/swarm/agents', deviceOrAuth, (req, res) => {
    const db = req.app.locals.db;

    const agentDefs = [
        {
            name: 'emergency_agent', display_name: '急救分诊Agent', icon: '🚨',
            priority: 0, color: 'red', query_interval: 10,
            when_to_use: '跌倒检测、离床告警、危急生命体征',
            triggers: ['fall_detected', 'pressure_empty', 'vision_fall', 'heart_rate', 'blood_oxygen'],
            allowed_actions: ['alert_critical', 'alert_warning', 'voice_remind', 'no_action'],
        },
        {
            name: 'vitals_agent', display_name: '体征监护Agent', icon: '🫀',
            priority: 2, color: 'green', query_interval: 30,
            when_to_use: '心率/血压/血氧/体温异常或趋势变化',
            triggers: ['heart_rate', 'blood_oxygen', 'temperature', 'blood_pressure_sys', 'vitals_trend'],
            allowed_actions: ['raise_bed', 'lower_bed', 'voice_remind', 'alert_info', 'alert_warning', 'alert_critical', 'no_action'],
        },
        {
            name: 'pressure_agent', display_name: '褥疮预防Agent', icon: '🛡️',
            priority: 3, color: 'blue', query_interval: 60,
            when_to_use: '受压风险评估、翻身提醒、气囊减压策略',
            triggers: ['ulcer_risk_level', 'posture_unchanged_minutes', 'predicted_risk', 'posture'],
            allowed_actions: ['air_inflate', 'air_deflate', 'air_relief_cycle', 'raise_bed', 'voice_remind', 'alert_info', 'alert_warning', 'no_action'],
        },
        {
            name: 'companion_agent', display_name: '情绪陪伴Agent', icon: '💬',
            priority: 7, color: 'yellow', query_interval: 120,
            when_to_use: '患者情绪低落、孤独、焦虑时主动关怀',
            triggers: ['emotion_score', 'loneliness_flag', 'voice_request'],
            allowed_actions: ['voice_remind', 'alert_info', 'alert_warning', 'no_action'],
        },
    ];

    // 尝试从数据库获取Agent配置 (如果有)
    for (const def of agentDefs) {
        const dbAgent = db.prepare('SELECT * FROM agent_configs WHERE agent_name = ?').get(def.name);
        if (dbAgent) {
            def.has_db_config = true;
            def.db_display_name = dbAgent.display_name;
        } else {
            def.has_db_config = false;
        }
    }

    res.json({
        total: agentDefs.length,
        agents: agentDefs,
    });
});

module.exports = router;
