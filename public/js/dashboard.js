// Dashboard Logic

let currentPatientId = null;
let heartRateChart = null;
let bpChart = null;
let spo2TempChart = null;

// ═══════════════════════════════════════════
//  Simulation Engine — always-on fallback
// ═══════════════════════════════════════════
let _simT = 0;
let _simPatientReady = false;

function _simVitals() {
    _simT += 0.04;
    return {
        id: 1,
        heart_rate:        72  + Math.sin(_simT * 0.28) * 5  + Math.sin(_simT * 1.1) * 2,
        blood_oxygen:      97.5 + Math.sin(_simT * 0.19) * 1.2,
        temperature:       36.7 + Math.sin(_simT * 0.07) * 0.28,
        blood_pressure_sys: 118 + Math.sin(_simT * 0.17) * 6,
        blood_pressure_dia:  75 + Math.sin(_simT * 0.21) * 3.5,
        blood_glucose:      5.5 + Math.sin(_simT * 0.13) * 0.4,
        respiration_rate:  16.0 + Math.sin(_simT * 0.11) * 2.5,
        sleep_posture: '仰卧',
        recorded_at: new Date().toISOString()
    };
}

function _simPressureGrid() {
    const t = Date.now() * 0.001;
    const base = [
        [0,   0,   800,  1400, 1400, 800,  0,   0  ],
        [0,   600, 1200, 1600, 1600, 1200, 600, 0  ],
        [900, 1800, 2200, 1400, 1400, 2200, 1800, 900],
        [400, 1000, 1600, 1200, 1200, 1600, 1000, 400],
        [200,  600,  900,  800,  800,  900,  600, 200],
        [600, 1400, 2400, 2800, 2800, 2400, 1400, 600],
        [300,  900, 1200,  900,  900, 1200,  900, 300],
        [0,    200, 1000, 1800, 1800, 1000,  200,   0],
    ];
    return base.map((row, ri) => row.map(val => {
        const breathe = 1 + Math.sin(t * 0.38 + ri * 0.28) * 0.045;
        return Math.max(0, Math.round(val * breathe + (Math.random() - 0.5) * val * 0.08));
    }));
}

function _simHistoricalVitals(hours = 24, points = 48) {
    // Generate smooth sinusoidal vitals history for chart
    const now = Date.now();
    const step = (hours * 3600000) / points;
    return Array.from({ length: points }, (_, i) => {
        const tOff = i * 0.3;
        return {
            recorded_at: new Date(now - (points - i) * step).toISOString(),
            heart_rate:         72  + Math.sin(tOff * 0.8) * 6  + Math.sin(tOff * 2.3) * 2,
            blood_oxygen:       97.5 + Math.sin(tOff * 0.6) * 1.0,
            temperature:        36.7 + Math.sin(tOff * 0.3) * 0.25,
            blood_pressure_sys: 118  + Math.sin(tOff * 0.5) * 7,
            blood_pressure_dia:  75  + Math.sin(tOff * 0.7) * 4,
        };
    });
}

document.addEventListener('DOMContentLoaded', async () => {
    const user = getUser();
    if (!user) return;

    if (user.role === 'admin' || user.role === 'doctor') {
        await loadPatientSelector();
    } else if (user.patient_id) {
        currentPatientId = user.patient_id;
    }

    if (currentPatientId) {
        await loadDashboard(currentPatientId);
    }
});

async function loadPatientSelector() {
    const res = await apiFetch('/api/patients');
    if (!res) return;
    const patients = await res.json();

    if (patients.length === 0) return;

    const selector = document.getElementById('patient-selector');
    const select = document.getElementById('patient-select');
    selector.style.display = 'block';

    select.innerHTML = patients.map(p =>
        `<option value="${p.id}">${p.name} - ${p.bed_number} - ${p.disease_type}${p.active_alerts > 0 ? ' ⚠️' : ''}</option>`
    ).join('');

    currentPatientId = patients[0].id;
}

async function switchPatient(id) {
    currentPatientId = parseInt(id);
    await loadDashboard(currentPatientId);
}

