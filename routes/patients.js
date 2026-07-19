const express = require('express');
const router = express.Router();
const { authMiddleware, adminOnly } = require('../middleware/auth');

// GET /api/patients - list all patients (doctor/admin)
router.get('/', authMiddleware, (req, res) => {
    const db = req.app.locals.db;

    if (req.user.role === 'patient') {
        // Patients can only see themselves
        const patient = db.prepare('SELECT * FROM patients WHERE user_id = ?').get(req.user.id);
        return res.json(patient ? [patient] : []);
    }

    if (req.user.role === 'family') {
        // Family members see patients linked by emergency_phone match or all patients for demo
        const familyUser = db.prepare('SELECT phone FROM users WHERE id = ?').get(req.user.id);
        let patients = [];
        if (familyUser && familyUser.phone) {
            patients = db.prepare('SELECT * FROM patients WHERE emergency_phone = ?').all(familyUser.phone);
        }
        // Fallback: if no phone match, show all patients (demo mode)
        if (patients.length === 0) {
            patients = db.prepare('SELECT * FROM patients').all();
        }
        return res.json(patients);
    }

    const patients = db.prepare(`
        SELECT p.*, u.username, u.real_name as user_real_name,
        (SELECT COUNT(*) FROM alerts WHERE patient_id = p.id AND status = 'active') as active_alerts
        FROM patients p LEFT JOIN users u ON p.user_id = u.id
        ORDER BY p.room_number, p.bed_number
    `).all();

    res.json(patients);
});

// GET /api/patients/:id
router.get('/:id', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const patient = db.prepare(`
        SELECT p.*, u.username, u.real_name as user_real_name
        FROM patients p LEFT JOIN users u ON p.user_id = u.id
        WHERE p.id = ?
    `).get(req.params.id);

    if (!patient) return res.status(404).json({ error: '患者不存在' });

    // Patients can only view their own data
    if (req.user.role === 'patient' && patient.user_id !== req.user.id) {
        return res.status(403).json({ error: '无权访问该患者信息' });
    }

    // Get latest vitals
    const latestVitals = db.prepare(
        'SELECT * FROM vitals WHERE patient_id = ? ORDER BY recorded_at DESC LIMIT 1'
    ).get(patient.id);

    // Get active alerts count
    const alertCount = db.prepare(
        "SELECT COUNT(*) as count FROM alerts WHERE patient_id = ? AND status = 'active'"
    ).get(patient.id);

    // Get agent config
    const agent = db.prepare(
        'SELECT * FROM agent_configs WHERE agent_name = ?'
    ).get(patient.assigned_agent);

    res.json({ patient, latestVitals, activeAlerts: alertCount.count, agent });
});

// POST /api/patients (admin/doctor only)
router.post('/', authMiddleware, adminOnly, (req, res) => {
    const db = req.app.locals.db;
    const { user_id, name, age, gender, bed_number, room_number, disease_type, disease_detail, assigned_agent, emergency_contact, emergency_phone } = req.body;

    const result = db.prepare(`
        INSERT INTO patients (user_id, name, age, gender, bed_number, room_number, disease_type, disease_detail, admission_date, assigned_agent, emergency_contact, emergency_phone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, date('now'), ?, ?, ?)
    `).run(user_id, name, age, gender, bed_number, room_number, disease_type, disease_detail || '', assigned_agent || 'general', emergency_contact || '', emergency_phone || '');

    res.status(201).json({ id: result.lastInsertRowid, message: '患者添加成功' });
});

// PUT /api/patients/:id
router.put('/:id', authMiddleware, adminOnly, (req, res) => {
    const db = req.app.locals.db;
    const fields = req.body;
    const updates = [];
    const values = [];

    for (const [key, value] of Object.entries(fields)) {
        if (['name', 'age', 'gender', 'bed_number', 'room_number', 'disease_type', 'disease_detail', 'assigned_agent', 'emergency_contact', 'emergency_phone'].includes(key)) {
            updates.push(`${key} = ?`);
            values.push(value);
        }
    }

    if (updates.length === 0) return res.status(400).json({ error: '没有可更新的字段' });

    updates.push('updated_at = CURRENT_TIMESTAMP');
    values.push(req.params.id);

    db.prepare(`UPDATE patients SET ${updates.join(', ')} WHERE id = ?`).run(...values);
    res.json({ message: '更新成功' });
});

module.exports = router;
