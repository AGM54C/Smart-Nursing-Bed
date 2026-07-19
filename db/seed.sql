-- Seed Data for Smart Nursing Bed Demo

-- Admin user (password: admin123)
INSERT INTO users (username, password, role, real_name, phone) VALUES
('admin', '$2a$10$XK1OVHzOMwR5E5v4Q3v9z.7mH5T7a3KRfY4e9V5w0UqK8k5v8m5Ky', 'admin', '系统管理员', '13800000000');

-- Doctor user (password: doctor123)
INSERT INTO users (username, password, role, real_name, phone) VALUES
('dr_wang', '$2a$10$XK1OVHzOMwR5E5v4Q3v9z.7mH5T7a3KRfY4e9V5w0UqK8k5v8m5Ky', 'doctor', '王医生', '13800000001');

-- Patient users (password: patient123)
INSERT INTO users (username, password, role, real_name, phone) VALUES
('patient_zhang', '$2a$10$XK1OVHzOMwR5E5v4Q3v9z.7mH5T7a3KRfY4e9V5w0UqK8k5v8m5Ky', 'patient', '张建国', '13800000002'),
('patient_li', '$2a$10$XK1OVHzOMwR5E5v4Q3v9z.7mH5T7a3KRfY4e9V5w0UqK8k5v8m5Ky', 'patient', '李秀芳', '13800000003'),
('patient_wang', '$2a$10$XK1OVHzOMwR5E5v4Q3v9z.7mH5T7a3KRfY4e9V5w0UqK8k5v8m5Ky', 'patient', '王明辉', '13800000004');

-- Family member user (password: family123)
INSERT INTO users (username, password, role, real_name, phone) VALUES
('family_zhang', '$2a$10$XK1OVHzOMwR5E5v4Q3v9z.7mH5T7a3KRfY4e9V5w0UqK8k5v8m5Ky', 'family', '张伟（家属）', '13800000005');

-- Patients
INSERT INTO patients (user_id, name, age, gender, bed_number, room_number, disease_type, disease_detail, admission_date, assigned_agent, emergency_contact, emergency_phone) VALUES
(3, '张建国', 62, '男', 'A-101', '101', '高位截瘫', '车祸后C4-C5脊髓损伤，四肢瘫痪，需长期护理及康复训练', '2026-01-15', 'quadriplegia', '张伟', '13800000005'),
(4, '李秀芳', 58, '女', 'A-102', '101', '糖尿病', 'II型糖尿病合并高血压，需监控血糖/血压并定期用药', '2026-02-01', 'diabetes', '李强', '13800000006'),
(5, '王明辉', 71, '男', 'B-201', '201', '中风后遗症', '脑梗后遗症，左侧偏瘫，需康复理疗', '2026-01-20', 'post_stroke', '王芳', '13800000007');

-- Agent Configurations
INSERT INTO agent_configs (agent_name, display_name, disease_type, system_prompt, vital_thresholds, description, icon) VALUES
('quadriplegia', '高位截瘫护理Agent', '高位截瘫', '你是一位专业的高位截瘫护理AI助手。你的患者因脊髓损伤导致四肢瘫痪，需要全面的生命体征监护。你需要特别关注以下方面：
1. 体温监测：截瘫患者体温调节能力受损，需密切关注体温变化和散热问题
2. 血压管理：注意体位性低血压和自主神经过反射的风险
3. 呼吸功能：高位截瘫影响呼吸肌，需监控血氧饱和度
4. 体位护理管理：通过织物传感器的睡姿监测，建议定时翻身以减轻局部受压
5. 心率监测：注意心动过缓等自主神经功能障碍
6. 康复建议：制定合理的被动运动和康复训练方案
请根据患者的生命体征数据，给出专业的护理建议和风险评估。使用中文回答，语气温和专业。', 
'{"heart_rate_min":45,"heart_rate_max":110,"blood_oxygen_min":92,"temperature_min":35.5,"temperature_max":38.0,"bp_sys_max":160,"bp_dia_max":100}',
'专为高位截瘫患者设计的AI护理助手，重点关注体温调节、受压监测与体位护理、呼吸功能和自主神经管理', '🦽'),