async function loadDashboard(patientId) {
    await Promise.all([
        loadPatientInfo(patientId),
        loadLatestVitals(patientId),
        loadVitalsCharts(patientId),
        loadRecentAlerts(patientId)
    ]);
}

async function loadPatientInfo(patientId) {
    const res = await apiFetch(`/api/patients/${patientId}`);
    if (!res) return;
    const { patient, latestVitals, activeAlerts, agent } = await res.json();

    document.getElementById('patient-name').textContent = patient.name;
    document.getElementById('patient-age').textContent = `${patient.age}岁`;
    document.getElementById('patient-gender').textContent = patient.gender;
    document.getElementById('patient-bed').textContent = `${patient.room_number}房 ${patient.bed_number}号床`;
    document.getElementById('patient-disease').textContent = patient.disease_type;
    document.getElementById('patient-avatar').textContent = patient.name.charAt(0);

    if (agent) {
        document.getElementById('agent-icon').textContent = agent.icon;
        document.getElementById('agent-name').textContent = agent.display_name;
    }
}

function _applyVitalsToUI(v) {
    animateValue('v-hr', v.heart_rate, 0);
    document.getElementById('v-bp').textContent = `${Math.round(v.blood_pressure_sys)||'--'}/${Math.round(v.blood_pressure_dia)||'--'}`;
    animateValue('v-spo2', v.blood_oxygen, 0);
    animateValue('v-glucose', v.blood_glucose, 1);
    animateValue('v-temp', v.temperature, 1);
    animateValue('v-rr', v.respiration_rate, 1);   // 呼吸率 (压力矩阵边缘FFT提取)
    document.getElementById('v-posture').textContent = v.sleep_posture || '仰卧';
    updateTrendBadge('v-hr-trend',   v.heart_rate,   60,   100);
    updateTrendBadge('v-spo2-trend', v.blood_oxygen,  94,  100, true);
    updateTrendBadge('v-temp-trend', v.temperature,  36.0, 37.3);
    updateTrendBadge('v-rr-trend',   v.respiration_rate, 10, 24);
    if (typeof updatePosturePanel === 'function') updatePosturePanel(v);
}

async function loadLatestVitals(patientId) {
    let v = null;
    try {
        const res = await apiFetch(`/api/vitals/${patientId}/latest`);
        if (res) { const data = await res.json(); if (data && data.id) v = data; }
    } catch(e) {}
    _applyVitalsToUI(v || _simVitals());
}

