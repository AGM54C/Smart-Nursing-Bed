/**
 * 智能护理病床 - 压力矩阵深度分析 (云端 LLM)
 *
 * 处理复杂分析任务:
 *   - 压力分布详细解读
 *   - 受压风险评估报告
 *   - 长期趋势分析和护理建议
 */

const express = require('express');
const router = express.Router();
const { chat } = require('../services/llm');   // 统一 LLM 网关 (LLM_PROVIDER 切换 openai/涂鸦智能体)

/**
 * POST /api/pressure/analyze
 * 
 * 使用Kimi AI对压力矩阵数据进行深度分析
 * 
 * Body: {
 *   patient_id: 1,
 *   grid: [[...],[...],...],          // 8x8压力矩阵
 *   posture_cnn: "supine",           // RPi CNN分类结果
 *   posture_confidence: 0.95,
 *   ulcer_risk: "low",              // RPi受压风险等级
 *   body_regions: {...},             // 身体区域压力
 *   duration_data: {...}             // 持续时间数据(可选)
 * }
 */
router.post('/analyze', async (req, res) => {
    try {
        const {
            patient_id,
            grid,
            posture_cnn,
            posture_confidence,
            ulcer_risk,
            body_regions,
            duration_data
        } = req.body;

        if (!grid || !Array.isArray(grid)) {
            return res.status(400).json({ error: 'Missing or invalid grid data' });
        }

        // 获取患者信息
        const db = req.app.get('db');
        let patientInfo = '';
        if (patient_id) {
            const patient = db.prepare('SELECT name, age, condition FROM patients WHERE id = ?').get(patient_id);
            if (patient) {
                patientInfo = `患者: ${patient.name}, ${patient.age}岁, 病情: ${patient.condition || '未记录'}`;
            }
        }

        // 获取最近的体征数据
        let recentVitals = '';
        if (patient_id) {
            const vitals = db.prepare(
                'SELECT heart_rate, blood_oxygen, temperature, sleep_posture FROM vitals WHERE patient_id = ? ORDER BY created_at DESC LIMIT 1'
            ).get(patient_id);
            if (vitals) {
                recentVitals = `最新体征: 心率${vitals.heart_rate || '?'}bpm, 血氧${vitals.blood_oxygen || '?'}%, 体温${vitals.temperature || '?'}°C`;
            }
        }

        // 构建Kimi分析Prompt
        const gridStr = grid.map((row, i) => `  行${i}: [${row.join(', ')}]`).join('\n');

        const prompt = `你是一位专业的体位护理评估专家。请分析以下智能病床织物压力传感器的数据，给出专业的护理建议。

## 患者信息
${patientInfo || '未知患者'}
${recentVitals || ''}

## 压力矩阵数据 (8×8, 值域0-4095, 值越高压力越大)
${gridStr}

## 边缘AI分析结果
- CNN睡姿分类: ${posture_cnn || '未知'} (置信度: ${posture_confidence ? (posture_confidence * 100).toFixed(0) + '%' : '未知'})
- 受压风险等级: ${ulcer_risk || '未评估'}
${body_regions ? `- 身体区域压力: 头颈${body_regions.head_neck?.toFixed(0)}, 肩部${body_regions.shoulders?.toFixed(0)}, 背部${body_regions.back?.toFixed(0)}, 臀部${body_regions.hips?.toFixed(0)}, 腿部${body_regions.legs?.toFixed(0)}` : ''}
${duration_data ? `- 持续受压数据: ${JSON.stringify(duration_data)}` : ''}

## 请分析以下内容 (用JSON格式返回):
1. **pressure_distribution**: 压力分布特征描述 (100字内)
2. **posture_assessment**: 对CNN睡姿判断的确认或修正
3. **ulcer_risk_detail**: 受压风险详细评估
   - level: none/low/medium/high/critical
   - high_risk_areas: 高风险部位列表
   - explanation: 风险原因说明
4. **nursing_advice**: 具体护理建议 (3-5条)
5. **alert**: 是否需要立即通知护理人员 (true/false, 及原因)

请直接返回JSON,不要其他文字。`;

        // 调用统一 LLM 网关 (45s 超时; 低温度确保稳定 JSON 输出)
        let aiText;
        try {
            aiText = await chat([
                { role: 'system', content: '你是专业的体位护理评估AI助手。始终用JSON格式回复。' },
                { role: 'user', content: prompt }
            ], { temperature: 0.3, maxTokens: 1000, timeoutMs: 45000, agentKey: 'pressure_agent' });
        } catch (llmErr) {
            console.error('[Pressure AI] LLM error:', llmErr.message);
            return res.status(502).json({ error: 'AI service error' });
        }
        if (!aiText) {
            console.error('[Pressure AI] LLM timeout');
            return res.status(502).json({ error: 'AI service timeout' });
        }

        // 尝试解析JSON
        let analysis;
        try {
            // 提取JSON (有时Kimi会包裹在```json...```中)
            const jsonMatch = aiText.match(/\{[\s\S]*\}/);
            analysis = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(aiText);
        } catch (parseErr) {
            // JSON解析失败, 返回原始文本
            analysis = {
                raw_response: aiText,
                parse_error: true
            };
        }

        // 如果AI判断需要告警
        if (analysis.alert === true) {
            try {
                db.prepare(
                    'INSERT INTO alerts (patient_id, alert_type, severity, message) VALUES (?, ?, ?, ?)'
                ).run(
                    patient_id || 1,
                    'pressure_ulcer_risk',
                    analysis.ulcer_risk_detail?.level === 'critical' ? 'critical' : 'warning',
                    analysis.ulcer_risk_detail?.explanation || '压力分布异常,存在受压风险'
                );
            } catch (dbErr) {
                console.error('[Pressure AI] Alert insert error:', dbErr.message);
            }
        }

        res.json({
            success: true,
            analysis,
            edge_results: {
                posture_cnn,
                posture_confidence,
                ulcer_risk,
                body_regions
            },
            timestamp: new Date().toISOString()
        });

    } catch (err) {
        console.error('[Pressure AI] Error:', err);
        res.status(500).json({ error: err.message });
    }
});


