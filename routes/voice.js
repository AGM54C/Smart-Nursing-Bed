const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../middleware/auth');
const { callKimiAPI } = require('./reports');
const { chat } = require('../services/llm');   // 统一 LLM 网关
const http = require('http');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const WebSocket = require('ws');

// Multer config for device audio upload
const uploadDir = path.join(__dirname, '..', 'uploads');
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });

const upload = multer({
    dest: uploadDir,
    limits: { fileSize: 50 * 1024 * 1024 }, // 50MB max
    fileFilter: (req, file, cb) => {
        const allowed = ['audio/wav', 'audio/wave', 'audio/x-wav', 'audio/mpeg', 'audio/mp3',
            'audio/webm', 'audio/ogg', 'audio/mp4', 'audio/m4a', 'application/octet-stream'];
        cb(null, true); // Accept all for device compatibility
    }
});

// ═══════════════════════════════════════════════════════════
//  DEVICE API: Hardware microphone → Server → Voice response
// ═══════════════════════════════════════════════════════════

// POST /api/voice/device/chat
// Hardware device uploads audio file → ASR → Kimi chat → return text + TTS audio
// Auth: device API key via header or query param
router.post('/device/chat', upload.single('audio'), async (req, res) => {
    // Device auth via API key
    const apiKey = req.headers['x-device-key'] || req.query.key;
    if (apiKey !== process.env.DEVICE_API_KEY) {
        return res.status(401).json({ error: '设备认证失败' });
    }

    const patientId = req.body.patient_id || req.query.patient_id;
    if (!patientId) {
        return res.status(400).json({ error: '缺少 patient_id 参数' });
    }

    if (!req.file) {
        return res.status(400).json({ error: '未上传音频文件' });
    }

    const db = req.app.locals.db;
    const patient = db.prepare('SELECT * FROM patients WHERE id = ?').get(patientId);
    if (!patient) {
        cleanupFile(req.file.path);
        return res.status(404).json({ error: '患者不存在' });
    }

    try {
        // ─── Step 1: ASR - 讯飞实时语音转写大模型 (202种方言) ───
        console.log(`🎤 [Device] Received audio from patient ${patient.name}, size: ${req.file.size} bytes`);
        const audioBuffer = fs.readFileSync(req.file.path);
        const recognizedText = await callXfyunASR(audioBuffer, req.file.originalname || 'audio.wav');
        console.log(`📝 [ASR] Recognized: "${recognizedText}"`);

        if (!recognizedText || !recognizedText.trim()) {
            cleanupFile(req.file.path);
            return res.json({
                text_in: '',
                text_out: '',
                audio_base64: null
            });
        }

        // asr_only 模式：仅做语音识别，不调用 LLM/TTS（用于唤醒词检测）
        const asrOnly = req.body.asr_only === '1' || req.query.asr_only === '1';
        if (asrOnly) {
            cleanupFile(req.file.path);
            return res.json({ text_in: recognizedText.trim(), text_out: '', audio_base64: null });
        }

        // Save patient message
        db.prepare(
            'INSERT INTO voice_conversations (patient_id, role, content) VALUES (?, ?, ?)'
        ).run(patientId, 'user', recognizedText.trim());

        // ─── Step 2: Kimi Chat ───
        const history = db.prepare(`
            SELECT role, content FROM voice_conversations 
            WHERE patient_id = ? ORDER BY created_at DESC LIMIT 10
        `).all(patientId).reverse();

        const systemPrompt = `你是一位温暖、耐心的AI陪护助手，正在和一位意识清醒的住院患者进行语音聊天。
患者信息：${patient.name}，${patient.age}岁，${patient.gender}，患有${patient.disease_type}（${patient.disease_detail || ''}）。

语音聊天要求：
1. 语气亲切温暖，像家人朋友一样陪伴，不要过于正式
2. 主动关心患者的身体感受、心情、想法和日常需求
3. 引导患者表达自己关心的事情（家人、身体、生活等）
4. 如果患者提到不适或异常，温和地建议告知护士
5. 可以聊轻松话题帮助患者放松心情
6. 回答简洁自然，每次40字以内，适合语音播放
7. 用中文回答，口语化表达`;

        const messages = history.map(h => ({
            role: h.role === 'user' ? 'user' : 'assistant',
            content: h.content
        }));

        const aiResponse = await callKimiAPIWithHistory(systemPrompt, messages);
        console.log(`🤖 [Kimi] Response: "${aiResponse}"`);

        // Save AI response
        db.prepare(
            'INSERT INTO voice_conversations (patient_id, role, content) VALUES (?, ?, ?)'
        ).run(patientId, 'assistant', aiResponse);

        // ─── Step 3: TTS - 阿里云 CosyVoice (DashScope) ───
        let audioBase64 = null;
        try {
            audioBase64 = await callCosyVoiceTTS(aiResponse);
            console.log(`🔊 [TTS] Audio generated, size: ${audioBase64.length} chars (base64)`);
        } catch (ttsErr) {
            console.error('TTS Error (non-fatal):', ttsErr.message);
        }

        cleanupFile(req.file.path);

        res.json({
            text_in: recognizedText.trim(),
            text_out: aiResponse,
            audio_base64: audioBase64,    // base64-encoded MP3 for device playback
            patient_name: patient.name
        });

    } catch (err) {
        cleanupFile(req.file.path);
        console.error('Device voice chat error:', err.message);
        res.status(500).json({ error: '语音处理失败: ' + err.message });
    }
});