('diabetes', '糖尿病管理Agent', '糖尿病', '你是一位专业的糖尿病管理AI助手。你负责监护II型糖尿病患者的健康状况。你需要特别关注：
1. 血糖监测：关注空腹血糖、餐后血糖波动，识别低血糖和高血糖事件
2. 血压管理：糖尿病合并高血压的联合管理，目标血压<130/80mmHg
3. 心血管风险：监测心率异常，评估心血管并发症风险
4. 体温监测：关注感染风险，糖尿病患者感染恢复较慢
5. 足部和皮肤：通过织物传感器监测体表温度分布，预防糖尿病足
6. 饮食和运动：根据血糖趋势给出饮食调整和运动建议
请用通俗易懂的中文给出建议，帮助患者及家属理解病情变化。',
'{"heart_rate_min":50,"heart_rate_max":120,"blood_oxygen_min":93,"blood_glucose_min":3.9,"blood_glucose_max":11.1,"temperature_max":37.5,"bp_sys_max":140,"bp_dia_max":90}',
'针对II型糖尿病患者的智能管理助手，综合管理血糖、血压和并发症风险', '💉'),

('post_stroke', '中风康复Agent', '中风后遗症', '你是一位专业的中风后康复AI助手。你负责协助中风后遗症患者（偏瘫）的康复管理。你需要特别关注：
1. 血压控制：中风后血压管理至关重要，目标<140/90mmHg，避免剧烈波动
2. 心率监测：房颤等心律失常是中风复发的重要风险因素
3. 血氧监测：注意吞咽困难导致的误吸风险
4. 睡姿监测：通过织物传感器确保患侧肢体正确摆放，预防关节挛缩
5. 体温监测：发热可能提示感染或中风复发
6. 康复进展：根据日常活动数据评估康复进展，调整训练方案
7. 情绪管理：关注患者情绪变化，中风后抑郁很常见
请使用温暖亲切的中文回应，鼓励患者积极康复。',
'{"heart_rate_min":50,"heart_rate_max":110,"blood_oxygen_min":94,"temperature_max":37.8,"bp_sys_min":90,"bp_sys_max":150,"bp_dia_max":95}',
'专注中风后遗症康复管理，涵盖血压控制、康复训练和二次预防', '🧠'),

('copd', 'COPD呼吸管理Agent', '慢性阻塞性肺疾病', '你是一位专业的COPD（慢性阻塞性肺疾病）管理AI助手。你需要特别关注：
1. 血氧监测：COPD患者血氧至关重要，SpO2<88%需立即干预
2. 呼吸频率：通过织物传感器的胸腹运动监测呼吸模式
3. 体温监测：发热提示急性加重或肺部感染
4. 心率监测：肺心病导致的右心功能不全风险
5. 睡姿管理：推荐半卧位或侧卧位以改善通气
6. 用药提醒：吸入剂使用和按时用药
请优先关注呼吸相关指标，用简洁明了的中文给出建议。',
'{"heart_rate_min":50,"heart_rate_max":120,"blood_oxygen_min":88,"temperature_max":37.5,"bp_sys_max":160,"bp_dia_max":100}',
'COPD患者专属呼吸管理助手，重点监护血氧和呼吸功能', '🫁'),

('general', '通用护理Agent', '一般护理', '你是一位全科护理AI助手，负责一般慢性病患者的日常健康监护。你需要：
1. 综合监测：心率、血压、血氧、体温、血糖等全方位健康指标
2. 趋势分析：识别指标变化趋势，及时预警
3. 生活建议：给出饮食、运动、作息等日常建议
4. 康复指导：根据患者具体情况给出康复建议
5. 织物传感器数据：分析体温分布和睡姿，优化睡眠质量
请用温和专业的中文回答，注重整体健康管理。',
'{"heart_rate_min":50,"heart_rate_max":120,"blood_oxygen_min":93,"temperature_max":37.5,"bp_sys_max":140,"bp_dia_max":90}',
'通用全科护理智能助手，适用于各类慢性病患者的日常健康管理', '🏥');

