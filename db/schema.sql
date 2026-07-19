-- Smart Nursing Bed Database Schema

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'patient' CHECK(role IN ('patient', 'doctor', 'admin', 'family')),
    real_name TEXT,
    phone TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    name TEXT NOT NULL,
    age INTEGER,
    gender TEXT CHECK(gender IN ('男', '女')),
    bed_number TEXT,
    room_number TEXT,
    disease_type TEXT NOT NULL,
    disease_detail TEXT,
    admission_date DATE,
    assigned_agent TEXT NOT NULL DEFAULT 'general',
    emergency_contact TEXT,
    emergency_phone TEXT,
    avatar_url TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vitals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    heart_rate REAL,
    blood_pressure_sys REAL,
    blood_pressure_dia REAL,
    blood_oxygen REAL,
    blood_glucose REAL,
    temperature REAL,
    sleep_posture TEXT,
    temperature_grid TEXT,
    fabric_sensor_raw TEXT,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    report_date DATE NOT NULL,
    report_type TEXT DEFAULT 'daily' CHECK(report_type IN ('daily', 'weekly', 'monthly')),
    summary TEXT,
    vital_stats TEXT,
    ai_diagnosis TEXT,
    rehab_suggestions TEXT,
    risk_assessment TEXT,
    generated_by TEXT DEFAULT 'kimi-k2.5',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    alert_type TEXT NOT NULL CHECK(alert_type IN ('critical', 'warning', 'info')),
    metric TEXT NOT NULL,
    value REAL,
    threshold TEXT,
    message TEXT NOT NULL,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'acknowledged', 'resolved')),
    resolved_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    disease_type TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    vital_thresholds TEXT,
    description TEXT,
    icon TEXT DEFAULT '🏥',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS voice_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS patient_concerns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    top_concerns TEXT,
    emotional_state TEXT,
    physical_complaints TEXT,
    needs TEXT,
    summary TEXT,
    conversation_count INTEGER DEFAULT 0,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS emotion_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    text_input TEXT,
    primary_emotion TEXT DEFAULT 'unknown',
    emotion_intensity REAL DEFAULT 0.5,
    valence REAL DEFAULT 0,
    arousal REAL DEFAULT 0.5,
    risk_indicators TEXT,
    analysis_json TEXT,
    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS voice_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    text_input TEXT,
    parsed_action TEXT,
    parsed_params TEXT,
    reply TEXT,
    executed INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_vitals_patient_time ON vitals(patient_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_reports_patient_date ON reports(patient_id, report_date);
CREATE INDEX IF NOT EXISTS idx_alerts_patient_status ON alerts(patient_id, status);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_emotion_patient ON emotion_records(patient_id, analyzed_at);
CREATE INDEX IF NOT EXISTS idx_voice_commands_patient ON voice_commands(patient_id, created_at);

-- Smart Reminders (water / medicine)
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    reminder_type TEXT NOT NULL CHECK(reminder_type IN ('water', 'medicine', 'medication')),
    title TEXT NOT NULL,
    description TEXT,
    schedule_time TEXT NOT NULL,
    dosage TEXT,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reminder_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id INTEGER NOT NULL REFERENCES reminders(id),
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    scheduled_time DATETIME NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed', 'skipped', 'missed', 'notified')),
    completed_at DATETIME,
    note TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reminders_patient ON reminders(patient_id, is_active);
CREATE INDEX IF NOT EXISTS idx_reminder_logs_patient ON reminder_logs(patient_id, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_reminder_logs_status ON reminder_logs(reminder_id, status);