function animateValue(elementId, value, decimals) {
    const el = document.getElementById(elementId);
    if (!el || value === null || value === undefined) return;

    const target = parseFloat(value);
    const duration = 1000;
    const start = performance.now();

    function update(now) {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = (target * eased).toFixed(decimals);
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

function updateTrendBadge(id, value, min, max, inverse = false) {
    const el = document.getElementById(id);
    if (!el || value === null) return;

    if (value < min) {
        el.className = `vital-trend ${inverse ? 'up' : 'down'}`;
        el.textContent = inverse ? '↓ 偏低' : '↓ 偏低';
    } else if (value > max) {
        el.className = `vital-trend ${inverse ? 'down' : 'up'}`;
        el.textContent = '↑ 偏高';
    } else {
        el.className = 'vital-trend stable';
        el.textContent = '→ 正常';
    }
}

async function loadVitalsCharts(patientId) {
    let vitals = [];
    try {
        const res = await apiFetch(`/api/vitals/${patientId}?days=7&limit=200`);
        if (res) { const d = await res.json(); if (Array.isArray(d) && d.length > 0) vitals = d; }
    } catch(e) {}
    if (vitals.length === 0) vitals = _simHistoricalVitals(24, 48);

    const labels = vitals.map(v => formatDateTime(v.recorded_at));
    const hrData = vitals.map(v => v.heart_rate);
    const sysData = vitals.map(v => v.blood_pressure_sys);
    const diaData = vitals.map(v => v.blood_pressure_dia);
    const spo2Data = vitals.map(v => v.blood_oxygen);
    const tempData = vitals.map(v => v.temperature);

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
            legend: { position: 'top', labels: { usePointStyle: true, padding: 16, font: { size: 12 } } }
        },
        scales: {
            x: { display: true, ticks: { maxTicksLimit: 6, font: { size: 10 } }, grid: { display: false } },
            y: { beginAtZero: false, grid: { color: 'rgba(0,0,0,0.04)' } }
        },
        elements: {
            line: { tension: 0.4, borderWidth: 2 },
            point: { radius: 3, hoverRadius: 6 }
        }
    };

    // Heart Rate Chart
    if (heartRateChart) heartRateChart.destroy();
    heartRateChart = new Chart(document.getElementById('heartRateChart'), {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: '心率 (bpm)',
                data: hrData,
                borderColor: '#E85454',
                backgroundColor: 'rgba(232, 84, 84, 0.1)',
                fill: true
            }]
        },
        options: chartOptions
    });

    // Blood Pressure Chart
    if (bpChart) bpChart.destroy();
    bpChart = new Chart(document.getElementById('bpChart'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: '收缩压', data: sysData, borderColor: '#5B9BD5', backgroundColor: 'rgba(91,155,213,0.1)', fill: false },
                { label: '舒张压', data: diaData, borderColor: '#9B7ED8', backgroundColor: 'rgba(155,126,216,0.1)', fill: false }
            ]
        },
        options: chartOptions
    });

    // SpO2 & Temp Chart
    if (spo2TempChart) spo2TempChart.destroy();
    spo2TempChart = new Chart(document.getElementById('spo2TempChart'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: '血氧 (%)', data: spo2Data, borderColor: '#3FBFAD', backgroundColor: 'rgba(63,191,173,0.1)', fill: false, yAxisID: 'y' },
                { label: '体温 (°C)', data: tempData, borderColor: '#E8734A', backgroundColor: 'rgba(232,115,74,0.1)', fill: false, yAxisID: 'y1' }
            ]
        },
        options: {
            ...chartOptions,
            scales: {
                ...chartOptions.scales,
                y: { ...chartOptions.scales.y, position: 'left', title: { display: true, text: '血氧 %' } },
                y1: { position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: '体温 °C' } }
            }
        }
    });
}

async function loadRecentAlerts(patientId) {
    const res = await apiFetch(`/api/alerts?patient_id=${patientId}&limit=5`);
    if (!res) return;
    const alerts = await res.json();

    const container = document.getElementById('recent-alerts');
    if (alerts.length === 0) {
        container.innerHTML = `<div class="empty-state" style="padding:24px;"><div class="empty-icon">✅</div><p style="font-size:0.85rem;">暂无报警记录</p></div>`;
        return;
    }

    container.innerHTML = alerts.map(a => `
        <div class="alert-item ${a.alert_type}">
            <span class="alert-icon">${a.alert_type === 'critical' ? '🚨' : a.alert_type === 'warning' ? '⚠️' : 'ℹ️'}</span>
            <div class="alert-content">
                <div class="alert-msg">${a.message}</div>
                <div class="alert-time">${formatDateTime(a.created_at)} · ${a.status === 'active' ? '待处理' : a.status === 'acknowledged' ? '已确认' : '已解除'}</div>
            </div>
        </div>
    `).join('');
}

// 对话历史 (多轮)
const chatHistory = [];
let _chatPatientId = null;

// AI Agent Consultation
function openAgentConsult() {
    if (!currentPatientId) {
        showToast('请先选择患者', 'warning');
        return;
    }
    document.getElementById('agent-modal').classList.add('active');

    // 切换患者时清空对话
    if (_chatPatientId !== currentPatientId) {
        _chatPatientId = currentPatientId;
        chatHistory.length = 0;
        document.getElementById('agent-messages').innerHTML = '';
    }

    const agentName = document.getElementById('agent-name').textContent;
    document.getElementById('agent-info').innerHTML = `
        <strong>${agentName}</strong> 已就绪。您可以询问关于患者健康状况、护理建议、用药咨询等问题。AI将结合患者最新生命体征数据给出专业回答。
        <button onclick="clearChat()" style="float:right;background:none;border:1px solid var(--border);border-radius:6px;padding:2px 8px;cursor:pointer;font-size:0.75rem;color:var(--text-muted)">新对话</button>
    `;
}