// ═══════════════════════════════════════════════════════════
//  DEVICE API: Natural Language Control (NLC)
//  Voice command → ASR → Intent Parsing (Kimi) → Action JSON
// ═══════════════════════════════════════════════════════════

// Supported NLC actions mapping
const NLC_ACTIONS = [
    'bed_raise', 'bed_lower', 'bed_stop',
    'forward', 'backward', 'left', 'right', 'stop',
    'nav_line', 'nav_rfid', 'nav_stop'
];

const NLC_SYSTEM_PROMPT = `你是一个智能护理病床的语音控制解析器。患者会用自然语言说出控制指令，你需要将其解析为标准动作。

支持的动作列表：
- bed_raise: 升高靠背（"升起来""抬高""靠背升""坐起来"）
- bed_lower: 降低靠背（"放平""降下来""躺下去""靠背降"）
- bed_stop: 停止升降（"好了""停""不要再升了""不要再降了"）
- forward: 前进（"往前走""前进""向前"）
- backward: 后退（"往后退""后退""向后"）
- left: 左转（"往左转""左转""向左"）
- right: 右转（"往右转""右转""向右"）
- stop: 停止移动（"停下来""别走了""停车"）
- nav_line: 循迹导航（"沿着线走""开始循迹""自动导航"）
- nav_rfid: 寻房导航（"去X号房""去护士站""去X病房"，需提取房间号）
- nav_stop: 停止导航（"停止导航""取消导航"）
- none: 无法识别为控制指令

你必须严格以JSON格式回复，不要添加任何其他内容：
{"action": "动作名", "params": {"room": "302"}, "reply": "简短确认语（15字内）"}

params仅在nav_rfid时需要包含room字段，其他动作params为空对象{}。
如果无法识别为控制指令，action设为"none"，reply说明无法识别。`;

