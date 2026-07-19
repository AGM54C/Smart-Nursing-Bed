// TTS WebSocket 测试脚本 - 在云服务器运行
// node test_tts.js
require('dotenv').config();
const WebSocket = require('ws');
const fs = require('fs');
const crypto = require('crypto');

const apiKey = process.env.DASHSCOPE_API_KEY;
const model = process.env.COSYVOICE_MODEL || 'cosyvoice-v3-plus';
const voice = process.env.COSYVOICE_VOICE_ID || 'longanyang';
const text = '您好张叔，我是您的智能护理助手，今天感觉怎么样？有没有哪里不舒服？';

console.log('API Key:', apiKey ? apiKey.substring(0, 12) + '...' : 'MISSING');
console.log('Model:', model);
console.log('Voice:', voice);
console.log('Text:', text);

const taskId = crypto.randomBytes(16).toString('hex');
const url = 'wss://dashscope.aliyuncs.com/api-ws/v1/inference/';

console.log('\n--- Connecting WebSocket... ---');

const ws = new WebSocket(url, {
    headers: {
        'Authorization': `bearer ${apiKey}`,
        'X-DashScope-DataInspection': 'enable'
    }
});

const audioChunks = [];

ws.on('open', () => {
    console.log('✅ WebSocket connected');
    ws.send(JSON.stringify({
        header: { action: 'run-task', task_id: taskId, streaming: 'duplex' },
        payload: {
            task_group: 'audio', task: 'tts', function: 'SpeechSynthesizer',
            model: model,
            parameters: {
                text_type: 'PlainText', voice: voice,
                format: 'mp3', sample_rate: 22050,
                volume: 50, rate: 1, pitch: 1
            },
            input: {}
        }
    }));
    console.log('📤 Sent run-task');
});

ws.on('message', (data, isBinary) => {
    if (isBinary) {
        audioChunks.push(Buffer.from(data));
        process.stdout.write('.');
    } else {
        const msg = JSON.parse(data.toString());
        const event = msg.header?.event;
        console.log('\n📩 Event:', event);

        if (event === 'task-started') {
            ws.send(JSON.stringify({
                header: { action: 'continue-task', task_id: taskId, streaming: 'duplex' },
                payload: { input: { text: text } }
            }));
            console.log('📤 Sent text');
            setTimeout(() => {
                ws.send(JSON.stringify({
                    header: { action: 'finish-task', task_id: taskId, streaming: 'duplex' },
                    payload: { input: {} }
                }));
                console.log('📤 Sent finish-task');
            }, 500);
        } else if (event === 'task-finished') {
            const buffer = Buffer.concat(audioChunks);
            fs.writeFileSync('/tmp/test_tts.mp3', buffer);
            console.log(`\n✅ Audio saved: /tmp/test_tts.mp3 (${buffer.length} bytes)`);
            ws.close();
        } else if (event === 'task-failed') {
            console.error('❌ Failed:', msg.header?.error_message);
            ws.close();
        }
    }
});

ws.on('error', (err) => console.error('❌ Error:', err.message));
ws.on('close', () => { console.log('🔌 Done'); process.exit(0); });

setTimeout(() => { console.log('\n⏰ Timeout'); process.exit(1); }, 20000);
