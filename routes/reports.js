const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../middleware/auth');
const { chat, provider: llmProvider } = require('../services/llm');

// GET /api/reports/:patientId - List reports (2-month window)
router.get('/:patientId', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { patientId } = req.params;
    const { months = 2 } = req.query;

    const reports = db.prepare(`
        SELECT * FROM reports 
        WHERE patient_id = ? AND report_date >= date('now', '-${parseInt(months)} months')
        ORDER BY report_date DESC
    `).all(patientId);

    res.json(reports);
});

// GET /api/reports/:patientId/:date - Single report
router.get('/:patientId/:date', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const report = db.prepare(
        'SELECT * FROM reports WHERE patient_id = ? AND report_date = ?'
    ).get(req.params.patientId, req.params.date);

    if (!report) return res.status(404).json({ error: '该日期暂无体检报告' });
    res.json(report);
});

// POST /api/reports/generate - Generate AI report via Kimi-2.5
router.post('/generate', authMiddleware, async (req, res) => {
    const db = req.app.locals.db;
    const { patient_id, date } = req.body;

    if (!patient_id) return res.status(400).json({ error: '缺少患者ID' });

    const reportDate = date || new Date().toISOString().split('T')[0];

    // Get patient info
    const patient = db.prepare('SELECT * FROM patients WHERE id = ?').get(patient_id);
    if (!patient) return res.status(404).json({ error: '患者不存在' });

    // Get agent config
    const agent = db.prepare('SELECT * FROM agent_configs WHERE agent_name = ?').get(patient.assigned_agent);

    // Get recent vitals (last 24 hours for daily report)
    const vitals = db.prepare(`
        SELECT * FROM vitals WHERE patient_id = ? AND recorded_at >= datetime('now', '-1 days')
        ORDER BY recorded_at ASC
    `).all(patient_id);

    // Get vitals stats
    const stats = db.prepare(`
        SELECT 
            AVG(heart_rate) as avg_hr, MIN(heart_rate) as min_hr, MAX(heart_rate) as max_hr,
            AVG(blood_pressure_sys) as avg_sys, AVG(blood_pressure_dia) as avg_dia,
            AVG(blood_oxygen) as avg_spo2, MIN(blood_oxygen) as min_spo2,
            AVG(blood_glucose) as avg_glu, MIN(blood_glucose) as min_glu, MAX(blood_glucose) as max_glu,
            AVG(temperature) as avg_temp, MAX(temperature) as max_temp,
            COUNT(*) as readings
        FROM vitals WHERE patient_id = ? AND recorded_at >= datetime('now', '-1 days')
    `).get(patient_id);

    // Get recent alerts
    const alerts = db.prepare(`
        SELECT * FROM alerts WHERE patient_id = ? AND created_at >= datetime('now', '-1 days')
        ORDER BY created_at DESC
    `).all(patient_id);

    // Build prompt for Kimi
    const prompt = `请为以下患者生成今日体检报告。
    
## 患者信息
- 姓名：${patient.name}
- 年龄：${patient.age}岁
- 性别：${patient.gender}
- 疾病类型：${patient.disease_type}
- 疾病详情：${patient.disease_detail}
- 入院日期：${patient.admission_date}

## 今日生命体征统计（${vitals.length}次采集）
- 心率：均值${stats?.avg_hr?.toFixed(1) || 'N/A'}bpm，范围${stats?.min_hr || 'N/A'}-${stats?.max_hr || 'N/A'}bpm
- 血压：均值${stats?.avg_sys?.toFixed(0) || 'N/A'}/${stats?.avg_dia?.toFixed(0) || 'N/A'}mmHg
- 血氧：均值${stats?.avg_spo2?.toFixed(1) || 'N/A'}%，最低${stats?.min_spo2 || 'N/A'}%
- 血糖：均值${stats?.avg_glu?.toFixed(1) || 'N/A'}mmol/L，范围${stats?.min_glu?.toFixed(1) || 'N/A'}-${stats?.max_glu?.toFixed(1) || 'N/A'}
- 体温：均值${stats?.avg_temp?.toFixed(1) || 'N/A'}°C，最高${stats?.max_temp || 'N/A'}°C

## 今日报警记录
${alerts.length > 0 ? alerts.map(a => `- [${a.alert_type}] ${a.message}`).join('\n') : '无报警记录'}

## 睡姿记录
${vitals.filter(v => v.sleep_posture).map(v => `${v.recorded_at}: ${v.sleep_posture}`).join(', ') || '暂无记录'}

请按以下格式输出（用JSON格式）：
{
  "summary": "整体健康状况总结（100-200字）",
  "ai_diagnosis": "临床分析和诊断意见（150-300字）",
  "rehab_suggestions": "康复理疗建议（分点列出，4-6条）",
  "risk_assessment": "风险等级评估（低风险/中等风险/高风险 + 说明）"
}`;

    try {
        console.log('[REPORT] Step 1: Calling API...');
        const aiResponse = await callKimiAPI(agent?.system_prompt || '', prompt, agent?.agent_name);
        console.log('[REPORT] Step 2: Got response, len:', aiResponse?.length);

        // Parse the AI response - robust handling of malformed JSON
        let parsed = { summary: '', ai_diagnosis: '', rehab_suggestions: '', risk_assessment: '' };
        try {
            const jsonMatch = aiResponse.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                // Clean up common AI JSON issues: fix unescaped quotes in arrays
                let cleaned = jsonMatch[0]
                    .replace(/\n/g, '\\n')
                    .replace(/\r/g, '')
                    .replace(/\t/g, '  ');
                const obj = JSON.parse(cleaned);
                parsed.summary = obj.summary || '';
                parsed.ai_diagnosis = obj.ai_diagnosis || '';
                parsed.rehab_suggestions = Array.isArray(obj.rehab_suggestions) ? obj.rehab_suggestions.join('\n') : (obj.rehab_suggestions || '');
                parsed.risk_assessment = obj.risk_assessment || '';
            } else {
                parsed.summary = aiResponse;
            }
        } catch (e) {
            console.log('[REPORT] JSON parse failed, using raw response. Error:', e.message);
            // Try to extract fields with regex as fallback
            const sumMatch = aiResponse.match(/"summary"\s*:\s*"([\s\S]*?)(?:"|",\s*")/);
            const diagMatch = aiResponse.match(/"ai_diagnosis"\s*:\s*"([\s\S]*?)(?:"|",\s*")/);
            const rehabMatch = aiResponse.match(/"rehab_suggestions"\s*:\s*([\s\S]*?)(?:],|"risk)/);
            const riskMatch = aiResponse.match(/"risk_assessment"\s*:\s*"([\s\S]*?)(?:"\s*}|"$)/);
            parsed.summary = sumMatch ? sumMatch[1].replace(/\\n/g, '\n') : aiResponse;
            parsed.ai_diagnosis = diagMatch ? diagMatch[1].replace(/\\n/g, '\n') : '';
            parsed.rehab_suggestions = rehabMatch ? rehabMatch[1].replace(/[\[\]"]/g, '').replace(/\\n/g, '\n').trim() : '';
            parsed.risk_assessment = riskMatch ? riskMatch[1].replace(/\\n/g, '\n') : '';
        }
        console.log('[REPORT] Step 3: Parsed -', 'summary:', parsed.summary?.length, 'diag:', parsed.ai_diagnosis?.length);

        const vitalStatsStr = JSON.stringify({
            avg_heart_rate: stats?.avg_hr?.toFixed(1),
            avg_bp: `${stats?.avg_sys?.toFixed(0)}/${stats?.avg_dia?.toFixed(0)}`,
            avg_spo2: stats?.avg_spo2?.toFixed(1),
            avg_temp: stats?.avg_temp?.toFixed(1),
            avg_glucose: stats?.avg_glu?.toFixed(1)
        });

        const modelUsed = llmProvider() === 'tuya' ? 'tuya-agent' : (process.env.KIMI_MODEL || 'qwen3.5-plus');

        // Save report (UPDATE also refreshes created_at so user can see it changed)
        const existing = db.prepare('SELECT id FROM reports WHERE patient_id = ? AND report_date = ?').get(patient_id, reportDate);
        console.log('[REPORT] Step 4: existing=', existing ? existing.id : 'null');

        if (existing) {
            db.prepare(`
                UPDATE reports SET summary = ?, vital_stats = ?, ai_diagnosis = ?, rehab_suggestions = ?, risk_assessment = ?, generated_by = ?, created_at = CURRENT_TIMESTAMP
                WHERE id = ?
            `).run(parsed.summary, vitalStatsStr, parsed.ai_diagnosis, parsed.rehab_suggestions, parsed.risk_assessment, modelUsed, existing.id);
        } else {
            db.prepare(`
                INSERT INTO reports (patient_id, report_date, summary, vital_stats, ai_diagnosis, rehab_suggestions, risk_assessment, generated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            `).run(patient_id, reportDate, parsed.summary, vitalStatsStr, parsed.ai_diagnosis, parsed.rehab_suggestions, parsed.risk_assessment, modelUsed);
        }
        console.log('[REPORT] Step 5: DB saved!');

        const report = db.prepare('SELECT * FROM reports WHERE patient_id = ? AND report_date = ?').get(patient_id, reportDate);
        res.json(report);
    } catch (err) {
        console.error('AI Report generation error:', err.message, 'STACK:', err.stack?.split('\n')[1]);
        res.status(500).json({ error: 'AI报告生成失败: ' + err.message });
    }
});

// 生成报告用的 LLM 调用 — 走统一网关 services/llm.js (LLM_PROVIDER 切换 openai/tuya)
// timeoutMs:0 = 不限时: 日报生成 2000 token 可能超过 30s, 不能套常规超时
function callKimiAPI(systemPrompt, userMessage, agentKey) {
    return chat([
        { role: 'system', content: systemPrompt || '你是一位专业的临床医学AI助手，请用中文回答。' },
        { role: 'user', content: userMessage },
    ], { timeoutMs: 0, maxTokens: 2000, temperature: 1, agentKey });
}

module.exports = router;
module.exports.callKimiAPI = callKimiAPI;