// POST /api/voice/device/command
// NLC: Hardware microphone → Server → Intent parsing → Action JSON + TTS
router.post('/device/command', upload.single('audio'), async (req, res) => {
    // Device auth
    const apiKey = req.headers['x-device-key'] || req.query.key;
    if (apiKey !== process.env.DEVICE_API_KEY) {
        return res.status(401).json({ error: '设备认证失败' });
    }

    const patientId = req.body.patient_id || req.query.patient_id;
    if (!patientId) {
        return res.status(400).json({ error: '缺少 patient_id 参数' });
    }

    if (!req.file) {
        return res.status(400).json({ error: '未上传音频文件' });
    }

    const db = req.app.locals.db;
    const patient = db.prepare('SELECT * FROM patients WHERE id = ?').get(patientId);
    if (!patient) {
        cleanupFile(req.file.path);
        return res.status(404).json({ error: '患者不存在' });
    }

    try {
        // ─── Step 1: ASR - 讯飞实时语音转写大模型 ───
        console.log(`🎮 [NLC] Received voice command from patient ${patient.name}, size: ${req.file.size} bytes`);
        const audioBuffer = fs.readFileSync(req.file.path);
        const recognizedText = await callXfyunASR(audioBuffer, req.file.originalname || 'audio.wav');
        console.log(`📝 [NLC-ASR] Recognized: "${recognizedText}"`);

        if (!recognizedText || !recognizedText.trim()) {
            cleanupFile(req.file.path);
            return res.json({
                text_in: '',
                action: 'none',
                params: {},
                reply: '没有听清您的指令，请再说一次',
                audio_base64: null
            });
        }

        // ─── Step 2: Intent Parsing via Kimi ───
        const messages = [{ role: 'user', content: recognizedText.trim() }];
        const aiResponse = await callKimiAPIWithHistory(NLC_SYSTEM_PROMPT, messages);
        console.log(`🤖 [NLC-Parse] Response: "${aiResponse}"`);

        // Parse JSON from AI response
        let parsed = { action: 'none', params: {}, reply: '无法识别该指令' };
        try {
            const jsonMatch = aiResponse.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                parsed = JSON.parse(jsonMatch[0]);
            }
        } catch (e) {
            console.error('NLC JSON parse error:', e.message);
        }

        // Validate action
        const action = NLC_ACTIONS.includes(parsed.action) ? parsed.action : 'none';
        const params = parsed.params || {};
        const reply = parsed.reply || (action === 'none' ? '无法识别该指令' : '好的');

        // ─── Step 3: Log to database ───
        try {
            db.prepare(
                'INSERT INTO voice_commands (patient_id, text_input, parsed_action, parsed_params, reply, executed) VALUES (?, ?, ?, ?, ?, ?)'
            ).run(patientId, recognizedText.trim(), action, JSON.stringify(params), reply, action !== 'none' ? 1 : 0);
        } catch (dbErr) {
            console.error('NLC DB log error (non-fatal):', dbErr.message);
        }

        // ─── Step 4: TTS for reply ───
        let audioBase64 = null;
        try {
            audioBase64 = await callCosyVoiceTTS(reply);
            console.log(`🔊 [NLC-TTS] Reply audio generated`);
        } catch (ttsErr) {
            console.error('NLC TTS Error (non-fatal):', ttsErr.message);
        }

        cleanupFile(req.file.path);

        console.log(`🎮 [NLC] Action: ${action}, Reply: "${reply}"`);

        res.json({
            text_in: recognizedText.trim(),
            action: action,
            params: params,
            reply: reply,
            audio_base64: audioBase64,
            patient_name: patient.name
        });

    } catch (err) {
        cleanupFile(req.file.path);
        console.error('NLC voice command error:', err.message);
        res.status(500).json({ error: '语音控制处理失败: ' + err.message });
    }
});

// POST /api/voice/device/tts - Text-to-Speech only (for device playback)
router.post('/device/tts', async (req, res) => {
    const apiKey = req.headers['x-device-key'] || req.query.key;
    if (apiKey !== process.env.DEVICE_API_KEY) {
        return res.status(401).json({ error: '设备认证失败' });
    }

    const { text } = req.body;
    if (!text) return res.status(400).json({ error: '缺少文本' });

    try {
        const audioBase64 = await callCosyVoiceTTS(text);
        res.json({ audio_base64: audioBase64 });
    } catch (err) {
        res.status(500).json({ error: 'TTS失败: ' + err.message });
    }
});


// ═══════════════════════════════════════════════════════════
//  WEB API: Browser-side endpoints (for dashboard/family)
// ═══════════════════════════════════════════════════════════