-- Generate demo vitals data for patient 1 (张建国 - Quadriplegia) - last 7 days
INSERT INTO vitals (patient_id, heart_rate, blood_pressure_sys, blood_pressure_dia, blood_oxygen, blood_glucose, temperature, sleep_posture, recorded_at) VALUES
(1, 68, 118, 72, 96, 5.2, 36.4, '仰卧', datetime('now', '-7 days', '+8 hours')),
(1, 72, 122, 75, 95, 5.5, 36.6, '左侧卧', datetime('now', '-7 days', '+14 hours')),
(1, 65, 115, 70, 97, 5.0, 36.3, '仰卧', datetime('now', '-6 days', '+8 hours')),
(1, 70, 120, 73, 96, 5.3, 36.5, '右侧卧', datetime('now', '-6 days', '+14 hours')),
(1, 67, 125, 78, 94, 5.4, 36.7, '仰卧', datetime('now', '-5 days', '+8 hours')),
(1, 74, 130, 82, 93, 5.6, 37.0, '仰卧', datetime('now', '-5 days', '+14 hours')),
(1, 66, 118, 72, 96, 5.1, 36.4, '左侧卧', datetime('now', '-4 days', '+8 hours')),
(1, 71, 121, 74, 95, 5.3, 36.5, '仰卧', datetime('now', '-4 days', '+14 hours')),
(1, 69, 119, 73, 97, 5.2, 36.3, '右侧卧', datetime('now', '-3 days', '+8 hours')),
(1, 73, 123, 76, 96, 5.4, 36.6, '仰卧', datetime('now', '-3 days', '+14 hours')),
(1, 68, 117, 71, 96, 5.1, 36.4, '仰卧', datetime('now', '-2 days', '+8 hours')),
(1, 75, 126, 79, 95, 5.5, 36.8, '左侧卧', datetime('now', '-2 days', '+14 hours')),
(1, 67, 119, 73, 97, 5.2, 36.3, '仰卧', datetime('now', '-1 days', '+8 hours')),
(1, 70, 122, 75, 96, 5.3, 36.5, '右侧卧', datetime('now', '-1 days', '+14 hours')),
(1, 69, 120, 74, 96, 5.2, 36.5, '仰卧', datetime('now', '+8 hours'));

-- Generate demo vitals for patient 2 (李秀芳 - Diabetes)
INSERT INTO vitals (patient_id, heart_rate, blood_pressure_sys, blood_pressure_dia, blood_oxygen, blood_glucose, temperature, sleep_posture, recorded_at) VALUES
(2, 78, 142, 88, 97, 8.2, 36.5, '仰卧', datetime('now', '-7 days', '+8 hours')),
(2, 82, 148, 92, 96, 12.5, 36.7, '仰卧', datetime('now', '-7 days', '+14 hours')),
(2, 76, 138, 85, 97, 7.8, 36.4, '右侧卧', datetime('now', '-6 days', '+8 hours')),
(2, 80, 145, 90, 96, 11.8, 36.6, '仰卧', datetime('now', '-6 days', '+14 hours')),
(2, 77, 140, 87, 97, 7.5, 36.5, '仰卧', datetime('now', '-5 days', '+8 hours')),
(2, 83, 150, 94, 96, 13.2, 36.8, '左侧卧', datetime('now', '-5 days', '+14 hours')),
(2, 75, 136, 84, 98, 7.2, 36.3, '仰卧', datetime('now', '-4 days', '+8 hours')),
(2, 81, 144, 89, 97, 11.5, 36.6, '仰卧', datetime('now', '-4 days', '+14 hours')),
(2, 78, 139, 86, 97, 7.9, 36.5, '右侧卧', datetime('now', '-3 days', '+8 hours')),
(2, 79, 143, 88, 96, 10.8, 36.7, '仰卧', datetime('now', '-3 days', '+14 hours')),
(2, 76, 137, 85, 97, 7.6, 36.4, '仰卧', datetime('now', '-2 days', '+8 hours')),
(2, 84, 146, 91, 96, 12.1, 36.8, '仰卧', datetime('now', '-2 days', '+14 hours')),
(2, 77, 138, 86, 98, 7.4, 36.3, '左侧卧', datetime('now', '-1 days', '+8 hours')),
(2, 80, 141, 87, 97, 11.2, 36.6, '仰卧', datetime('now', '-1 days', '+14 hours')),
(2, 78, 140, 87, 97, 8.0, 36.5, '仰卧', datetime('now', '+8 hours'));