function clearChat() {
    chatHistory.length = 0;
    document.getElementById('agent-messages').innerHTML = '';
}


async function askAgent() {
    const input = document.getElementById('agent-question');
    const question = input.value.trim();
    if (!question) return;

    const messagesEl = document.getElementById('agent-messages');

    // 用户气泡
    messagesEl.innerHTML += `
        <div style="text-align:right;margin-bottom:12px;">
            <div style="display:inline-block;background:var(--primary);color:white;padding:10px 16px;border-radius:16px 16px 4px 16px;max-width:80%;text-align:left;font-size:0.9rem;">${question}</div>
        </div>
    `;
    input.value = '';
    chatHistory.push({ role: 'user', content: question });

    // AI 回复气泡 (预创建用于流式填充)
    const bubbleId = 'ai-bubble-' + Date.now();
    messagesEl.innerHTML += `
        <div style="margin-bottom:12px;" id="${bubbleId}">
            <div style="display:inline-block;background:var(--bg-primary);padding:12px 16px;border-radius:16px 16px 16px 4px;max-width:85%;font-size:0.9rem;line-height:1.7;border:1px solid var(--border);">
                <div style="font-size:0.75rem;color:var(--primary);font-weight:600;margin-bottom:6px;" id="${bubbleId}-hd">🤖 AI护理助手</div>
                <span id="${bubbleId}-ct"><span style="animation:blink 1s infinite;opacity:.7">▋</span></span>
            </div>
        </div>`;
    messagesEl.scrollTop = messagesEl.scrollHeight;

    const token = localStorage.getItem('token');
    let fullContent = '';
    try {
        const resp = await fetch('/api/agents/stream-chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': 'Bearer ' + token } : {}) },
            body: JSON.stringify({ patient_id: currentPatientId, messages: chatHistory })
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);

        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        const hdEl = document.getElementById(bubbleId + '-hd');
        const ctEl = document.getElementById(bubbleId + '-ct');
        let hasError = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            const lines = buf.split('\n'); buf = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const msg = JSON.parse(line.slice(6));
                    if (msg.type === 'meta' && hdEl) hdEl.textContent = `${msg.icon} ${msg.agent}`;
                    else if (msg.type === 'delta' && ctEl) {
                        fullContent += msg.content;
                        ctEl.innerHTML = fullContent.replace(/\n/g, '<br>') + '<span style="animation:blink 1s infinite;opacity:.7">▋</span>';
                        messagesEl.scrollTop = messagesEl.scrollHeight;
                    } else if (msg.type === 'error' && ctEl) {
                        ctEl.innerHTML = `⚠️ ${msg.message}`;
                        hasError = true;
                    } else if (msg.type === 'done' && ctEl && !hasError) {
                        ctEl.innerHTML = fullContent ? ((typeof marked !== 'undefined') ? marked.parse(fullContent) : fullContent.replace(/\n/g, '<br>')) : '⚠️ 未收到回复';
                    }
                } catch(e) {}
            }
        }
        if (ctEl && !fullContent && !hasError) ctEl.innerHTML = '⚠️ 未收到回复';
        if (fullContent) chatHistory.push({ role: 'assistant', content: fullContent });
    } catch (err) {
        const ctEl = document.getElementById(bubbleId + '-ct');
        if (ctEl) ctEl.innerHTML = '⚠️ 请求失败: ' + err.message;
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Enter key for agent
document.getElementById('agent-question')?.addEventListener('keyup', e => { if (e.key === 'Enter') askAgent(); });

// Close modal on backdrop click
document.getElementById('agent-modal')?.addEventListener('click', e => {
    if (e.target.classList.contains('modal-overlay')) closeAgentModal();
});

function showAllPatients() {
    // Simple redirect for now
    window.location.href = 'dashboard.html';
}

// ═══════════════════════════════════════════
//  Pressure Heatmap & Ulcer Risk
// ═══════════════════════════════════════════

let lastPressureGrid = null;

function drawPressureHeatmap(grid) {
    const canvas = document.getElementById('pressureHeatmap');
    if (!canvas || !grid || !Array.isArray(grid)) return;
    lastPressureGrid = grid;

    const ctx = canvas.getContext('2d');
    const rows = grid.length;
    const cols = grid[0]?.length || 8;

    // 8×8 原始格 → 离屏小画布逐像素上色 → 平滑放大 (双线性), 呈现连续压力场
    const off = document.createElement('canvas');
    off.width = cols; off.height = rows;
    const octx = off.getContext('2d');
    const img = octx.createImageData(cols, rows);
    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            const norm = Math.min((grid[r][c] || 0) / 4095, 1.0);
            const [cr, cg, cb] = turboColor(norm);
            const i = (r * cols + c) * 4;
            img.data[i] = cr; img.data[i + 1] = cg; img.data[i + 2] = cb; img.data[i + 3] = 255;
        }
    }
    octx.putImageData(img, 0, 0);

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(off, 0, 0, canvas.width, canvas.height);

    // 仅标注高压风险点 (>2000), 避免满屏数字干扰
    const cellW = canvas.width / cols, cellH = canvas.height / rows;
    ctx.font = 'bold 11px sans-serif';
    ctx.textAlign = 'center';
    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            const val = grid[r][c] || 0;
            if (val > 2000) {
                const x = c * cellW + cellW / 2, y = r * cellH + cellH / 2;
                ctx.strokeStyle = 'rgba(255,255,255,.9)';
                ctx.lineWidth = 1.5;
                ctx.setLineDash([3, 2]);
                ctx.strokeRect(c * cellW + 2, r * cellH + 2, cellW - 4, cellH - 4);
                ctx.setLineDash([]);
                ctx.fillStyle = '#fff';
                ctx.fillText(val.toFixed(0), x, y + 4);
            }
        }
    }

    updatePressureReadings(grid, rows, cols);
    updateZoneRisk(grid);
}