// POST /api/voice/chat - Text chat (web interface fallback)
router.post('/chat', authMiddleware, async (req, res) => {
    const db = req.app.locals.db;
    const { patient_id, message } = req.body;

    if (!patient_id || !message) {
        return res.status(400).json({ error: '请提供患者ID和对话内容' });
    }

    const patient = db.prepare('SELECT * FROM patients WHERE id = ?').get(patient_id);
    if (!patient) return res.status(404).json({ error: '患者不存在' });

    const history = db.prepare(`
        SELECT role, content FROM voice_conversations 
        WHERE patient_id = ? ORDER BY created_at DESC LIMIT 10
    `).all(patient_id).reverse();

    db.prepare(
        'INSERT INTO voice_conversations (patient_id, role, content) VALUES (?, ?, ?)'
    ).run(patient_id, 'user', message);

    const systemPrompt = `你是一位温暖、耐心的AI陪护助手，正在和一位意识清醒的住院患者聊天。
患者信息：${patient.name}，${patient.age}岁，${patient.gender}，患有${patient.disease_type}（${patient.disease_detail || ''}）。
回答简洁温暖，每次100字以内，用中文回答。`;

    const messages = history.map(h => ({
        role: h.role === 'user' ? 'user' : 'assistant',
        content: h.content
    }));
    messages.push({ role: 'user', content: message });

    try {
        const aiResponse = await callKimiAPIWithHistory(systemPrompt, messages);
        db.prepare(
            'INSERT INTO voice_conversations (patient_id, role, content) VALUES (?, ?, ?)'
        ).run(patient_id, 'assistant', aiResponse);
        res.json({ response: aiResponse, patient_name: patient.name });
    } catch (err) {
        console.error('Voice chat error:', err.message);
        res.status(500).json({ error: 'AI陪聊失败: ' + err.message });
    }
});

// GET /api/voice/conversations/:patientId
router.get('/conversations/:patientId', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { patientId } = req.params;
    const { limit = 50 } = req.query;

    const conversations = db.prepare(`
        SELECT * FROM voice_conversations 
        WHERE patient_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    `).all(patientId, parseInt(limit));

    res.json(conversations.reverse());
});

// GET /api/voice/concerns/:patientId
router.get('/concerns/:patientId', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    const { patientId } = req.params;

    const concerns = db.prepare(`
        SELECT * FROM patient_concerns 
        WHERE patient_id = ? 
        ORDER BY generated_at DESC 
        LIMIT 10
    `).all(patientId);

    res.json(concerns);
});

// POST /api/voice/concerns/generate/:patientId
router.post('/concerns/generate/:patientId', authMiddleware, async (req, res) => {
    const db = req.app.locals.db;
    const { patientId } = req.params;

    const patient = db.prepare('SELECT * FROM patients WHERE id = ?').get(patientId);
    if (!patient) return res.status(404).json({ error: '患者不存在' });

    const conversations = db.prepare(`
        SELECT role, content, created_at FROM voice_conversations 
        WHERE patient_id = ? AND created_at >= datetime('now', '-3 days')
        ORDER BY created_at ASC
    `).all(patientId);

    if (conversations.length === 0) {
        return res.status(400).json({ error: '近3天暂无对话记录，无法生成关注点分析' });
    }

    const chatLog = conversations.map(c =>
        `[${c.created_at}] ${c.role === 'user' ? '患者' : 'AI'}：${c.content}`
    ).join('\n');

    const prompt = `以下是患者 ${patient.name}（${patient.age}岁，${patient.gender}，${patient.disease_type}）最近3天和AI陪护助手的对话记录：

${chatLog}

请分析这些对话，总结患者最关心的问题和情绪状态。用JSON格式输出：
{
  "top_concerns": ["关注点1", "关注点2", "关注点3"],
  "emotional_state": "情绪状态描述（50字内）",
  "physical_complaints": ["身体不适1", "身体不适2"],
  "needs": ["需求1", "需求2"],
  "summary": "整体总结（100-200字，包含患者的心理状态、主要诉求和建议家属关注的方面）"
}`;

    try {
        const aiResponse = await callKimiAPI('你是一位专业的医疗心理分析师，请用中文分析患者的对话内容。', prompt);

        let parsed;
        try {
            const jsonMatch = aiResponse.match(/\{[\s\S]*\}/);
            parsed = jsonMatch ? JSON.parse(jsonMatch[0]) : { summary: aiResponse };
        } catch (e) {
            parsed = { summary: aiResponse };
        }

        db.prepare(`
            INSERT INTO patient_concerns (patient_id, top_concerns, emotional_state, physical_complaints, needs, summary, conversation_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        `).run(
            patientId,
            JSON.stringify(parsed.top_concerns || []),
            parsed.emotional_state || '',
            JSON.stringify(parsed.physical_complaints || []),
            JSON.stringify(parsed.needs || []),
            parsed.summary || '',
            conversations.length
        );

        const latest = db.prepare(
            'SELECT * FROM patient_concerns WHERE patient_id = ? ORDER BY generated_at DESC LIMIT 1'
        ).get(patientId);

        res.json(latest);
    } catch (err) {
        console.error('Concern analysis error:', err.message);
        res.status(500).json({ error: '关注点分析失败: ' + err.message });
    }
});

