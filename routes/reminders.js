const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../middleware/auth');

// ═══════════════════════════════════════════════════════════
//  SSE Client Registry  (module-level, shared across requests)
// ═══════════════════════════════════════════════════════════
// Map<clientId, { res, patientFilter }>
const sseClients = new Map();

// ═══════════════════════════════════════════════════════════
//  Reminder Plans CRUD
// ═══════════════════════════════════════════════════════════

// GET /api/reminders/:patientId — list reminders for a patient
router.get('/:patientId', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { patientId } = req.params;
    const { active } = req.query;

    let query = 'SELECT r.*, u.real_name as creator_name FROM reminders r LEFT JOIN users u ON r.created_by = u.id WHERE r.patient_id = ?';
    const params = [patientId];

    if (active !== undefined) {
        query += ' AND r.is_active = ?';
        params.push(active === 'true' ? 1 : 0);
    }
    query += ' ORDER BY r.schedule_time ASC';

    const reminders = db.prepare(query).all(...params);
    res.json(reminders);
});

// POST /api/reminders — create reminder (doctor/admin only)
router.post('/', authMiddleware, (req, res) => {
    if (req.user.role !== 'doctor' && req.user.role !== 'admin') {
        return res.status(403).json({ error: '仅医生或管理员可创建提醒' });
    }

    const db = req.app.locals.db;
    const { patient_id, reminder_type, title, description, schedule_time, dosage } = req.body;

    if (!patient_id || !reminder_type || !title || !schedule_time) {
        return res.status(400).json({ error: '缺少必填字段' });
    }

    const result = db.prepare(`
        INSERT INTO reminders (patient_id, reminder_type, title, description, schedule_time, dosage, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(patient_id, reminder_type, title, description || '', schedule_time, dosage || '', req.user.id);

    // Also generate today's log for this new reminder (only if time hasn't passed)
    const today = new Date();
    const [hh, mm] = schedule_time.split(':');
    const scheduledTime = new Date(today.getFullYear(), today.getMonth(), today.getDate(), parseInt(hh), parseInt(mm));

    if (scheduledTime > new Date()) {
        db.prepare(`
            INSERT INTO reminder_logs (reminder_id, patient_id, scheduled_time, status)
            VALUES (?, ?, ?, 'pending')
        `).run(result.lastInsertRowid, patient_id, scheduledTime.toISOString());
    }

    res.status(201).json({ id: result.lastInsertRowid, message: '提醒已创建' });
});

// PUT /api/reminders/:id — update reminder
router.put('/:id', authMiddleware, (req, res) => {
    if (req.user.role !== 'doctor' && req.user.role !== 'admin') {
        return res.status(403).json({ error: '仅医生或管理员可编辑提醒' });
    }

    const db = req.app.locals.db;
    const { title, description, schedule_time, dosage, reminder_type } = req.body;

    db.prepare(`
        UPDATE reminders SET title = ?, description = ?, schedule_time = ?, dosage = ?, reminder_type = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    `).run(title, description || '', schedule_time, dosage || '', reminder_type, req.params.id);

    res.json({ message: '提醒已更新' });
});

// DELETE /api/reminders/:id
router.delete('/:id', authMiddleware, (req, res) => {
    if (req.user.role !== 'doctor' && req.user.role !== 'admin') {
        return res.status(403).json({ error: '仅医生或管理员可删除提醒' });
    }

    const db = req.app.locals.db;
    db.prepare('DELETE FROM reminder_logs WHERE reminder_id = ?').run(req.params.id);
    db.prepare('DELETE FROM reminders WHERE id = ?').run(req.params.id);
    res.json({ message: '提醒已删除' });
});

// PUT /api/reminders/:id/toggle — enable / disable
router.put('/:id/toggle', authMiddleware, (req, res) => {
    if (req.user.role !== 'doctor' && req.user.role !== 'admin') {
        return res.status(403).json({ error: '仅医生或管理员可操作' });
    }

    const db = req.app.locals.db;
    const current = db.prepare('SELECT is_active FROM reminders WHERE id = ?').get(req.params.id);
    if (!current) return res.status(404).json({ error: '提醒不存在' });

    const newState = current.is_active ? 0 : 1;
    db.prepare('UPDATE reminders SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?').run(newState, req.params.id);
    res.json({ message: newState ? '已启用' : '已停用', is_active: newState });
});

// ═══════════════════════════════════════════════════════════
//  Reminder Logs
// ═══════════════════════════════════════════════════════════

// GET /api/reminders/logs/:patientId — today's logs
router.get('/logs/:patientId', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { patientId } = req.params;

    const logs = db.prepare(`
        SELECT rl.*, r.title, r.reminder_type, r.dosage, r.description, r.schedule_time
        FROM reminder_logs rl
        JOIN reminders r ON rl.reminder_id = r.id
        WHERE rl.patient_id = ?
          AND date(rl.scheduled_time) = date('now')
        ORDER BY rl.scheduled_time ASC
    `).all(patientId);

    res.json(logs);
});

// PUT /api/reminders/logs/:logId/complete
router.put('/logs/:logId/complete', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    db.prepare(`UPDATE reminder_logs SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?`).run(req.params.logId);
    res.json({ message: '已完成' });
});

// PUT /api/reminders/logs/:logId/skip
router.put('/logs/:logId/skip', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { note } = req.body || {};
    db.prepare(`UPDATE reminder_logs SET status = 'skipped', completed_at = CURRENT_TIMESTAMP, note = ? WHERE id = ?`).run(note || '跳过', req.params.logId);
    res.json({ message: '已跳过' });
});

// ═══════════════════════════════════════════════════════════
//  Today Overview & Stats
// ═══════════════════════════════════════════════════════════

// GET /api/reminders/today/:patientId — summary stats
router.get('/today/:patientId', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { patientId } = req.params;

    const stats = db.prepare(`
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'pending'   THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'skipped'   THEN 1 ELSE 0 END) as skipped,
            SUM(CASE WHEN status = 'missed'    THEN 1 ELSE 0 END) as missed,
            SUM(CASE WHEN status = 'notified'  THEN 1 ELSE 0 END) as notified
        FROM reminder_logs
        WHERE patient_id = ? AND date(scheduled_time) = date('now')
    `).get(patientId);

    res.json(stats);
});

// ═══════════════════════════════════════════════════════════
//  Pending Reminders — legacy polling endpoint
// ═══════════════════════════════════════════════════════════

// GET /api/reminders/pending/:patientId — returns reminders due now (±2 min)
router.get('/pending/:patientId', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { patientId } = req.params;

    const pending = db.prepare(`
        SELECT rl.*, r.title, r.reminder_type, r.dosage, r.description, r.schedule_time,
               p.name as patient_name
        FROM reminder_logs rl
        JOIN reminders r ON rl.reminder_id = r.id
        JOIN patients p ON rl.patient_id = p.id
        WHERE rl.patient_id = ?
          AND rl.status = 'pending'
          AND rl.scheduled_time BETWEEN datetime('now', '-2 minutes') AND datetime('now', '+2 minutes')
        ORDER BY rl.scheduled_time ASC
    `).all(patientId);

    res.json(pending);
});

// ═══════════════════════════════════════════════════════════
//  Device API — ESP32 polls for pending reminders
// ═══════════════════════════════════════════════════════════

// GET /api/reminders/device/pending?key=xxx&patient_id=1
router.get('/device/pending', (req, res) => {
    const apiKey = req.headers['x-device-key'] || req.query.key;
    if (apiKey !== process.env.DEVICE_API_KEY) {
        return res.status(401).json({ error: '设备认证失败' });
    }

    const patientId = req.query.patient_id;
    if (!patientId) return res.status(400).json({ error: '缺少 patient_id' });

    const db = req.app.locals.db;

    const pending = db.prepare(`
        SELECT rl.id as log_id, r.title, r.reminder_type, r.dosage, r.description,
               r.schedule_time, p.name as patient_name
        FROM reminder_logs rl
        JOIN reminders r ON rl.reminder_id = r.id
        JOIN patients p ON rl.patient_id = p.id
        WHERE rl.patient_id = ?
          AND rl.status = 'pending'
          AND rl.scheduled_time BETWEEN datetime('now', '-2 minutes') AND datetime('now', '+2 minutes')
        ORDER BY rl.scheduled_time ASC
    `).all(patientId);

    const results = pending.map(r => {
        const typeText = r.reminder_type === 'water' ? '喝水' : '吃药';
        const ttsText = `${r.patient_name}，现在是${r.schedule_time}，该${typeText}了。${r.title}，${r.dosage || ''}。${r.description || ''}`;
        return { ...r, tts_text: ttsText };
    });

    res.json(results);
});

// ═══════════════════════════════════════════════════════════
//  SSE — Real-time reminder push to browser
// ═══════════════════════════════════════════════════════════

// GET /api/reminders/sse?patient_id=all|1|2
// Browser subscribes and keeps connection open; server pushes 'reminder' events
router.get('/sse', authMiddleware, (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no'); // disable nginx buffering
    res.flushHeaders();

    const clientId = `${req.user.id}_${Date.now()}`;
    const patientFilter = req.query.patient_id || 'all';

    sseClients.set(clientId, { res, patientFilter });
    console.log(`📡 [SSE] Client connected: user=${req.user.id} filter=${patientFilter} total=${sseClients.size}`);

    // Heartbeat every 25 s to keep connection alive through proxies
    const heartbeat = setInterval(() => {
        try { res.write(': heartbeat\n\n'); } catch (e) { /* client gone */ }
    }, 25000);

    // Immediately send a 'connected' event
    res.write(`event: connected\ndata: ${JSON.stringify({ ok: true, clientId })}\n\n`);

    req.on('close', () => {
        clearInterval(heartbeat);
        sseClients.delete(clientId);
        console.log(`📡 [SSE] Client disconnected: ${clientId}, remaining=${sseClients.size}`);
    });
});

// ═══════════════════════════════════════════════════════════
//  Generate today's logs for all patients
// ═══════════════════════════════════════════════════════════

// POST /api/reminders/generate-logs  (used by scheduler & manually)
router.post('/generate-logs', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const count = generateTodayLogs(db);
    res.json({ message: `已生成 ${count} 条今日提醒日志` });
});

// ═══════════════════════════════════════════════════════════
//  Helper functions (exported to server.js scheduler)
// ═══════════════════════════════════════════════════════════

function generateTodayLogs(db) {
    const reminders = db.prepare('SELECT * FROM reminders WHERE is_active = 1').all();
    let count = 0;
    const today = new Date();

    for (const r of reminders) {
        const [hh, mm] = r.schedule_time.split(':');
        const scheduledTime = new Date(today.getFullYear(), today.getMonth(), today.getDate(), parseInt(hh), parseInt(mm));
        const isoTime = scheduledTime.toISOString();

        const exists = db.prepare(`
            SELECT id FROM reminder_logs
            WHERE reminder_id = ? AND date(scheduled_time) = date('now')
        `).get(r.id);

        if (!exists) {
            db.prepare(`
                INSERT INTO reminder_logs (reminder_id, patient_id, scheduled_time, status)
                VALUES (?, ?, ?, 'pending')
            `).run(r.id, r.patient_id, isoTime);
            count++;
        }
    }
    return count;
}

// Mark overdue pending logs as 'missed' (called every minute by server.js)
function markMissedLogs(db) {
    const result = db.prepare(`
        UPDATE reminder_logs
        SET status = 'missed'
        WHERE status = 'pending'
          AND scheduled_time < datetime('now', '-10 minutes')
          AND date(scheduled_time) = date('now')
    `).run();
    return result.changes;
}

// ═══════════════════════════════════════════════════════════
//  broadcastPendingReminders — called every minute by server.js
//  Finds reminders due RIGHT NOW (±30 s window), calls TTS,
//  pushes audio+text to all connected SSE browser clients,
//  and marks each log as 'notified'.
// ═══════════════════════════════════════════════════════════
async function broadcastPendingReminders(db, callTTS) {
    const dueLogs = db.prepare(`
        SELECT rl.id as log_id, rl.patient_id,
               r.title, r.reminder_type, r.dosage, r.description, r.schedule_time,
               p.name as patient_name
        FROM reminder_logs rl
        JOIN reminders r ON rl.reminder_id = r.id
        JOIN patients p ON rl.patient_id = p.id
        WHERE rl.status = 'pending'
          AND rl.scheduled_time BETWEEN datetime('now', '-30 seconds') AND datetime('now', '+30 seconds')
    `).all();

    if (dueLogs.length === 0) return;

    console.log(`⏰ [Reminder] ${dueLogs.length} reminder(s) due now — broadcasting...`);

    for (const log of dueLogs) {
        const typeText = log.reminder_type === 'medication' ? '吃药' : '喝水';
        const dosageText = log.dosage ? `，${log.dosage}` : '';
        const descText  = log.description ? `。${log.description}` : '';
        const ttsText   = `${log.patient_name}，现在是${log.schedule_time}，该${typeText}了。${log.title}${dosageText}${descText}`;

        // Mark as 'notified' IMMEDIATELY so it won't fire again next tick
        db.prepare(`UPDATE reminder_logs SET status = 'notified', completed_at = CURRENT_TIMESTAMP WHERE id = ?`)
            .run(log.log_id);

        // Build SSE payload
        const payload = {
            log_id:        log.log_id,
            patient_id:    log.patient_id,
            patient_name:  log.patient_name,
            reminder_type: log.reminder_type,
            title:         log.title,
            dosage:        log.dosage,
            schedule_time: log.schedule_time,
            tts_text:      ttsText,
            audio_base64:  null          // populated below if TTS succeeds
        };

        // Generate TTS audio (non-fatal if API fails)
        try {
            if (typeof callTTS === 'function') {
                payload.audio_base64 = await callTTS(ttsText);
                console.log(`🔊 [Reminder-TTS] Audio generated: "${ttsText.substring(0, 40)}..."`);
            }
        } catch (ttsErr) {
            console.error(`[Reminder-TTS] fallback to browser speechSynthesis: ${ttsErr.message}`);
        }

        // Push to all matching SSE clients
        const eventData = `event: reminder\ndata: ${JSON.stringify(payload)}\n\n`;
        let pushed = 0;
        for (const [cid, client] of sseClients.entries()) {
            const match = client.patientFilter === 'all' ||
                          String(client.patientFilter) === String(log.patient_id);
            if (match) {
                try {
                    client.res.write(eventData);
                    pushed++;
                } catch (e) {
                    sseClients.delete(cid); // stale / disconnected client
                }
            }
        }
        console.log(`📡 [SSE] Reminder pushed to ${pushed} client(s) for patient "${log.patient_name}"`);
    }
}

// ─── Exports ───────────────────────────────────────────────
router.generateTodayLogs         = generateTodayLogs;
router.markMissedLogs            = markMissedLogs;
router.broadcastPendingReminders = broadcastPendingReminders;

module.exports = router;
