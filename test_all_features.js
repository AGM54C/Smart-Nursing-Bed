/**
 * Comprehensive test for all non-hardware features
 */
const http = require('http');

const BASE = 'http://127.0.0.1:3000';
let TOKEN = '';
let PASS = 0, FAIL = 0;
const results = [];

function req(method, path, body, headers = {}) {
    return new Promise((resolve, reject) => {
        const url = new URL(BASE + path);
        const postData = body ? JSON.stringify(body) : null;
        const opts = {
            hostname: url.hostname, port: url.port, path: url.pathname + url.search,
            method, headers: { 'Content-Type': 'application/json', ...headers }
        };
        if (TOKEN) opts.headers['Authorization'] = `Bearer ${TOKEN}`;
        if (postData) opts.headers['Content-Length'] = Buffer.byteLength(postData);

        const r = http.request(opts, (res) => {
            let data = '';
            res.on('data', c => data += c);
            res.on('end', () => {
                let json;
                try { json = JSON.parse(data); } catch(e) { json = data; }
                resolve({ status: res.statusCode, body: json });
            });
        });
        r.on('error', reject);
        if (postData) r.write(postData);
        r.end();
    });
}

function test(name, fn) {
    return fn().then(r => {
        PASS++;
        results.push(`✅ ${name}`);
        return r;
    }).catch(e => {
        FAIL++;
        results.push(`❌ ${name}: ${e.message || e}`);
    });
}