/**
 * GET /api/pressure/history/:patient_id
 * 
 * 获取患者的压力矩阵历史 (最近N条含fabric_sensor_raw的记录)
 */
router.get('/history/:patient_id', (req, res) => {
    try {
        const db = req.app.get('db');
        const limit = parseInt(req.query.limit) || 20;

        const rows = db.prepare(
            `SELECT id, fabric_sensor_raw, sleep_posture, created_at 
             FROM vitals 
             WHERE patient_id = ? AND fabric_sensor_raw IS NOT NULL 
             ORDER BY created_at DESC 
             LIMIT ?`
        ).all(req.params.patient_id, limit);

        // 解析fabric_sensor_raw JSON
        const parsed = rows.map(row => ({
            id: row.id,
            grid: row.fabric_sensor_raw ? JSON.parse(row.fabric_sensor_raw) : null,
            posture: row.sleep_posture,
            time: row.created_at
        }));

        res.json({ history: parsed });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});



// ─────────────────────────────────────────────────────────────────
//  POST /api/pressure/predict  — instant zone-based risk scoring
// ─────────────────────────────────────────────────────────────────
const BODY_ZONES = [
    { id: 'occiput',  name: '枕部',   rows:[0,1], cols:[2,5], w:1.5 },
    { id: 'shoulder', name: '肩胛',   rows:[1,2], cols:[1,6], w:2.0 },
    { id: 'thoracic', name: '胸背',   rows:[3,4], cols:[2,5], w:1.2 },
    { id: 'sacrum',   name: '骶尾',   rows:[4,5], cols:[2,5], w:3.0 },
    { id: 'heel_l',   name: '左足跟', rows:[6,7], cols:[2,3], w:2.5 },
    { id: 'heel_r',   name: '右足跟', rows:[6,7], cols:[4,5], w:2.5 },
];
const POSTURE_NEXT = {
    supine:    { next:'left_side',  label:'建议左侧卧 30°' },
    left_side: { next:'supine',     label:'建议恢复仰卧位' },
    right_side:{ next:'left_side',  label:'建议转换左侧卧' },
    prone:     { next:'supine',     label:'建议转为仰卧位' },
    sitting:   { next:'supine',     label:'建议平躺休息' },
};
function zoneAvg(grid, r1,r2,c1,c2) {
    let s=0,n=0;
    for(let r=r1;r<=Math.min(r2,grid.length-1);r++)
        for(let c=c1;c<=Math.min(c2,(grid[r]||[]).length-1);c++){s+=grid[r][c]||0;n++;}
    return n?s/n:0;
}

router.post('/predict', (req, res) => {
    const { grid, posture='supine', posture_minutes=60 } = req.body;
    if (!grid || !Array.isArray(grid)) return res.status(400).json({ error: 'grid required' });

    const zones = BODY_ZONES.map(z => {
        const avg = zoneAvg(grid, z.rows[0], z.rows[1], z.cols[0], z.cols[1]);
        const norm = Math.min(avg/4095, 1);
        const timeFact = Math.min(posture_minutes/120, 2);
        const score = norm * z.w * timeFact;
        const level = score>1.5?'high':score>0.8?'medium':score>0.3?'low':'safe';
        return { ...z, avg_pressure: Math.round(avg), norm_pct: Math.round(norm*100), score: Math.round(score*100)/100, level };
    });

    const maxScore = Math.max(...zones.map(z=>z.score));
    const topZone  = zones.find(z=>z.score===maxScore);
    const avgNorm  = zones.reduce((s,z)=>s+z.norm_pct,0)/zones.length/100;
    const interval = Math.max(30, 120*(1-avgNorm*0.5));
    const until    = Math.max(0, Math.round(interval - posture_minutes));
    const overallRisk = maxScore>1.5?'high':maxScore>0.8?'medium':maxScore>0.3?'low':'safe';

    res.json({
        zones: zones.sort((a,b)=>b.score-a.score),
        overall_risk: overallRisk,
        overall_score: Math.round(maxScore*100)/100,
        top_risk_zone: topZone,
        minutes_until_turn: until,
        needs_immediate_turn: until===0,
        recommended_action: POSTURE_NEXT[posture] || POSTURE_NEXT.supine,
        adjusted_interval: Math.round(interval),
        posture, time_in_posture: posture_minutes,
        timestamp: new Date().toISOString()
    });
});

// GET /api/pressure/schedule/:patient_id
router.get('/schedule/:patient_id', (req, res) => {
    const db = req.app.locals.db || req.app.get('db');
    try {
        const v = db.prepare('SELECT sleep_posture,recorded_at FROM vitals WHERE patient_id=? ORDER BY recorded_at DESC LIMIT 1')
                    .get(req.params.patient_id);
        const posture = v?.sleep_posture || 'supine';
        const ROTATION = ['supine','left_side','supine','right_side'];
        const LABELS   = { supine:'仰卧位', left_side:'左侧卧30°', right_side:'右侧卧30°', prone:'俯卧位', sitting:'坐起' };
        const now = new Date();
        const schedule = Array.from({length:4},(_,i)=>{
            const t = new Date(now.getTime()+(i+1)*2*3600000);
            const p = ROTATION[i%4];
            return { index:i+1, posture:p, label:LABELS[p]||p,
                     time: t.toTimeString().slice(0,5), due_in_minutes:(i+1)*120 };
        });
        res.json({ current_posture:posture, recorded_at:v?.recorded_at, schedule });
    } catch(e) { res.status(500).json({ error: e.message }); }
});

module.exports = router;