// ═══════════════════════════════════════════════════════════
//  Helper Functions
// ═══════════════════════════════════════════════════════════

// ─── 讯飞 实时语音转写大模型 ASR (Python 桥接) ───
// Node.js ws 库与讯飞 WS 服务器不兼容 (HPE_INVALID_STATUS)
// 改用 Python websocket-client 库通过 child_process 调用
function callXfyunASR(audioBuffer, filename) {
    return new Promise((resolve, reject) => {
        const { execFile } = require('child_process');

        // 将音频保存到临时文件
        const tmpFile = path.join(__dirname, '..', 'uploads', `asr_tmp_${Date.now()}.wav`);
        fs.writeFileSync(tmpFile, audioBuffer);

        const scriptPath = path.join(__dirname, '..', 'scripts', 'xfyun_asr.py');
        console.log(`📡 [ASR] Calling Python xfyun_asr.py (${audioBuffer.length} bytes)...`);

        // 传递环境变量给 Python 进程
        const env = {
            ...process.env,
            XFYUN_APP_ID: process.env.XFYUN_APP_ID,
            XFYUN_API_KEY: process.env.XFYUN_API_KEY,
            XFYUN_API_SECRET: process.env.XFYUN_API_SECRET
        };

        execFile('python3', [scriptPath, tmpFile], {
            env: env,
            timeout: 30000,
            maxBuffer: 1024 * 1024
        }, (error, stdout, stderr) => {
            // 清理临时文件
            try { fs.unlinkSync(tmpFile); } catch (e) { }

            if (stderr) {
                // stderr 是日志信息, 转发到 console
                stderr.split('\n').forEach(line => {
                    if (line.trim()) console.log(`📡 [ASR-PY] ${line.trim()}`);
                });
            }

            if (error) {
                console.error(`❌ [ASR] Python error: ${error.message}`);
                return resolve('');  // 不 reject, 防止全链路崩溃
            }

            const text = (stdout || '').trim();
            console.log(`📝 [ASR] Python result: "${text}"`);
            resolve(text);
        });
    });
}


