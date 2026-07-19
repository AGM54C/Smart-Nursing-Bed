/**
 * 语音流式交互 WebSocket 处理器
 * 
 * 协议:
 *   客户端 → 服务端:
 *     { type: "config", patient_id: 1, sample_rate: 48000 }  // 初始化
 *     { type: "audio", data: "<base64 PCM>" }                // 音频帧
 *     { type: "end" }                                         // 录音结束
 *   
 *   服务端 → 客户端:
 *     { type: "asr", text: "识别文本" }             // ASR 结果
 *     { type: "llm_start" }                          // LLM 开始
 *     { type: "llm_text", text: "一句话" }           // LLM 文本片段
 *     { type: "tts_audio", data: "<base64 mp3>" }    // TTS 音频片段
 *     { type: "done" }                                // 全部完成
 *     { type: "error", message: "..." }               // 错误
 */

const { spawn } = require('child_process');
const WebSocket = require('ws');
const path = require('path');
const https = require('https');
const crypto = require('crypto');

// ─── 流式 LLM 调用 (SSE) ───
// ⚠️ 此文件有意不走 services/llm.js 统一网关: 逐句流式打断 (LLM delta → 断句 → CosyVoice TTS)
//    依赖 SSE 增量输出, 涂鸦智能体 API 为整段返回; 且 TTS 本就绑定 DashScope, 语音链路整体留在百炼。
function streamLLM(systemPrompt, messages, onSentence, onDone) {
    const postData = JSON.stringify({
        model: process.env.VOICE_LLM_MODEL || process.env.KIMI_MODEL || 'qwen-turbo',
        messages: [{ role: 'system', content: systemPrompt }, ...messages],
        stream: true,
        max_tokens: 200,
        temperature: 0.8
    });

    const url = new URL(process.env.KIMI_BASE_URL + '/chat/completions');
    let fullText = '';
    let sentenceBuffer = '';

    const req = https.request({
        hostname: url.hostname, port: 443, path: url.pathname, method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${process.env.KIMI_API_KEY}`,
            'Content-Length': Buffer.byteLength(postData)
        }
    }, (res) => {
        if (res.statusCode !== 200) {
            let raw = '';
            res.on('data', c => raw += c);
            res.on('end', () => {
                try { onDone(new Error(JSON.parse(raw)?.error?.message || `HTTP ${res.statusCode}`), ''); }
                catch(e) { onDone(new Error(`HTTP ${res.statusCode}`), ''); }
            });
            return;
        }

        let residual = '';
        res.on('data', (chunk) => {
            const text = residual + chunk.toString();
            residual = '';
            for (const line of text.split('\n')) {
                const trimmed = line.trim();
                if (!trimmed) continue;
                if (!trimmed.startsWith('data: ')) {
                    residual = line;
                    continue;
                }
                const data = trimmed.slice(6);
                if (data === '[DONE]') continue;
                try {
                    const delta = JSON.parse(data).choices?.[0]?.delta?.content;
                    if (delta) {
                        fullText += delta;
                        sentenceBuffer += delta;
                        // 按句号/问号/感叹号断句
                        const sentEnd = sentenceBuffer.search(/[。！？!?]\s*/);
                        if (sentEnd !== -1) {
                            const sentence = sentenceBuffer.substring(0, sentEnd + 1);
                            sentenceBuffer = sentenceBuffer.substring(sentEnd + 1);
                            if (sentence.trim()) {
                                onSentence(sentence.trim());
                            }
                        }
                    }
                } catch(e) {}
            }
        });

        res.on('end', () => {
            // 发送剩余文本
            if (sentenceBuffer.trim()) {
                onSentence(sentenceBuffer.trim());
            }
            onDone(null, fullText);
        });
    });

    req.on('error', (err) => onDone(err, fullText));
    req.write(postData);
    req.end();
}

// ─── 流式 TTS (逐句合成) ───
function streamTTSsentence(text, onAudioChunk) {
    return new Promise((resolve, reject) => {
        const apiKey = process.env.DASHSCOPE_API_KEY;
        const model = process.env.COSYVOICE_MODEL || 'cosyvoice-v3-flash';
        const voice = process.env.COSYVOICE_VOICE_ID || 'longanyang';
        const taskId = crypto.randomBytes(16).toString('hex');

        const wsUrl = 'wss://dashscope.aliyuncs.com/api-ws/v1/inference/';
        const ws = new WebSocket(wsUrl, {
            headers: { 'Authorization': `bearer ${apiKey}` }
        });

        let timeout = setTimeout(() => {
            try { ws.close(); } catch(e) {}
            resolve();
        }, 15000);

        ws.on('open', () => {
            ws.send(JSON.stringify({
                header: { action: 'run-task', task_id: taskId, streaming: 'duplex' },
                payload: {
                    task_group: 'audio', task: 'tts', function: 'SpeechSynthesizer',
                    model, parameters: { text_type: 'PlainText', voice, format: 'mp3', sample_rate: 22050, volume: 50, rate: 1, pitch: 1 },
                    input: {}
                }
            }));
        });

        ws.on('message', (data, isBinary) => {
            if (isBinary) {
                onAudioChunk(Buffer.from(data));
            } else {
                try {
                    const msg = JSON.parse(data.toString());
                    const event = msg.header?.event;
                    if (event === 'task-started') {
                        ws.send(JSON.stringify({
                            header: { action: 'continue-task', task_id: taskId, streaming: 'duplex' },
                            payload: { input: { text } }
                        }));
                        setTimeout(() => {
                            try {
                                ws.send(JSON.stringify({
                                    header: { action: 'finish-task', task_id: taskId, streaming: 'duplex' },
                                    payload: { input: {} }
                                }));
                            } catch(e) {}
                        }, 300);
                    } else if (event === 'task-finished') {
                        clearTimeout(timeout);
                        ws.close();
                        resolve();
                    } else if (event === 'task-failed') {
                        clearTimeout(timeout);
                        ws.close();
                        resolve();
                    }
                } catch(e) {}
            }
        });

        ws.on('error', () => { clearTimeout(timeout); resolve(); });
        ws.on('close', () => { clearTimeout(timeout); resolve(); });
    });
}

// ─── WebSocket 处理器 ───
function setupVoiceStream(wss, db) {
    wss.on('connection', (clientWs) => {
        console.log('🔌 [VoiceStream] Client connected');
        let asrProcess = null;
        let configured = false;
        let patientId = null;
        let sampleRate = 48000;

        function send(obj) {
            if (clientWs.readyState === WebSocket.OPEN) {
                clientWs.send(JSON.stringify(obj));
            }
        }

        function sendBinary(buf) {
            if (clientWs.readyState === WebSocket.OPEN) {
                clientWs.send(buf);
            }
        }

        clientWs.on('message', async (rawData, isBinary) => {
            // Binary = audio frame, 直接转发给 ASR 子进程
            if (isBinary) {
                if (asrProcess && asrProcess.stdin.writable) {
                    const b64 = Buffer.from(rawData).toString('base64');
                    asrProcess.stdin.write(`AUDIO:${b64}\n`);
                }
                return;
            }

            let msg;
            try { msg = JSON.parse(rawData.toString()); } catch(e) { return; }

            if (msg.type === 'config') {
                patientId = msg.patient_id;
                sampleRate = msg.sample_rate || 48000;
                configured = true;

                // 启动 ASR 子进程
                const scriptPath = path.join(__dirname, '..', 'scripts', 'xfyun_asr_stream.py');
                asrProcess = spawn('python3', [scriptPath], {
                    env: { ...process.env },
                    stdio: ['pipe', 'pipe', 'pipe']
                });

                // 发送配置给 ASR 子进程
                asrProcess.stdin.write(JSON.stringify({ sample_rate: sampleRate }) + '\n');

                // ASR 子进程 stdout → JSON lines
                let asrBuffer = '';
                asrProcess.stdout.on('data', (data) => {
                    asrBuffer += data.toString();
                    const lines = asrBuffer.split('\n');
                    asrBuffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.trim()) continue;
                        try {
                            const result = JSON.parse(line);
                            if (result.done) {
                                // ASR 完成, 开始 LLM
                                const finalText = result.text || '';
                                console.log(`📝 [VoiceStream] ASR final: "${finalText}"`);
                                send({ type: 'asr', text: finalText });

                                if (finalText.trim()) {
                                    startLLMAndTTS(finalText);
                                } else {
                                    send({ type: 'done' });
                                }
                            } else if (result.text) {
                                // ASR 中间结果
                                send({ type: 'asr_partial', text: result.text });
                            }
                        } catch(e) {}
                    }
                });

                asrProcess.stderr.on('data', (data) => {
                    data.toString().split('\n').forEach(line => {
                        if (line.trim()) console.log(`📡 [ASR-Stream] ${line.trim()}`);
                    });
                });

                asrProcess.on('close', () => { asrProcess = null; });

                send({ type: 'ready' });
                console.log(`🎤 [VoiceStream] Configured: patient=${patientId}, rate=${sampleRate}`);

            } else if (msg.type === 'audio' && msg.data) {
                // Base64 文本模式音频帧
                if (asrProcess && asrProcess.stdin.writable) {
                    asrProcess.stdin.write(`AUDIO:${msg.data}\n`);
                }

            } else if (msg.type === 'end') {
                // 录音结束
                if (asrProcess && asrProcess.stdin.writable) {
                    asrProcess.stdin.write('END\n');
                }
            }
        });

        // LLM → TTS 流水线
        async function startLLMAndTTS(userText) {
            const patient = db.prepare('SELECT * FROM patients WHERE id = ?').get(patientId);
            const patientInfo = patient
                ? `${patient.name}，${patient.age}岁，${patient.gender}，患有${patient.disease_type}`
                : '未知患者';

            const systemPrompt = `你是一位温暖、耐心的AI陪护助手，正在和住院患者语音聊天。
患者信息：${patientInfo}。
要求：
1. 语气亲切温暖，像家人朋友一样
2. 回答简洁自然，每次40字以内
3. 用中文口语化表达`;

            // 获取对话历史
            const history = db.prepare(
                'SELECT role, content FROM voice_conversations WHERE patient_id = ? ORDER BY created_at DESC LIMIT 6'
            ).all(patientId || 1).reverse();

            // 保存用户消息
            if (patientId) {
                db.prepare('INSERT INTO voice_conversations (patient_id, role, content) VALUES (?, ?, ?)').run(patientId, 'user', userText);
            }

            const messages = [
                ...history.map(h => ({ role: h.role === 'user' ? 'user' : 'assistant', content: h.content })),
                { role: 'user', content: userText }
            ];

            send({ type: 'llm_start' });
            console.log(`🤖 [VoiceStream] LLM starting...`);

            let sentenceQueue = [];
            let ttsRunning = false;
            let llmDone = false;
            let fullResponse = '';

            async function processTTSQueue() {
                if (ttsRunning) return;
                ttsRunning = true;

                while (sentenceQueue.length > 0) {
                    const sentence = sentenceQueue.shift();
                    console.log(`🔊 [VoiceStream] TTS: "${sentence}"`);

                    await streamTTSsentence(sentence, (audioChunk) => {
                        // 发送 TTS 音频帧（二进制）给客户端
                        sendBinary(audioChunk);
                    });
                }

                ttsRunning = false;

                if (llmDone && sentenceQueue.length === 0) {
                    send({ type: 'done' });
                    console.log(`✅ [VoiceStream] Pipeline complete`);
                }
            }

            streamLLM(systemPrompt, messages,
                // onSentence
                (sentence) => {
                    fullResponse += sentence;
                    send({ type: 'llm_text', text: sentence });
                    sentenceQueue.push(sentence);
                    processTTSQueue();
                },
                // onDone
                (err, fullText) => {
                    llmDone = true;
                    if (err) {
                        console.error(`❌ [VoiceStream] LLM error: ${err.message}`);
                        send({ type: 'error', message: err.message });
                        return;
                    }
                    console.log(`🤖 [VoiceStream] LLM full: "${fullText}"`);

                    // 保存 AI 回复
                    if (patientId && fullText) {
                        db.prepare('INSERT INTO voice_conversations (patient_id, role, content) VALUES (?, ?, ?)').run(patientId, 'assistant', fullText);
                    }

                    // 如果队列空了且TTS没在跑，直接完成
                    if (sentenceQueue.length === 0 && !ttsRunning) {
                        send({ type: 'done' });
                        console.log(`✅ [VoiceStream] Pipeline complete`);
                    }
                }
            );
        }

        clientWs.on('close', () => {
            console.log('🔌 [VoiceStream] Client disconnected');
            if (asrProcess) {
                try { asrProcess.kill(); } catch(e) {}
            }
        });

        clientWs.on('error', (err) => {
            console.error('❌ [VoiceStream] Error:', err.message);
        });
    });
}

module.exports = { setupVoiceStream };