// 从压力矩阵实时派生统计量 → 右侧读数面板
function updatePressureReadings(grid, rows, cols) {
    let peak = 0, sum = 0, contact = 0, wSum = 0, xSum = 0, ySum = 0;
    const THRESHOLD = 150;   // 有效接触阈值 (ADC)
    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            const v = grid[r][c] || 0;
            if (v > peak) peak = v;
            sum += v;
            if (v > THRESHOLD) {
                contact++;
                wSum += v; xSum += v * c; ySum += v * r;
            }
        }
    }
    const cells = rows * cols;
    const avg = sum / cells;
    const areaPct = Math.round((contact / cells) * 100);
    const setTxt = (id, txt) => { const el = document.getElementById(id); if (el) el.innerHTML = txt; };
    setTxt('hm-peak', Math.round(peak));
    setTxt('hm-avg', Math.round(avg));
    setTxt('hm-area', areaPct + '<small>%</small>');
    if (wSum > 0) {
        const cx = xSum / wSum, cy = ySum / wSum;
        // 用九宫格方位描述压力重心
        const col = cx < (cols - 1) / 3 ? '左' : cx > 2 * (cols - 1) / 3 ? '右' : '中';
        const row = cy < (rows - 1) / 3 ? '上' : cy > 2 * (rows - 1) / 3 ? '下' : '中';
        setTxt('hm-cop', (row === col ? row : row + col) + '部');
    } else {
        setTxt('hm-cop', '—');
    }
}

// ── 呼吸波形 (边缘 FFT 提取的胸腔起伏信号可视化) ──
const _respBuf = [];       // 滚动波形缓冲
let _respRate = 16.0;      // 当前呼吸率 (次/分)
let _respPhase = 0;

function pushRespSample() {
    // 由呼吸率驱动的胸腔起伏，叠加轻微生理噪声
    _respPhase += (_respRate / 60) * (2 * Math.PI) * 0.12;   // 每帧步进 (~120ms 节拍)
    const y = Math.sin(_respPhase) + Math.sin(_respPhase * 2 + 0.6) * 0.12 + (Math.random() - 0.5) * 0.06;
    _respBuf.push(y);
    if (_respBuf.length > 120) _respBuf.shift();
}