-- Generate demo vitals for patient 3 (王明辉 - Post-stroke)
INSERT INTO vitals (patient_id, heart_rate, blood_pressure_sys, blood_pressure_dia, blood_oxygen, blood_glucose, temperature, sleep_posture, recorded_at) VALUES
(3, 72, 135, 82, 96, 5.8, 36.6, '仰卧', datetime('now', '-7 days', '+8 hours')),
(3, 76, 140, 86, 95, 6.2, 36.8, '仰卧', datetime('now', '-7 days', '+14 hours')),
(3, 70, 132, 80, 97, 5.5, 36.5, '右侧卧', datetime('now', '-6 days', '+8 hours')),
(3, 74, 138, 84, 96, 6.0, 36.7, '仰卧', datetime('now', '-6 days', '+14 hours')),
(3, 71, 134, 82, 96, 5.7, 36.6, '仰卧', datetime('now', '-5 days', '+8 hours')),
(3, 77, 142, 88, 95, 6.4, 36.9, '左侧卧', datetime('now', '-5 days', '+14 hours')),
(3, 69, 130, 79, 97, 5.4, 36.4, '仰卧', datetime('now', '-4 days', '+8 hours')),
(3, 75, 139, 85, 96, 6.1, 36.7, '仰卧', datetime('now', '-4 days', '+14 hours')),
(3, 71, 133, 81, 96, 5.6, 36.5, '右侧卧', datetime('now', '-3 days', '+8 hours')),
(3, 73, 137, 83, 96, 5.9, 36.7, '仰卧', datetime('now', '-3 days', '+14 hours')),
(3, 70, 131, 80, 97, 5.5, 36.4, '仰卧', datetime('now', '-2 days', '+8 hours')),
(3, 76, 141, 87, 95, 6.3, 36.9, '仰卧', datetime('now', '-2 days', '+14 hours')),
(3, 72, 134, 82, 96, 5.7, 36.6, '左侧卧', datetime('now', '-1 days', '+8 hours')),
(3, 74, 138, 84, 96, 6.0, 36.7, '仰卧', datetime('now', '-1 days', '+14 hours')),
(3, 72, 136, 83, 96, 5.8, 36.6, '仰卧', datetime('now', '+8 hours'));

-- Demo reports
INSERT INTO reports (patient_id, report_date, report_type, summary, vital_stats, ai_diagnosis, rehab_suggestions, risk_assessment) VALUES
(1, date('now', '-1 days'), 'daily', 
'张建国（62岁）今日整体生命体征稳定。心率维持在65-75bpm之间，血压平稳，血氧饱和度保持在95-97%，体温正常。织物传感器显示夜间翻身频率适中。',
'{"avg_heart_rate":69,"avg_bp":"120/74","avg_spo2":96,"avg_temp":36.5,"avg_glucose":5.3}',
'患者今日各项指标平稳，脊髓损伤后自主神经功能维持在可控范围。血压未见明显体位性低血压发作。呼吸功能通过血氧监测显示稳定。',
'1. 建议继续每2小时辅助翻身一次，预防持续受压\n2. 进行上肢被动关节活动训练，每次15分钟\n3. 配合呼吸训练，增强肺功能\n4. 注意保暖，体温调节功能受损需关注环境温度',
'低风险 - 各项指标正常范围内'),

(2, date('now', '-1 days'), 'daily',
'李秀芳（58岁）今日血糖控制需关注。空腹血糖7.4mmol/L略高，餐后血糖11.2mmol/L超过理想范围。血压142/88mmHg偏高。',
'{"avg_heart_rate":79,"avg_bp":"141/88","avg_spo2":97,"avg_temp":36.5,"avg_glucose":9.3}',
'患者II型糖尿病合并高血压控制欠佳。餐后血糖多次超过10mmol/L，提示当前降糖方案可能需要调整。血压偏高，建议复查降压药物剂量。',
'1. 减少精制碳水化合物摄入，增加蔬菜和高纤维食物\n2. 每日餐后30分钟进行轻度步行15-20分钟\n3. 按时服用降糖和降压药物\n4. 关注足部皮肤状况，织物传感器温度监测有助于早期发现异常',
'中等风险 - 血糖和血压控制需加强'),

(3, date('now', '-1 days'), 'daily',
'王明辉（71岁）今日康复进展良好。血压控制在目标范围内，心率规律无异常。左侧肢体康复训练按计划进行。',
'{"avg_heart_rate":73,"avg_bp":"136/83","avg_spo2":96,"avg_temp":36.6,"avg_glucose":5.8}',
'中风后遗症患者今日各项指标平稳。血压控制在140/90mmHg以下，降低二次中风风险。心律规律，未见房颤表现。',
'1. 继续左侧肢体主动+被动训练，逐步增加难度\n2. 每日步行训练10-15分钟（需辅助）\n3. 语言康复训练每天20分钟\n4. 保持规律作息，织物传感器监测显示睡眠质量可',
'低风险 - 康复稳步推进');

