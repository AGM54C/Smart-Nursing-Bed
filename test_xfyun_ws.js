// 讯飞实时语音转写大模型 - 连接测试脚本
// 用法: node test_xfyun_ws.js
// 在云服务器上运行验证 WebSocket 连接是否能建立

const crypto = require('crypto');
const WebSocket = require('ws');

const APP_ID = process.env.XFYUN_APP_ID || '';
const API_KEY = process.env.XFYUN_API_KEY || '';
const API_SECRET = process.env.XFYUN_API_SECRET || '';

// 1. 生成 UTC 时间 (ISO 8601)
const now = new Date();
const pad = n => String(n).padStart(2, '0');
const utc = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}+0800`;
const uuid = crypto.randomBytes(16).toString('hex');

console.log('APP_ID:', APP_ID);
console.log('API_KEY:', API_KEY.substring(0, 8) + '...');
console.log('API_SECRET:', API_SECRET.substring(0, 8) + '...');
console.log('UTC:', utc);
console.log('UUID:', uuid);

// 2. 构造参数 (signature 除外, 按key升序)
const rawParams = {
    accessKeyId: API_KEY,
    appId: APP_ID,
    audio_encode: 'pcm_s16le',
    lang: 'autodialect',
    samplerate: '16000',
    utc: utc,
    uuid: uuid
};

// 3. 生成 signature: 排序 → URL编码 → 拼接 → HmacSHA1(apiSecret)
const sortedKeys = Object.keys(rawParams).sort();
const baseString = sortedKeys.map(k => `${encodeURIComponent(k)}=${encodeURIComponent(rawParams[k])}`).join('&');
console.log('\nbaseString:', baseString);

const signature = crypto.createHmac('sha1', API_SECRET).update(baseString).digest('base64');
console.log('signature:', signature);

// 4. 构造完整 URL
const wsBase = 'wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1';
const allParams = { ...rawParams, signature: signature };
const queryString = Object.keys(allParams).map(k => `${encodeURIComponent(k)}=${encodeURIComponent(allParams[k])}`).join('&');
const wsUrl = `${wsBase}?${queryString}`;

console.log('\nFull URL:', wsUrl);
console.log('URL length:', wsUrl.length, 'chars');

// 5. 尝试连接
console.log('\n--- Connecting... ---');
const ws = new WebSocket(wsUrl, {
    maxPayload: 1024 * 1024,
    handshakeTimeout: 10000
});

ws.on('open', () => {
    console.log('✅ WebSocket CONNECTED!');
    // 发送一小段静音 PCM (1280 bytes = 40ms of silence)
    const silence = Buffer.alloc(1280, 0);
    ws.send(silence);
    console.log('Sent 1280 bytes silence');
    
    // 发送结束标识
    setTimeout(() => {
        ws.send(JSON.stringify({ end: true }));
        console.log('Sent end marker');
    }, 500);
});

ws.on('message', (data) => {
    console.log('📩 Message:', data.toString().substring(0, 300));
});

ws.on('error', (err) => {
    console.error('❌ Error:', err.message);
    console.error('Error code:', err.code);
});

ws.on('close', (code, reason) => {
    console.log('🔌 Closed:', code, reason?.toString());
    process.exit(0);
});

// 超时退出
setTimeout(() => {
    console.log('⏰ Timeout, exiting...');
    ws.close();
    process.exit(0);
}, 15000);
