// 本地静态预览 + CDP 截图: 仅截取热力图卡片, 用于验证改版
const { execFile } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const CDP_PORT = 9788;
const HTTP_PORT = 8123;
const ROOT = path.join(__dirname, '..', 'public');
const OUT = process.argv[2] || 'D:/IOT/figures/shot_heatmap_new.png';

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const get = url => new Promise((res, rej) => http.get(url, r => { let d = ''; r.on('data', c => d += c); r.on('end', () => res(d)); }).on('error', rej));

// 静态服务器: 拦截 auth.js 注入假登录, 拦截所有 /api 返回空以走模拟引擎
const server = http.createServer((req, res) => {
    let url = req.url.split('?')[0];
    if (url.startsWith('/api')) { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end('{}'); }
    if (url === '/') url = '/dashboard.html';
    if (url === '/js/auth.js') {
        res.writeHead(200, { 'Content-Type': 'text/javascript' });
        return res.end("function getUser(){return{role:'user',patient_id:0,username:'demo'};}function apiFetch(){return Promise.resolve(null);}function logout(){}function showToast(){}function formatDateTime(x){return String(x||'').slice(11,16);}window.currentPatientId=0;");
    }
    const fp = path.join(ROOT, url);
    fs.readFile(fp, (err, data) => {
        if (err) { res.writeHead(404); return res.end('404'); }
        res.writeHead(200, { 'Content-Type': MIME[path.extname(fp)] || 'application/octet-stream' });
        res.end(data);
    });
});

(async () => {
    await new Promise(r => server.listen(HTTP_PORT, r));
    execFile(EDGE, [`--remote-debugging-port=${CDP_PORT}`, '--headless=new', '--no-first-run',
        '--disable-gpu', '--force-device-scale-factor=2', `--user-data-dir=D:/IOT/.edge-tmp2`, 'about:blank']);
    let target = null;
    for (let i = 0; i < 30 && !target; i++) {
        await sleep(500);
        try { target = JSON.parse(await get(`http://127.0.0.1:${CDP_PORT}/json/list`)).find(t => t.type === 'page'); } catch (e) {}
    }
    if (!target) throw new Error('Edge CDP 未就绪');
    const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 });
    await new Promise(r => ws.on('open', r));
    let id = 0; const pend = new Map();
    ws.on('message', m => { const j = JSON.parse(m); if (pend.has(j.id)) { pend.get(j.id)(j); pend.delete(j.id); } });
    const cmd = (method, params = {}) => new Promise(res => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });

    await cmd('Page.enable');
    await cmd('Runtime.enable');
    await cmd('Emulation.setDeviceMetricsOverride', { width: 1500, height: 1200, deviceScaleFactor: 2, mobile: false });
    await cmd('Page.navigate', { url: `http://localhost:${HTTP_PORT}/dashboard.html` });
    await sleep(4500);   // 等热力图 + 波形渲染

    // 取热力图卡片的包围盒
    const box = await cmd('Runtime.evaluate', {
        expression: `(function(){var cards=document.querySelectorAll('.card');for(var i=0;i<cards.length;i++){if(cards[i].textContent.indexOf('织物压力热力图')>=0){var r=cards[i].getBoundingClientRect();return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height});}}return 'NOTFOUND';})()`,
        returnByValue: true
    });
    const val = box && box.result && box.result.result && box.result.result.value;
    if (!val || val === 'NOTFOUND') throw new Error('未找到热力图卡片: ' + JSON.stringify(box && box.result));
    const b = JSON.parse(val);
    console.log('  卡片包围盒:', val);
    const shot = await cmd('Page.captureScreenshot', {
        format: 'png',
        clip: { x: b.x, y: b.y, width: b.w, height: b.h, scale: 2 }
    });
    fs.writeFileSync(OUT, Buffer.from(shot.result.data, 'base64'));
    console.log('热力图卡片截图完成:', OUT, `${Math.round(b.w)}x${Math.round(b.h)}`);
    ws.close(); server.close(); process.exit(0);
})().catch(e => { console.error('失败:', e.message); process.exit(1); });