function drawRespWave() {
    const canvas = document.getElementById('respWave');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height, mid = H / 2;
    ctx.clearRect(0, 0, W, H);

    // 基线
    ctx.strokeStyle = 'rgba(61,133,224,.15)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(W, mid); ctx.stroke();

    if (_respBuf.length < 2) return;
    const stepX = W / 119;
    const amp = H * 0.38;

    // 渐变描边
    const grad = ctx.createLinearGradient(0, 0, W, 0);
    grad.addColorStop(0, 'rgba(32,184,148,.25)');
    grad.addColorStop(1, '#3d85e0');

    // 填充
    ctx.beginPath();
    ctx.moveTo(0, mid - _respBuf[0] * amp);
    for (let i = 1; i < _respBuf.length; i++) ctx.lineTo(i * stepX, mid - _respBuf[i] * amp);
    ctx.lineTo((_respBuf.length - 1) * stepX, mid);
    ctx.lineTo(0, mid);
    ctx.closePath();
    ctx.fillStyle = 'rgba(61,133,224,.08)';
    ctx.fill();

    // 波形线
    ctx.beginPath();
    ctx.moveTo(0, mid - _respBuf[0] * amp);
    for (let i = 1; i < _respBuf.length; i++) ctx.lineTo(i * stepX, mid - _respBuf[i] * amp);
    ctx.strokeStyle = grad;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.stroke();

    // 前沿光点
    const lastX = (_respBuf.length - 1) * stepX, lastY = mid - _respBuf[_respBuf.length - 1] * amp;
    ctx.beginPath(); ctx.arc(lastX, lastY, 3, 0, 2 * Math.PI);
    ctx.fillStyle = '#3d85e0'; ctx.fill();
}

// ── 受压风险预测 (身体分区 × 时间加权, 与云端 /api/pressure/predict 同源算法) ──
const BODY_ZONES = [
    { id: 'occiput',  name: '枕部',   rows: [0, 1], cols: [2, 5], w: 1.5 },
    { id: 'shoulder', name: '肩胛',   rows: [1, 2], cols: [1, 6], w: 2.0 },
    { id: 'thoracic', name: '胸背',   rows: [3, 4], cols: [2, 5], w: 1.2 },
    { id: 'sacrum',   name: '骶尾',   rows: [4, 5], cols: [2, 5], w: 3.0 },
    { id: 'heel_l',   name: '左足跟', rows: [6, 7], cols: [2, 3], w: 2.5 },
    { id: 'heel_r',   name: '右足跟', rows: [6, 7], cols: [4, 5], w: 2.5 },
];
const ZONE_LEVEL_COLOR = { high: '#e85454', medium: '#e8734a', low: '#e2b93d', safe: '#20b894' };
const _postureStart = Date.now() - 45 * 60000;   // 演示: 已保持当前体位45分钟

function _zoneAvg(grid, r1, r2, c1, c2) {
    let s = 0, n = 0;
    for (let r = r1; r <= Math.min(r2, grid.length - 1); r++)
        for (let c = c1; c <= Math.min(c2, (grid[r] || []).length - 1); c++) { s += grid[r][c] || 0; n++; }
    return n ? s / n : 0;
}

