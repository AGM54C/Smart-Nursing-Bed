/**
 * Emotion Analysis Route — LLM多维情感识别 + 关键词规则降级
 * POST /api/emotion/analyze
 *   主路径: LLM 输出 primary_emotion / intensity / valence(效价) / arousal(唤醒度)
 *           及 抑郁/焦虑/疼痛 三维风险指标, 持久化到 emotion_records
 *   降级:   LLM 超时(8s)或解析失败时自动回退关键词规则分类器, 保证零依赖可用
 */
const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../middleware/auth');
const { chat } = require('../services/llm');

// Keyword-based emotion classifier (降级路径 + 元数据来源)
const EMOTION_RULES = [
    { emotion: 'pain',     label: '疼痛',  emoji: '😣', color: '#ef4444', keywords: ['疼','痛','难受','不舒服','很痛','很疼','撑不住','受不了','酸','麻','刺痛'] },
    { emotion: 'anxious',  label: '焦虑',  emoji: '😰', color: '#f59e0b', keywords: ['担心','害怕','紧张','焦虑','恐惧','不安','怎么办','会不会','吓','慌','忧虑'] },
    { emotion: 'sad',      label: '忧郁',  emoji: '😢', color: '#6366f1', keywords: ['难过','伤心','哭','悲','寂寞','想家','没意思','绝望','失落','沮丧'] },
    { emotion: 'lonely',   label: '孤独',  emoji: '🥺', color: '#ec4899', keywords: ['孤独','一个人','没人','想念','思念','家人','子女','孩子','陪我'] },
    { emotion: 'tired',    label: '疲惫',  emoji: '😴', color: '#8b5cf6', keywords: ['累','乏','困','睡不着','无力','提不起劲','没精神','疲倦'] },
    { emotion: 'happy',    label: '愉快',  emoji: '😊', color: '#22c55e', keywords: ['开心','高兴','好','不错','挺好','谢谢','舒服','好多了','轻松','满意','棒'] },
    { emotion: 'calm',     label: '平静',  emoji: '😌', color: '#14b8a6', keywords: ['还好','正常','平静','没事','一般','还行'] },
];
const NEUTRAL_META = { emotion: 'neutral', label: '平静', emoji: '😌', color: '#14b8a6' };
const SEVERITY_MAP = { pain: 4, anxious: 3, sad: 3, lonely: 2, tired: 2, happy: 0, calm: 0, neutral: 0 };
const NEGATIVE = ['anxious', 'sad', 'pain', 'lonely'];
const SUGGESTIONS = {
    pain:    '患者可能正在经历疼痛，建议护士立即评估疼痛程度（NRS量表）并按医嘱镇痛。',
    anxious: '患者情绪焦虑，建议主动沟通病情，必要时通知主治医师。',
    sad:     '患者情绪低落，建议增加探视，评估抑郁风险，联系家属。',
    lonely:  '患者感到孤独，建议联系家属增加陪伴，或安排志愿者服务。',
    tired:   '患者疲惫，检查夜间睡眠质量，减少不必要打扰。',
    happy:   '患者情绪良好，继续常规护理。',
    calm:    '患者情绪平稳，继续常规护理。',
    neutral: '继续观察患者状态。',
};
// 规则路径的粗粒度 Valence-Arousal 映射 (LLM不可用时保证维度字段仍有值)
const VA_MAP = {
    pain:    { valence: -0.8, arousal: 0.8 },
    anxious: { valence: -0.6, arousal: 0.8 },
    sad:     { valence: -0.7, arousal: 0.3 },
    lonely:  { valence: -0.5, arousal: 0.3 },
    tired:   { valence: -0.3, arousal: 0.1 },
    happy:   { valence:  0.8, arousal: 0.6 },
    calm:    { valence:  0.4, arousal: 0.2 },
    neutral: { valence:  0.0, arousal: 0.3 },
};

function metaOf(emotion) {
    return EMOTION_RULES.find(r => r.emotion === emotion) || NEUTRAL_META;
}

function classifyEmotion(text) {
    const scores = {};
    for (const rule of EMOTION_RULES) {
        scores[rule.emotion] = rule.keywords.filter(kw => text.includes(kw)).length;
    }
    const top = Object.entries(scores).sort((a, b) => b[1] - a[1])[0];
    if (!top || top[1] === 0) return { ...NEUTRAL_META, score: 0 };
    return { ...metaOf(top[0]), score: top[1] };
}

const SER_SYSTEM_PROMPT = `你是医疗场景语音情感分析引擎(SER)。分析患者话语的情绪状态。
只输出一个JSON对象,不要输出任何其他文字、注释或markdown代码块:
{"emotion":"pain|anxious|sad|lonely|tired|happy|calm|neutral","intensity":0到1的小数,"valence":-1到1的小数,"arousal":0到1的小数,"risks":{"depression":0到1,"anxiety":0到1,"pain":0到1},"summary":"不超过30字的护理建议"}
字段含义: intensity=情绪强度; valence=效价(负面情绪为负值); arousal=唤醒度(情绪激动程度); risks=抑郁/焦虑/疼痛三维风险指标。`;

