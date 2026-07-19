const express = require('express');
const router = express.Router();
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');

// POST /api/auth/login
router.post('/login', (req, res) => {
    const { username, password } = req.body;
    if (!username || !password) {
        return res.status(400).json({ error: '请输入用户名和密码' });
    }

    const db = req.app.locals.db;
    const user = db.prepare('SELECT * FROM users WHERE username = ?').get(username);
    if (!user) {
        return res.status(401).json({ error: '用户名或密码错误' });
    }

    if (!bcrypt.compareSync(password, user.password)) {
        return res.status(401).json({ error: '用户名或密码错误' });
    }

    // Get patient info if applicable
    let patient = null;
    if (user.role === 'patient') {
        patient = db.prepare('SELECT * FROM patients WHERE user_id = ?').get(user.id);
    }

    const token = jwt.sign(
        { id: user.id, username: user.username, role: user.role, real_name: user.real_name, patient_id: patient?.id },
        process.env.JWT_SECRET,
        { expiresIn: '7d' }
    );

    res.json({
        token,
        user: {
            id: user.id,
            username: user.username,
            role: user.role,
            real_name: user.real_name,
            patient_id: patient?.id
        }
    });
});

// POST /api/auth/register
router.post('/register', (req, res) => {
    const { username, password, role, real_name, phone } = req.body;
    if (!username || !password) {
        return res.status(400).json({ error: '请输入用户名和密码' });
    }

    const db = req.app.locals.db;
    const existing = db.prepare('SELECT id FROM users WHERE username = ?').get(username);
    if (existing) {
        return res.status(409).json({ error: '用户名已存在' });
    }

    const hash = bcrypt.hashSync(password, 10);
    const result = db.prepare(
        'INSERT INTO users (username, password, role, real_name, phone) VALUES (?, ?, ?, ?, ?)'
    ).run(username, hash, role || 'patient', real_name || username, phone || '');

    res.status(201).json({ id: result.lastInsertRowid, message: '注册成功' });
});

// GET /api/auth/me
const { authMiddleware } = require('../middleware/auth');
router.get('/me', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const user = db.prepare('SELECT id, username, role, real_name, phone, created_at FROM users WHERE id = ?').get(req.user.id);
    if (!user) return res.status(404).json({ error: '用户不存在' });

    let patient = null;
    if (user.role === 'patient') {
        patient = db.prepare('SELECT * FROM patients WHERE user_id = ?').get(user.id);
    }

    res.json({ user, patient });
});

module.exports = router;