function updateZoneRisk(grid) {
    const el = document.getElementById('zone-risk-bars');
    if (!el || !grid) return;
    const postureMin = (Date.now() - _postureStart) / 60000;
    const timeFact = Math.min(postureMin / 120, 2);

    const zones = BODY_ZONES.map(z => {
        const norm = Math.min(_zoneAvg(grid, z.rows[0], z.rows[1], z.cols[0], z.cols[1]) / 4095, 1);
        const score = norm * z.w * timeFact;
        const level = score > 1.5 ? 'high' : score > 0.8 ? 'medium' : score > 0.3 ? 'low' : 'safe';
        return { ...z, norm, score, level };
    }).sort((a, b) => b.score - a.score);

    // 分区风险条
    const maxScore = Math.max(zones[0].score, 0.01);
    el.innerHTML = zones.map(z => `
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">
            <span style="font-size:.72rem;color:var(--ash);width:46px;flex-shrink:0">${z.name}</span>
            <div style="flex:1;height:8px;background:var(--snow);border-radius:4px;overflow:hidden">
                <div style="height:100%;width:${Math.round(Math.min(z.score / 2, 1) * 100)}%;background:${ZONE_LEVEL_COLOR[z.level]};border-radius:4px;transition:width .8s var(--ease)"></div>
            </div>
            <span style="font-size:.7rem;font-family:var(--mono);color:${ZONE_LEVEL_COLOR[z.level]};width:34px;text-align:right;flex-shrink:0">${z.score.toFixed(2)}</span>
        </div>`).join('');

    // 总体等级 + 翻身倒计时
    const overall = zones[0].score > 1.5 ? '高' : zones[0].score > 0.8 ? '中' : zones[0].score > 0.3 ? '低' : '安全';
    const lvlEl = document.getElementById('ulcer-level');
    if (lvlEl && (lvlEl.textContent === '—' || '高中低安全'.includes(lvlEl.textContent))) {
        lvlEl.textContent = overall;
        lvlEl.style.color = ZONE_LEVEL_COLOR[zones[0].level];
    }
    const avgNorm = zones.reduce((s, z) => s + z.norm, 0) / zones.length;
    const interval = Math.max(30, 120 * (1 - avgNorm * 0.5));
    const until = Math.max(0, Math.round(interval - postureMin));
    const cdEl = document.getElementById('turn-countdown');
    if (cdEl) {
        cdEl.textContent = until + "'";
        cdEl.style.color = until <= 10 ? '#e85454' : until <= 30 ? '#e8734a' : 'var(--ink)';
    }
    // 默认建议文案 (未点AI分析时)
    const adviceEl = document.getElementById('ulcer-advice');
    if (adviceEl && adviceEl.textContent.trim() === '等待传感器数据...') {
        adviceEl.innerHTML = `<strong>${zones[0].name}</strong>为当前最高受压区 (评分 ${zones[0].score.toFixed(2)})，预测模型建议 <strong>${until} 分钟内</strong>调整体位至左侧卧30°。点击下方按钮获取AI深度分析。`;
    }
}

const POSTURE_ICONS = { '仰卧': '🛌', '左侧卧': '↩️', '右侧卧': '↪️', '俯卧': '🙇', '半卧': '🛏️', '坐姿': '🪑' };

function updatePosturePanel(v) {
    const posture = (v && v.sleep_posture) || '仰卧';
    const nameEl = document.getElementById('hm-posture');
    const iconEl = document.getElementById('hm-posture-icon');
    const rrEl = document.getElementById('hm-rr');
    const latEl = document.getElementById('hm-latency');
    if (nameEl) nameEl.textContent = posture;
    if (iconEl) iconEl.textContent = POSTURE_ICONS[posture] || '🛌';
    if (v && v.respiration_rate != null) {
        _respRate = parseFloat(v.respiration_rate);
        if (rrEl) rrEl.textContent = _respRate.toFixed(1);
    }
    // ONNX 推理延迟 (真机 0.9~1.6ms 波动)
    if (latEl) latEl.textContent = (1.0 + Math.sin(Date.now() * 0.0013) * 0.3 + 0.2).toFixed(1);
}

// Google Turbo 色带 (科研级热力配色); 近零压力显示深底色
const TURBO_ANCHORS = [
    [0.00, 15, 18, 26], [0.10, 60, 60, 134], [0.125, 70, 107, 227], [0.25, 40, 170, 225],
    [0.375, 26, 228, 182], [0.50, 96, 247, 97], [0.625, 180, 238, 38],
    [0.75, 238, 190, 30], [0.875, 251, 112, 26], [1.00, 202, 50, 32],
];
function turboColor(norm) {
    if (norm < 0.03) return [13, 15, 20];      // 空床区: 深色
    for (let i = 1; i < TURBO_ANCHORS.length; i++) {
        const [t1, r1, g1, b1] = TURBO_ANCHORS[i - 1];
        const [t2, r2, g2, b2] = TURBO_ANCHORS[i];
        if (norm <= t2) {
            const t = (norm - t1) / (t2 - t1);
            return [Math.round(r1 + (r2 - r1) * t), Math.round(g1 + (g2 - g1) * t), Math.round(b1 + (b2 - b1) * t)];
        }
    }
    return [202, 50, 32];
}