-- Demo alerts
INSERT INTO alerts (patient_id, alert_type, metric, value, threshold, message, status, created_at) VALUES
(2, 'warning', '餐后血糖', 13.2, '>11.1 mmol/L', '⚠️ 李秀芳餐后血糖升至13.2mmol/L，超过预警阈值(11.1)，请关注饮食并考虑调整用药', 'acknowledged', datetime('now', '-5 days', '+14 hours')),
(2, 'warning', '收缩压', 150, '>140 mmHg', '⚠️ 李秀芳收缩压150mmHg，超过糖尿病患者目标血压(140)，请及时处理', 'resolved', datetime('now', '-5 days', '+14 hours')),
(1, 'info', '血氧', 93, '<94%', 'ℹ️ 张建国血氧饱和度降至93%，接近预警值，请注意观察呼吸情况', 'resolved', datetime('now', '-5 days', '+14 hours'));

-- Smart Reminders
INSERT INTO reminders (patient_id, reminder_type, title, description, schedule_time, dosage, is_active, created_by) VALUES
(1, 'water', '晨起饮水', '起床后空腹一杯温水', '07:00', '200ml', 1, 2),
(1, 'medicine', '降压药', '硝苯地平缓释片', '08:00', '1片', 1, 2),
(1, 'water', '上午饮水', '补充水分', '10:00', '200ml', 1, 2),
(1, 'medicine', '营养药', '甲钴胺片', '12:00', '1片', 1, 2),
(1, 'water', '下午饮水', '补充水分', '15:00', '200ml', 1, 2),
(1, 'water', '晚间饮水', '睡前适量饮水', '20:00', '150ml', 1, 2),
(2, 'medicine', '降糖药', '二甲双胍缓释片', '07:30', '1片', 1, 2),
(2, 'water', '餐前饮水', '早餐前一杯水', '07:00', '200ml', 1, 2),
(2, 'medicine', '降压药', '氨氯地平片', '08:00', '1片', 1, 2),
(2, 'medicine', '午间降糖药', '阿卡波糖', '12:00', '1片', 1, 2),
(2, 'water', '下午饮水', '补充水分', '14:30', '250ml', 1, 2),
(2, 'medicine', '晚间降糖药', '二甲双胍缓释片', '18:00', '1片', 1, 2),
(3, 'medicine', '抗凝药', '阿司匹林肠溶片', '08:00', '1片', 1, 2),
(3, 'water', '晨起饮水', '温水一杯', '07:00', '200ml', 1, 2),
(3, 'medicine', '降压药', '厄贝沙坦片', '08:30', '1片', 1, 2),
(3, 'water', '康复训练后饮水', '康复训练后补充水分', '11:00', '250ml', 1, 2),
(3, 'medicine', '他汀类药物', '阿托伐他汀', '21:00', '1片', 1, 2);

-- Today's reminder logs (generated for demo)
INSERT INTO reminder_logs (reminder_id, patient_id, scheduled_time, status) VALUES
(1, 1, datetime('now', 'start of day', '+7 hours'), 'completed'),
(2, 1, datetime('now', 'start of day', '+8 hours'), 'completed'),
(3, 1, datetime('now', 'start of day', '+10 hours'), 'pending'),
(4, 1, datetime('now', 'start of day', '+12 hours'), 'pending'),
(5, 1, datetime('now', 'start of day', '+15 hours'), 'pending'),
(6, 1, datetime('now', 'start of day', '+20 hours'), 'pending'),
(7, 2, datetime('now', 'start of day', '+7 hours', '+30 minutes'), 'completed'),
(8, 2, datetime('now', 'start of day', '+7 hours'), 'completed'),
(9, 2, datetime('now', 'start of day', '+8 hours'), 'completed'),
(10, 2, datetime('now', 'start of day', '+12 hours'), 'pending'),
(11, 2, datetime('now', 'start of day', '+14 hours', '+30 minutes'), 'pending'),
(12, 2, datetime('now', 'start of day', '+18 hours'), 'pending'),
(13, 3, datetime('now', 'start of day', '+8 hours'), 'completed'),
(14, 3, datetime('now', 'start of day', '+7 hours'), 'completed'),
(15, 3, datetime('now', 'start of day', '+8 hours', '+30 minutes'), 'pending'),
(16, 3, datetime('now', 'start of day', '+11 hours'), 'pending'),
(17, 3, datetime('now', 'start of day', '+21 hours'), 'pending');
