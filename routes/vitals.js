const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../middleware/auth');

// POST /api/vitals - Ingest vitals from ESP32/Raspberry Pi
router.post('/', (req, res) => {
    // Device authentication via API key
    const apiKey = req.headers['x-api-key'];
    if (apiKey !== process.env.DEVICE_API_KEY) {
        return res.status(401).json({ error: '设备认证失败' });
    }

    const db = req.app.locals.db;
    const { patient_id, heart_rate, blood_pressure_sys, blood_pressure_dia, blood_oxygen, blood_glucose, temperature, respiration_rate, sleep_posture, temperature_grid, fabric_sensor_raw } = req.body;

    if (!patient_id) {
        return res.status(400).json({ error: '缺少患者ID' });
    }

    // Insert vitals
    const result = db.prepare(`
        INSERT INTO vitals (patient_id, heart_rate, blood_pressure_sys, blood_pressure_dia, blood_oxygen, blood_glucose, temperature, respiration_rate, sleep_posture, temperature_grid, fabric_sensor_raw)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(patient_id, heart_rate, blood_pressure_sys, blood_pressure_dia, blood_oxygen, blood_glucose, temperature, respiration_rate, sleep_posture,
        temperature_grid ? JSON.stringify(temperature_grid) : null,
        fabric_sensor_raw ? JSON.stringify(fabric_sensor_raw) : null
    );

    // Check thresholds and generate alerts
    const patient = db.prepare('SELECT * FROM patients WHERE id = ?').get(patient_id);
    if (patient) {
        const agentConfig = db.prepare('SELECT * FROM agent_configs WHERE agent_name = ?').get(patient.assigned_agent);
        if (agentConfig && agentConfig.vital_thresholds) {
            const thresholds = JSON.parse(agentConfig.vital_thresholds);
            checkThresholds(db, patient_id, req.body, thresholds, patient.name);
        }
    }

    res.status(201).json({ id: result.lastInsertRowid, message: '数据记录成功' });

    // 记录设备IP (按patient_id绑定，用于云端摄像头自动发现)
    const deviceIp = req.headers['x-forwarded-for']?.split(',')[0].trim()
        || req.socket.remoteAddress?.replace('::ffff:', '') || null;
    if (deviceIp && patient_id) {
        if (!req.app.locals.deviceIps) req.app.locals.deviceIps = {};
        req.app.locals.deviceIps[patient_id] = deviceIp;
    }

    // 实时推送：通知所有连接的浏览器客户端
    const io = req.app.locals.io;
    if (io) {
        io.emit('vitals_update', {
            patient_id,
            heart_rate, blood_pressure_sys, blood_pressure_dia,
            blood_oxygen, temperature, respiration_rate, sleep_posture,
            recorded_at: new Date().toISOString()
        });
    }
});

function checkThresholds(db, patientId, vitals, thresholds, patientName) {
    const insertAlert = db.prepare(
        'INSERT INTO alerts (patient_id, alert_type, metric, value, threshold, message) VALUES (?, ?, ?, ?, ?, ?)'
    );

    if (vitals.heart_rate) {
        if (thresholds.heart_rate_min && vitals.heart_rate < thresholds.heart_rate_min) {
            insertAlert.run(patientId, 'critical', '心率', vitals.heart_rate,
                `<${thresholds.heart_rate_min} bpm`,
                `🚨 ${patientName}心率过低：${vitals.heart_rate}bpm，低于安全阈值(${thresholds.heart_rate_min})，请立即查看！`);
        }
        if (thresholds.heart_rate_max && vitals.heart_rate > thresholds.heart_rate_max) {
            insertAlert.run(patientId, 'critical', '心率', vitals.heart_rate,
                `>${thresholds.heart_rate_max} bpm`,
                `🚨 ${patientName}心率过高：${vitals.heart_rate}bpm，超过安全阈值(${thresholds.heart_rate_max})，请立即查看！`);
        }
    }

    if (vitals.blood_oxygen && thresholds.blood_oxygen_min && vitals.blood_oxygen < thresholds.blood_oxygen_min) {
        insertAlert.run(patientId, 'critical', '血氧', vitals.blood_oxygen,
            `<${thresholds.blood_oxygen_min}%`,
            `🚨 ${patientName}血氧饱和度过低：${vitals.blood_oxygen}%，低于安全阈值(${thresholds.blood_oxygen_min}%)，请立即查看！`);
    }

    if (vitals.temperature && thresholds.temperature_max && vitals.temperature > thresholds.temperature_max) {
        insertAlert.run(patientId, 'warning', '体温', vitals.temperature,
            `>${thresholds.temperature_max}°C`,
            `⚠️ ${patientName}体温偏高：${vitals.temperature}°C，超过阈值(${thresholds.temperature_max}°C)，注意观察`);
    }

    if (vitals.blood_pressure_sys) {
        if (thresholds.bp_sys_max && vitals.blood_pressure_sys > thresholds.bp_sys_max) {
            insertAlert.run(patientId, 'warning', '收缩压', vitals.blood_pressure_sys,
                `>${thresholds.bp_sys_max} mmHg`,
                `⚠️ ${patientName}收缩压偏高：${vitals.blood_pressure_sys}mmHg，超过阈值(${thresholds.bp_sys_max})，请关注`);
        }
    }

    if (vitals.blood_glucose) {
        if (thresholds.blood_glucose_max && vitals.blood_glucose > thresholds.blood_glucose_max) {
            insertAlert.run(patientId, 'warning', '血糖', vitals.blood_glucose,
                `>${thresholds.blood_glucose_max} mmol/L`,
                `⚠️ ${patientName}血糖偏高：${vitals.blood_glucose}mmol/L，超过阈值(${thresholds.blood_glucose_max})，请关注饮食`);
        }
        if (thresholds.blood_glucose_min && vitals.blood_glucose < thresholds.blood_glucose_min) {
            insertAlert.run(patientId, 'critical', '血糖', vitals.blood_glucose,
                `<${thresholds.blood_glucose_min} mmol/L`,
                `🚨 ${patientName}低血糖：${vitals.blood_glucose}mmol/L，低于安全阈值(${thresholds.blood_glucose_min})，请立即处理！`);
        }
    }
}

// GET /api/vitals/:patientId - Get vitals history
router.get('/:patientId', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { patientId } = req.params;
    const { days = 7, limit = 100 } = req.query;

    const vitals = db.prepare(`
        SELECT * FROM vitals 
        WHERE patient_id = ? AND recorded_at >= datetime('now', '-${parseInt(days)} days')
        ORDER BY recorded_at ASC
        LIMIT ?
    `).all(patientId, parseInt(limit));

    res.json(vitals);
});

// GET /api/vitals/:patientId/latest
router.get('/:patientId/latest', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const vital = db.prepare(
        'SELECT * FROM vitals WHERE patient_id = ? ORDER BY recorded_at DESC LIMIT 1'
    ).get(req.params.patientId);

    res.json(vital || {});
});

// GET /api/vitals/:patientId/stats
router.get('/:patientId/stats', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { days = 7 } = req.query;

    const stats = db.prepare(`
        SELECT 
            AVG(heart_rate) as avg_heart_rate,
            MIN(heart_rate) as min_heart_rate,
            MAX(heart_rate) as max_heart_rate,
            AVG(blood_pressure_sys) as avg_bp_sys,
            AVG(blood_pressure_dia) as avg_bp_dia,
            AVG(blood_oxygen) as avg_spo2,
            MIN(blood_oxygen) as min_spo2,
            AVG(blood_glucose) as avg_glucose,
            AVG(temperature) as avg_temp,
            COUNT(*) as total_readings
        FROM vitals
        WHERE patient_id = ? AND recorded_at >= datetime('now', '-${parseInt(days)} days')
    `).get(req.params.patientId);

    res.json(stats);
});

module.exports = router;