async function llmAnalyze(text, recentEmotions) {
    const user = `患者说:「${text}」` +
        (recentEmotions.length ? `\n近期情绪序列: ${recentEmotions.join(', ')}` : '');
    const raw = await chat(
        [{ role: 'system', content: SER_SYSTEM_PROMPT }, { role: 'user', content: user }],
        { timeoutMs: 8000, maxTokens: 300, temperature: 0.3, agentKey: 'companion_agent', fallback: null }
    );
    if (!raw) return null;
    // 剥掉可能的 ```json 围栏后解析
    const cleaned = raw.replace(/```json|```/g, '').trim();
    const m = cleaned.match(/\{[\s\S]*\}/);
    if (!m) return null;
    const j = JSON.parse(m[0]);
    if (!j.emotion || !metaOf(j.emotion)) return null;
    const clamp = (x, lo, hi, dft) => (typeof x === 'number' && !isNaN(x)) ? Math.min(hi, Math.max(lo, x)) : dft;
    return {
        emotion: EMOTION_RULES.some(r => r.emotion === j.emotion) || j.emotion === 'neutral' ? j.emotion : 'neutral',
        intensity: clamp(j.intensity, 0, 1, 0.5),
        valence: clamp(j.valence, -1, 1, 0),
        arousal: clamp(j.arousal, 0, 1, 0.5),
        risks: {
            depression: clamp(j.risks && j.risks.depression, 0, 1, 0),
            anxiety: clamp(j.risks && j.risks.anxiety, 0, 1, 0),
            pain: clamp(j.risks && j.risks.pain, 0, 1, 0),
        },
        summary: (j.summary || '').slice(0, 60),
    };
}

// POST /api/emotion/analyze
router.post('/analyze', authMiddleware, async (req, res) => {
    const { text, patient_id, history_emotions } = req.body;
    if (!text) return res.status(400).json({ error: 'text is required' });
    const recentEmotions = history_emotions || [];

    let out;      // 统一输出结构
    let source;

    // ── 主路径: LLM 多维分析 ──
    try {
        const llm = await llmAnalyze(text, recentEmotions);
        if (llm) {
            const meta = metaOf(llm.emotion);
            const maxRisk = Math.max(llm.risks.depression, llm.risks.anxiety, llm.risks.pain);
            out = {
                emotion: llm.emotion, label: meta.label, emoji: meta.emoji, color: meta.color,
                intensity: llm.intensity, valence: llm.valence, arousal: llm.arousal,
                risks: llm.risks,
                severity: Math.min(4, Math.round(maxRisk * 4 + (NEGATIVE.includes(llm.emotion) ? 1 : 0))),
                nursing_suggestion: llm.summary || SUGGESTIONS[llm.emotion] || '继续观察。',
            };
            source = 'llm';
        }
    } catch (e) { /* fall through to rules */ }

    // ── 降级路径: 关键词规则 ──
    if (!out) {
        const result = classifyEmotion(text);
        const va = VA_MAP[result.emotion] || VA_MAP.neutral;
        const sev = SEVERITY_MAP[result.emotion] || 0;
        out = {
            emotion: result.emotion, label: result.label, emoji: result.emoji, color: result.color,
            intensity: Math.min(1, 0.3 + result.score * 0.2),
            valence: va.valence, arousal: va.arousal,
            risks: {
                depression: ['sad', 'lonely'].includes(result.emotion) ? 0.5 : 0,
                anxiety: result.emotion === 'anxious' ? 0.6 : 0,
                pain: result.emotion === 'pain' ? 0.7 : 0,
            },
            severity: sev,
            nursing_suggestion: SUGGESTIONS[result.emotion] || '继续观察。',
        };
        source = 'rule_based';
    }

    const persistentDistress = recentEmotions.length >= 2 &&
        recentEmotions.slice(-2).every(e => NEGATIVE.includes(e)) &&
        NEGATIVE.includes(out.emotion);
    out.persistent_distress = persistentDistress;
    out.needs_alert = persistentDistress || out.severity >= 4 || out.risks.pain >= 0.7;
    out.source = source;

    // ── 持久化到 emotion_records (schema 已有 valence/arousal/risk_indicators 字段) ──
    if (patient_id) {
        try {
            req.app.locals.db.prepare(`
                INSERT INTO emotion_records
                    (patient_id, text_input, primary_emotion, emotion_intensity, valence, arousal, risk_indicators, analysis_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            `).run(patient_id, text.slice(0, 200), out.emotion, out.intensity,
                   out.valence, out.arousal, JSON.stringify(out.risks), JSON.stringify(out));
        } catch (e) { /* 存证失败不影响响应 */ }
    }

    res.json(out);
});

// POST /api/emotion/log
router.post('/log', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { patient_id, emotion, label, severity, text_snippet } = req.body;
    try {
        db.prepare(`CREATE TABLE IF NOT EXISTS emotion_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER,
            emotion TEXT, label TEXT, severity INTEGER, text_snippet TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)`).run();
        const r = db.prepare(
            'INSERT INTO emotion_logs (patient_id, emotion, label, severity, text_snippet) VALUES (?,?,?,?,?)'
        ).run(patient_id, emotion, label, severity, (text_snippet||'').slice(0,100));
        res.json({ id: r.lastInsertRowid });
    } catch(e) { res.status(500).json({ error: e.message }); }
});

// GET /api/emotion/history/:patient_id
router.get('/history/:patient_id', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    try {
        db.prepare(`CREATE TABLE IF NOT EXISTS emotion_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER,
            emotion TEXT, label TEXT, severity INTEGER, text_snippet TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)`).run();
        res.json(db.prepare(
            'SELECT * FROM emotion_logs WHERE patient_id=? ORDER BY created_at DESC LIMIT 20'
        ).all(req.params.patient_id));
    } catch(e) { res.json([]); }
});

module.exports = router;
