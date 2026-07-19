const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../middleware/auth');

// GET /api/alerts - List alerts
router.get('/', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { status, patient_id, limit = 50 } = req.query;

    let query = `
        SELECT a.*, p.name as patient_name, p.bed_number, p.room_number
        FROM alerts a JOIN patients p ON a.patient_id = p.id
    `;
    const conditions = [];
    const params = [];

    if (status) {
        conditions.push('a.status = ?');
        params.push(status);
    }

    if (patient_id) {
        conditions.push('a.patient_id = ?');
        params.push(patient_id);
    }

    // Patients can only see their own alerts
    if (req.user.role === 'patient' && req.user.patient_id) {
        conditions.push('a.patient_id = ?');
        params.push(req.user.patient_id);
    }

    if (conditions.length > 0) {
        query += ' WHERE ' + conditions.join(' AND ');
    }

    query += ' ORDER BY a.created_at DESC LIMIT ?';
    params.push(parseInt(limit));

    const alerts = db.prepare(query).all(...params);
    res.json(alerts);
});

// GET /api/alerts/active-count
router.get('/active-count', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    let query = "SELECT COUNT(*) as count FROM alerts WHERE status = 'active'";

    if (req.user.role === 'patient' && req.user.patient_id) {
        query += ` AND patient_id = ${req.user.patient_id}`;
    }

    const result = db.prepare(query).get();
    res.json({ count: result.count });
});

// POST /api/alerts — 护士站(JWT) 或 设备直通(X-API-Key, 语音SOS等)
const deviceOrAuth = (req, res, next) => {
    if (req.headers['x-api-key'] && req.headers['x-api-key'] === process.env.DEVICE_API_KEY) return next();
    return authMiddleware(req, res, next);
};
router.post('/', deviceOrAuth, (req, res) => {
    const db = req.app.locals.db;
    const { patient_id, alert_type, metric, value, threshold, message } = req.body;

    const result = db.prepare(`
        INSERT INTO alerts (patient_id, alert_type, metric, value, threshold, message)
        VALUES (?, ?, ?, ?, ?, ?)
    `).run(patient_id, alert_type, metric, value, threshold, message);

    // 实时推送 (SOS等即时弹到所有已连接的护士站页面)
    const io = req.app.locals.io;
    if (io) io.emit('alert_new', {
        id: result.lastInsertRowid, patient_id, alert_type, metric, message,
        created_at: new Date().toISOString()
    });

    res.status(201).json({ id: result.lastInsertRowid, message: '报警已创建' });
});

// PUT /api/alerts/:id/acknowledge
router.put('/:id/acknowledge', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    db.prepare("UPDATE alerts SET status = 'acknowledged' WHERE id = ?").run(req.params.id);
    res.json({ message: '已确认' });
});

// PUT /api/alerts/:id/resolve
router.put('/:id/resolve', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    db.prepare("UPDATE alerts SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP WHERE id = ?").run(req.params.id);
    res.json({ message: '已解除' });
});

module.exports = router;
