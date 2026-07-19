require('dotenv').config();
const express = require('express');
const http = require('http');
const { Server: SocketIOServer } = require('socket.io');
const Database = require('better-sqlite3');
const path = require('path');
const cors = require('cors');
const fs = require('fs');

const app = express();
const httpServer = http.createServer(app);
const io = new SocketIOServer(httpServer, { cors: { origin: '*' } });
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.static(path.join(__dirname, 'public')));

// Initialize Database
const dbPath = path.join(__dirname, 'db', 'nursing.db');
const db = new Database(dbPath);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

// Run schema
const schema = fs.readFileSync(path.join(__dirname, 'db', 'schema.sql'), 'utf8');
db.exec(schema);

// ─── Migration: vitals.respiration_rate (非接触呼吸率, 2026-07) ───
try {
    const cols = db.prepare('PRAGMA table_info(vitals)').all().map(c => c.name);
    if (!cols.includes('respiration_rate')) {
        db.exec('ALTER TABLE vitals ADD COLUMN respiration_rate REAL');
        console.log('⚙️  Migrated: vitals.respiration_rate column added');
    }
} catch (e) { console.warn('respiration_rate migration:', e.message); }

// ─── Migration: add 'notified' to reminder_logs CHECK constraint ───
// SQLite can't alter CHECK constraints, so we recreate the table if needed.
try {
    db.prepare("INSERT INTO reminder_logs (reminder_id, patient_id, scheduled_time, status) VALUES (0, 0, datetime('now'), 'notified')").run();
    db.prepare("DELETE FROM reminder_logs WHERE reminder_id = 0 AND patient_id = 0").run();
} catch (e) {
    if (e.message && e.message.includes('CHECK constraint')) {
        console.log('⚙️  Migrating reminder_logs table to support notified status...');
        db.exec(`
            PRAGMA foreign_keys = OFF;
            CREATE TABLE reminder_logs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reminder_id INTEGER NOT NULL REFERENCES reminders(id),
                patient_id INTEGER NOT NULL REFERENCES patients(id),
                scheduled_time DATETIME NOT NULL,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending','completed','skipped','missed','notified')),
                completed_at DATETIME,
                note TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO reminder_logs_new SELECT * FROM reminder_logs;
            DROP TABLE reminder_logs;
            ALTER TABLE reminder_logs_new RENAME TO reminder_logs;
            CREATE INDEX IF NOT EXISTS idx_reminder_logs_patient ON reminder_logs(patient_id, scheduled_time);
            CREATE INDEX IF NOT EXISTS idx_reminder_logs_status ON reminder_logs(reminder_id, status);
            PRAGMA foreign_keys = ON;
        `);
        console.log('✅ reminder_logs migration complete');
    }
}

// Check if database needs seeding
const userCount = db.prepare('SELECT COUNT(*) as count FROM users').get();
if (userCount.count === 0) {
    console.log('🌱 Seeding database with demo data...');
    // Hash passwords properly at runtime
    const bcrypt = require('bcryptjs');
    const hash = bcrypt.hashSync('admin123', 10);

    // Seed users
    const insertUser = db.prepare('INSERT INTO users (username, password, role, real_name, phone) VALUES (?, ?, ?, ?, ?)');
    insertUser.run('admin', hash, 'admin', '系统管理员', '13800000000');
    insertUser.run('dr_wang', bcrypt.hashSync('doctor123', 10), 'doctor', '王医生', '13800000001');
    insertUser.run('patient_zhang', bcrypt.hashSync('patient123', 10), 'patient', '张建国', '13800000002');
    insertUser.run('patient_li', bcrypt.hashSync('patient123', 10), 'patient', '李秀芳', '13800000003');
    insertUser.run('patient_wang', bcrypt.hashSync('patient123', 10), 'patient', '王明辉', '13800000004');
    insertUser.run('family_zhang', bcrypt.hashSync('family123', 10), 'family', '张伟（家属）', '13800000005');

    // Run seed SQL for other data
    const seed = fs.readFileSync(path.join(__dirname, 'db', 'seed.sql'), 'utf8');
    // Filter out user inserts from seed (already done above)
    const seedStatements = seed.split(';').filter(s => s.trim() && !s.includes('INSERT INTO users'));
    for (const stmt of seedStatements) {
        try {
            db.exec(stmt + ';');
        } catch (e) {
            // Skip individual statement errors
        }
    }
    console.log('✅ Database seeded successfully!');
}

// Make db and io available to routes
app.locals.db = db;
app.locals.io = io;

// Routes
app.use('/api/auth', require('./routes/auth'));
app.use('/api/patients', require('./routes/patients'));
app.use('/api/vitals', require('./routes/vitals'));
app.use('/api/reports', require('./routes/reports'));
app.use('/api/alerts', require('./routes/alerts'));
app.use('/api/agents', require('./routes/agents'));
const voiceRoute = require('./routes/voice');
app.use('/api/voice', voiceRoute);
app.use('/api/pressure', require('./routes/pressure'));
app.use('/api/emotion', require('./routes/emotion'));
const remindersRoute = require('./routes/reminders');
app.use('/api/reminders', remindersRoute);