// ─── 阿里云 CosyVoice TTS (DashScope WebSocket API) ───
// 官方文档: https://help.aliyun.com/zh/model-studio/cosyvoice-websocket-api
// WebSocket URL: wss://dashscope.aliyuncs.com/api-ws/v1/inference/
function callCosyVoiceTTS(text) {
    return new Promise((resolve, reject) => {
        const apiKey = process.env.DASHSCOPE_API_KEY;
        if (!apiKey) {
            return reject(new Error('DASHSCOPE_API_KEY 未配置'));
        }

        const model = process.env.COSYVOICE_MODEL || 'cosyvoice-v3-plus';
        const voice = process.env.COSYVOICE_VOICE_ID || 'longanyang';
        const taskId = crypto.randomBytes(16).toString('hex');

        console.log(`🔊 [TTS] CosyVoice model=${model}, voice=${voice}, text="${text.substring(0, 50)}..."`);

        const wsUrl = 'wss://dashscope.aliyuncs.com/api-ws/v1/inference/';
        const ws = new WebSocket(wsUrl, {
            headers: {
                'Authorization': `bearer ${apiKey}`,
                'X-DashScope-DataInspection': 'enable'
            }
        });

        const audioChunks = [];
        let taskStarted = false;
        let timeout = null;

        // 20秒超时
        timeout = setTimeout(() => {
            console.error('⏰ [TTS] Timeout after 20s');
            try { ws.close(); } catch(e) {}
            if (audioChunks.length > 0) {
                const buffer = Buffer.concat(audioChunks);
                resolve(buffer.toString('base64'));
            } else {
                resolve('');
            }
        }, 20000);

        ws.on('open', () => {
            // 发送 run-task 指令
            const runTask = JSON.stringify({
                header: { action: 'run-task', task_id: taskId, streaming: 'duplex' },
                payload: {
                    task_group: 'audio',
                    task: 'tts',
                    function: 'SpeechSynthesizer',
                    model: model,
                    parameters: {
                        text_type: 'PlainText',
                        voice: voice,
                        format: 'mp3',
                        sample_rate: 22050,
                        volume: 50,
                        rate: 1,
                        pitch: 1
                    },
                    input: {}
                }
            });
            ws.send(runTask);
        });

        ws.on('message', (data, isBinary) => {
            if (isBinary) {
                // 二进制数据 = 音频
                audioChunks.push(Buffer.from(data));
            } else {
                try {
                    const msg = JSON.parse(data.toString());
                    const event = msg.header?.event;

                    if (event === 'task-started') {
                        taskStarted = true;
                        // 发送文本 (continue-task)
                        ws.send(JSON.stringify({
                            header: { action: 'continue-task', task_id: taskId, streaming: 'duplex' },
                            payload: { input: { text: text } }
                        }));
                        // 发送 finish-task
                        setTimeout(() => {
                            if (taskStarted) {
                                ws.send(JSON.stringify({
                                    header: { action: 'finish-task', task_id: taskId, streaming: 'duplex' },
                                    payload: { input: {} }
                                }));
                            }
                        }, 500);
                    } else if (event === 'task-finished') {
                        clearTimeout(timeout);
                        const buffer = Buffer.concat(audioChunks);
                        console.log(`🔊 [TTS] Audio generated: ${buffer.length} bytes`);
                        ws.close();
                        resolve(buffer.toString('base64'));
                    } else if (event === 'task-failed') {
                        clearTimeout(timeout);
                        console.error(`❌ [TTS] Task failed: ${msg.header?.error_message}`);
                        ws.close();
                        resolve('');
                    }
                } catch(e) {
                    console.error('[TTS] Parse error:', e.message);
                }
            }
        });

        ws.on('error', (err) => {
            clearTimeout(timeout);
            console.error(`❌ [TTS] WebSocket error: ${err.message}`);
            resolve('');
        });

        ws.on('close', () => {
            clearTimeout(timeout);
        });
    });
}

// 带对话历史的 LLM 调用 — 走统一网关; 语音链路用快模型 (VOICE_LLM_MODEL) + 短回复
function callKimiAPIWithHistory(systemPrompt, messages) {
    return chat(
        [{ role: 'system', content: systemPrompt }, ...messages],
        {
            timeoutMs: 0,                 // 上层各自处理超时; 语音回复 500 token 通常很快
            maxTokens: 500,
            temperature: 1,
            model: process.env.VOICE_LLM_MODEL || process.env.KIMI_MODEL || 'qwen-turbo',
            agentKey: 'companion_agent',  // tuya provider 下路由到情绪陪伴智能体
        }
    );
}

function cleanupFile(filePath) {
    try { if (filePath && fs.existsSync(filePath)) fs.unlinkSync(filePath); } catch (e) { }
}

router.callCosyVoiceTTS = callCosyVoiceTTS;
module.exports = router;