async function run() {
    console.log('=== 开始测试所有非硬件功能 ===\n');

    // 1. Auth - Login
    await test('登录认证 (POST /api/auth/login)', async () => {
        const r = await req('POST', '/api/auth/login', { username: 'admin', password: 'admin123' });
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
        if (!r.body.token) throw new Error('No token returned');
        TOKEN = r.body.token;
        console.log(`  → 登录成功: ${r.body.user.real_name} (${r.body.user.role})`);
    });

    // 2. Auth - Me
    await test('获取当前用户 (GET /api/auth/me)', async () => {
        const r = await req('GET', '/api/auth/me');
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
        if (!r.body.user) throw new Error('No user object');
    });

    // 3. Patients list
    let patientId;
    await test('患者列表 (GET /api/patients)', async () => {
        const r = await req('GET', '/api/patients');
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
        if (!Array.isArray(r.body)) throw new Error('Expected array');
        if (r.body.length === 0) throw new Error('No patients found');
        patientId = r.body[0].id;
        console.log(`  → ${r.body.length}个患者, 使用ID: ${patientId}`);
    });

    // 4. Patient detail
    await test('患者详情 (GET /api/patients/:id)', async () => {
        const r = await req('GET', `/api/patients/${patientId}`);
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
        if (!r.body.patient) throw new Error('No patient object');
        console.log(`  → 患者: ${r.body.patient.name}, ${r.body.patient.age}岁`);
    });

    // 5. Vitals history
    await test('生命体征历史 (GET /api/vitals/:id)', async () => {
        const r = await req('GET', `/api/vitals/${patientId}`);
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
        if (!Array.isArray(r.body)) throw new Error('Expected array');
        console.log(`  → ${r.body.length}条记录`);
    });

    // 6. Vitals latest
    await test('最新体征 (GET /api/vitals/:id/latest)', async () => {
        const r = await req('GET', `/api/vitals/${patientId}/latest`);
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
    });

    // 7. Vitals stats
    await test('体征统计 (GET /api/vitals/:id/stats)', async () => {
        const r = await req('GET', `/api/vitals/${patientId}/stats`);
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
    });

    // 8. Alerts list
    await test('报警列表 (GET /api/alerts)', async () => {
        const r = await req('GET', '/api/alerts');
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
        if (!Array.isArray(r.body)) throw new Error('Expected array');
        console.log(`  → ${r.body.length}条报警`);
    });

    // 9. Alert active count
    await test('活跃报警数 (GET /api/alerts/active-count)', async () => {
        const r = await req('GET', '/api/alerts/active-count');
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
        if (r.body.count === undefined) throw new Error('No count field');
    });

    // 10. Emotion analyze
    await test('情绪分析 (POST /api/emotion/analyze)', async () => {
        const r = await req('POST', '/api/emotion/analyze', { text: '我觉得很痛，肩膀特别疼', patient_id: patientId });
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
        if (!r.body.emotion) throw new Error('No emotion field');
        console.log(`  → 情绪: ${r.body.label} ${r.body.emoji}, 严重度: ${r.body.severity}`);
    });

    // 11. Emotion log
    await test('情绪记录 (POST /api/emotion/log)', async () => {
        const r = await req('POST', '/api/emotion/log', { patient_id: patientId, emotion: 'pain', label: '疼痛', severity: 4, text_snippet: '测试' });
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
    });

    // 12. Emotion history
    await test('情绪历史 (GET /api/emotion/history/:id)', async () => {
        const r = await req('GET', `/api/emotion/history/${patientId}`);
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
        if (!Array.isArray(r.body)) throw new Error('Expected array');
    });

    // 13. Pressure predict
    await test('压力预测 (POST /api/pressure/predict)', async () => {
        const grid = Array(8).fill(null).map(() => Array(8).fill(0).map(() => Math.floor(Math.random() * 4096)));
        const r = await req('POST', '/api/pressure/predict', { grid, posture: 'supine', posture_minutes: 90 });
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
        if (!r.body.overall_risk) throw new Error('No overall_risk');
        console.log(`  → 风险: ${r.body.overall_risk}, 评分: ${r.body.overall_score}`);
    });

    // 14. Pressure schedule
    await test('翻身计划 (GET /api/pressure/schedule/:id)', async () => {
        const r = await req('GET', `/api/pressure/schedule/${patientId}`);
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
        if (!r.body.schedule) throw new Error('No schedule field');
        console.log(`  → 当前体位: ${r.body.current_posture}, ${r.body.schedule.length}个翻身计划`);
    });

    // 15. Agents list
    await test('Agent列表 (GET /api/agents)', async () => {
        const r = await req('GET', '/api/agents');
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
        if (!Array.isArray(r.body)) throw new Error('Expected array');
        console.log(`  → ${r.body.length}个Agent: ${r.body.map(a => a.display_name).join(', ')}`);
    });

    // 16. Reports history
    await test('报告历史 (GET /api/reports/:id)', async () => {
        const r = await req('GET', `/api/reports/${patientId}`);
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
        if (!Array.isArray(r.body)) throw new Error('Expected array');
        console.log(`  → ${r.body.length}份报告`);
    });

    // 17. Reminders list
    await test('提醒列表 (GET /api/reminders/:id)', async () => {
        const r = await req('GET', `/api/reminders/${patientId}`);
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
        if (!Array.isArray(r.body)) throw new Error('Expected array');
        console.log(`  → ${r.body.length}个提醒`);
    });

    // 18. Create reminder
    let reminderId;
    await test('创建提醒 (POST /api/reminders)', async () => {
        const r = await req('POST', '/api/reminders', {
            patient_id: patientId, reminder_type: 'water', title: '测试-喝水提醒',
            description: '自动化测试创建', schedule_time: '23:59', dosage: '200ml'
        });
        if (r.status !== 201) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
        reminderId = r.body.id;
        console.log(`  → 创建成功 ID: ${reminderId}`);
    });

    // 19. Reminder logs
    await test('提醒日志 (GET /api/reminders/logs/:id)', async () => {
        const r = await req('GET', `/api/reminders/logs/${patientId}`);
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
        if (!Array.isArray(r.body)) throw new Error('Expected array');
        console.log(`  → ${r.body.length}条日志`);
    });

    // 20. Today stats
    await test('今日统计 (GET /api/reminders/today/:id)', async () => {
        const r = await req('GET', `/api/reminders/today/${patientId}`);
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
    });

    // 21. Toggle reminder
    await test('启停提醒 (PUT /api/reminders/:id/toggle)', async () => {
        if (!reminderId) throw new Error('No reminder to toggle');
        const r = await req('PUT', `/api/reminders/${reminderId}/toggle`);
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
    });

    // 22. Delete the test reminder
    await test('删除提醒 (DELETE /api/reminders/:id)', async () => {
        if (!reminderId) throw new Error('No reminder to delete');
        const r = await req('DELETE', `/api/reminders/${reminderId}`);
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
    });

    // 23. Device register
    await test('设备注册 (POST /api/device/register)', async () => {
        const r = await req('POST', '/api/device/register', { patient_id: patientId, ip: '192.168.1.100' });
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
    });

    // 24. Device info
    await test('设备信息 (GET /api/device/info)', async () => {
        const r = await req('GET', `/api/device/info?patient_id=${patientId}`);
        if (r.status !== 200) throw new Error(`Status ${r.status}`);
        console.log(`  → device_ip: ${r.body.device_ip}`);
    });

    // 25. Vitals POST (simulate ESP32 data upload)
    await test('生命体征上传 (POST /api/vitals)', async () => {
        const r = await req('POST', '/api/vitals', {
            patient_id: patientId,
            heart_rate: 75, blood_pressure_sys: 120, blood_pressure_dia: 80,
            blood_oxygen: 98, blood_glucose: 5.5, temperature: 36.5,
            sleep_posture: 'supine'
        }, { 'x-api-key': process.env.DEVICE_API_KEY || '' });
        if (r.status !== 201) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body)}`);
        console.log(`  → 数据上传成功`);
    });

    // === LLM API Tests ===
    console.log('\n--- 以下测试需要云端LLM API (Qwen) ---');

    // 26. AI Report generate
    await test('AI报告生成 (POST /api/reports/generate)', async () => {
        const r = await req('POST', '/api/reports/generate', { patient_id: patientId });
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body).slice(0, 200)}`);
        if (!r.body.summary) throw new Error('No summary in response');
        console.log(`  → 报告生成成功: ${r.body.summary?.slice(0, 50)}...`);
    });

    // 27. Agent consult
    await test('Agent咨询 (POST /api/agents/consult)', async () => {
        const r = await req('POST', '/api/agents/consult', { patient_id: patientId, question: '这位患者今天的血压怎么样？' });
        if (r.status !== 200) throw new Error(`Status ${r.status}: ${JSON.stringify(r.body).slice(0, 200)}`);
        if (!r.body.response) throw new Error('No response field');
        console.log(`  → Agent回复: ${r.body.response?.slice(0, 80)}...`);
    });

    // 28. Agent stream-chat (SSE)
    await test('Agent流式聊天 (POST /api/agents/stream-chat)', async () => {
        return new Promise((resolve, reject) => {
            const postData = JSON.stringify({
                patient_id: patientId,
                messages: [{ role: 'user', content: '你好，请简单介绍自己' }]
            });
            const opts = {
                hostname: '127.0.0.1', port: 3000, path: '/api/agents/stream-chat', method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${TOKEN}`,
                    'Content-Length': Buffer.byteLength(postData)
                }
            };
            let data = '';
            const r = http.request(opts, (res) => {
                res.on('data', c => data += c);
                res.on('end', () => {
                    if (res.statusCode !== 200) return reject(new Error(`Status ${res.statusCode}: ${data.slice(0,200)}`));
                    if (!data.includes('"type":"done"')) return reject(new Error('Missing done event'));
                    if (data.includes('"type":"delta"')) {
                        console.log(`  → 流式响应OK (${data.length} bytes)`);
                        resolve();
                    } else if (data.includes('"type":"error"')) {
                        reject(new Error('Stream returned error: ' + data.slice(0,200)));
                    } else {
                        console.log(`  → 流式响应完成但无delta (可能API超时)`);
                        resolve();
                    }
                });
            });
            r.on('error', reject);
            r.write(postData); r.end();
            setTimeout(() => reject(new Error('Timeout 60s')), 60000);
        });
    });

    // Summary
    console.log('\n' + '='.repeat(50));
    console.log(`📊 测试完成: ✅ ${PASS} 通过, ❌ ${FAIL} 失败\n`);
    results.forEach(r => console.log(r));
    console.log('\n' + '='.repeat(50));
}

run().catch(e => console.error('Fatal:', e));