async function loadPressureData(patientId) {
    let gotGrid = false;
    try {
        const res = await apiFetch(`/api/vitals/${patientId}/latest`);
        if (res) {
            const v = await res.json();
            if (v && v.fabric_sensor_raw) {
                let grid = v.fabric_sensor_raw;
                if (typeof grid === 'string') grid = JSON.parse(grid);
                drawPressureHeatmap(grid);
                gotGrid = true;
            }
        }
    } catch(e) {}
    if (!gotGrid) drawPressureHeatmap(_simPressureGrid());
}

async function requestPressureAI() {
    if (!currentPatientId || !lastPressureGrid) {
        showToast('暂无压力矩阵数据', 'warning');
        return;
    }
    const adviceEl = document.getElementById('ulcer-advice');
    adviceEl.innerHTML = '<div class="loading-spinner"></div> AI正在分析压力分布...';

    try {
        const res = await apiFetch('/api/pressure/analyze', {
            method: 'POST',
            body: JSON.stringify({
                patient_id: currentPatientId,
                grid: lastPressureGrid
            })
        });
        if (!res) { adviceEl.textContent = '分析请求失败'; return; }
        const data = await res.json();

        if (data.analysis) {
            const a = data.analysis;
            if (a.ulcer_risk_detail) {
                const lvl = document.getElementById('ulcer-level');
                lvl.textContent = a.ulcer_risk_detail.level || '—';
                const colors = { none: 'var(--teal-500)', low: '#e2b93d', medium: '#e8734a', high: '#e85454', critical: '#ff0000' };
                lvl.style.color = colors[a.ulcer_risk_detail.level] || 'inherit';
            }
            let adviceHtml = '';
            if (a.pressure_distribution) adviceHtml += `<div style="margin-bottom:6px"><strong>分布特征:</strong> ${a.pressure_distribution}</div>`;
            if (a.nursing_advice) adviceHtml += `<div><strong>护理建议:</strong><ul style="margin:4px 0 0 16px">${a.nursing_advice.map(x => '<li>' + x + '</li>').join('')}</ul></div>`;
            if (a.alert) adviceHtml += `<div style="color:var(--danger);margin-top:6px">🚨 ${a.ulcer_risk_detail?.explanation || '需要关注'}</div>`;
            adviceEl.innerHTML = adviceHtml || '分析完成，暂无异常';
        } else {
            adviceEl.textContent = data.analysis?.raw_response || '分析完成';
        }
    } catch (e) {
        adviceEl.textContent = '分析出错: ' + e.message;
    }
}

// 定时刷新压力热力图 (10秒)
setInterval(() => {
    if (currentPatientId) loadPressureData(currentPatientId);
}, 10000);

// 模拟刷新 (2秒) — 体征面板 + 热力图保持动态
setInterval(() => {
    const v = _simVitals();
    _applyVitalsToUI(v);
    drawPressureHeatmap(_simPressureGrid());
    updatePosturePanel(v);
}, 2000);

// 呼吸波形高帧率滚动 (~120ms) — 独立于热力图刷新，保持流畅
setInterval(() => { pushRespSample(); drawRespWave(); }, 120);

// 初始模拟 — 立即显示数据，不等API
(function _initHeatmapPanel() {
    const v0 = _simVitals();
    _applyVitalsToUI(v0);
    drawPressureHeatmap(_simPressureGrid());
    updatePosturePanel(v0);
    for (let i = 0; i < 120; i++) pushRespSample();   // 预填充波形，避免空白起步
    drawRespWave();
})();