// ─── WebSocket 语音流式交互 ───
const { setupVoiceStream } = require('./routes/voiceStream');
const WsServer = require('ws').Server;
const voiceWss = new WsServer({ server: httpServer, path: '/ws/voice-stream' });
setupVoiceStream(voiceWss, db);
console.log('🎙️ Voice streaming WebSocket mounted at /ws/voice-stream');

// Device register: Pi启动时主动上报IP (不依赖传感器数据)
app.post('/api/device/register', (req, res) => {
    const { patient_id, ip } = req.body;
    const deviceIp = ip
        || req.headers['x-forwarded-for']?.split(',')[0].trim()
        || req.socket.remoteAddress?.replace('::ffff:', '');
    if (!req.app.locals.deviceIps) req.app.locals.deviceIps = {};
    if (deviceIp) {
        const pid = patient_id || 1;
        req.app.locals.deviceIps[pid] = deviceIp;
        console.log(`[Device] patient ${pid} registered IP: ${deviceIp}`);
    }
    res.json({ ok: true, ip: deviceIp });
});

// Device info: 按patient_id返回摄像头URL (供前端按当前患者自动发现)
app.get('/api/device/info', (req, res) => {
    const { patient_id } = req.query;
    const ips = req.app.locals.deviceIps || {};
    let ip = null;
    if (patient_id && ips[patient_id]) {
        ip = ips[patient_id];
    } else {
        // 任意可用IP兜底
        const vals = Object.values(ips);
        if (vals.length > 0) ip = vals[vals.length - 1];
    }
    res.json({
        device_ip: ip,
        camera_url: ip ? `http://${ip}:8080/stream` : null,
        camera_snapshot: ip ? `http://${ip}:8080/snapshot` : null,
    });
});

// Camera snapshot proxy: 云端代理Pi摄像头快照，避免浏览器CORS/私有网络访问限制
app.get('/api/camera/frame', async (req, res) => {
    const { patient_id } = req.query;
    const ips = req.app.locals.deviceIps || {};
    let ip = (patient_id && ips[patient_id]) || Object.values(ips).slice(-1)[0] || null;

    if (!ip) return res.status(503).json({ error: 'No device registered' });

    try {
        const http = require('http');
        const snapshotUrl = `http://${ip}:8080/snapshot`;
        await new Promise((resolve, reject) => {
            const proxyReq = http.get(snapshotUrl, { timeout: 3000 }, (piRes) => {
                if (piRes.statusCode !== 200) { reject(new Error('Pi camera: ' + piRes.statusCode)); return; }
                res.setHeader('Content-Type', 'image/jpeg');
                res.setHeader('Cache-Control', 'no-store');
                piRes.pipe(res);
                piRes.on('end', resolve);
            });
            proxyReq.on('error', reject);
            proxyReq.on('timeout', () => { proxyReq.destroy(); reject(new Error('timeout')); });
        });
    } catch (e) {
        if (!res.headersSent) res.status(502).json({ error: e.message });
    }
});

app.get('*', (req, res) => {
    if (!req.path.startsWith('/api')) {
        res.sendFile(path.join(__dirname, 'public', 'index.html'));
    }
});

// Error handler
app.use((err, req, res, next) => {
    console.error('❌ Error:', err.message);
    res.status(500).json({ error: '服务器内部错误', detail: err.message });
});

httpServer.listen(PORT, '0.0.0.0', () => {
    console.log(`
    🏥 ═══════════════════════════════════════════
    ║  智能护理病床云平台 (Smart Nursing Bed)
    ║  Server running on http://0.0.0.0:${PORT}
    ║  Database: ${dbPath}
    ║  LLM: ${process.env.KIMI_MODEL || 'kimi-k2.5'}
    🏥 ═══════════════════════════════════════════
    `);

    // ─── Reminder Schedulers ───
    // Generate today's reminder logs on startup
    try {
        const n = remindersRoute.generateTodayLogs(db);
        if (n > 0) console.log(`⏰ Generated ${n} reminder logs for today`);
    } catch (e) { console.error('Reminder log generation error:', e.message); }

    // Every minute: ① broadcast due reminders via TTS+SSE  ② mark overdue as missed
    const callTTS = voiceRoute.callCosyVoiceTTS;
    setInterval(async () => {
        try {
            await remindersRoute.broadcastPendingReminders(db, callTTS);
        } catch (e) { console.error('Broadcast reminder error:', e.message); }
        try { remindersRoute.markMissedLogs(db); } catch (e) { /* ignore */ }
    }, 60 * 1000);

    // Daily at midnight: generate next day's logs
    function scheduleDaily() {
        const now = new Date();
        const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 1, 0);
        const ms = tomorrow.getTime() - now.getTime();
        setTimeout(() => {
            try {
                const n = remindersRoute.generateTodayLogs(db);
                console.log(`⏰ [Daily] Generated ${n} reminder logs`);
            } catch (e) { console.error('Daily reminder error:', e.message); }
            scheduleDaily(); // reschedule
        }, ms);
    }
    scheduleDaily();
});

module.exports = app;
