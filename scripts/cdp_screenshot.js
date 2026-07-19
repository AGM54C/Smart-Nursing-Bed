/* 无头 Edge + CDP 截图: 自动登录 → 打开页面 → 全页截屏 (真机截图用) */
const { execFile } = require('child_process');
const http = require('http');
const fs = require('fs');
const WebSocket = require('ws');

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const PORT = 9777;
const BASE = 'http://localhost:3000';
const OUT_DIR = 'D:/IOT/figures';
const PAGES = JSON.parse(process.argv[2] || '[["dashboard.html","shot_dashboard",1600,2400]]');

const get = (url) => new Promise((res, rej) => http.get(url, r => {
    let d = ''; r.on('data', c => d += c); r.on('end', () => res(d));
}).on('error', rej));
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
    execFile(EDGE, [`--remote-debugging-port=${PORT}`, '--headless=new', '--no-first-run',
        '--disable-gpu', '--force-device-scale-factor=1.5', `--user-data-dir=D:/IOT/.edge-tmp`, 'about:blank']);
    let target = null;
    for (let i = 0; i < 30 && !target; i++) {
        await sleep(500);
        try {
            const tabs = JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`));
            target = tabs.find(t => t.type === 'page');
        } catch (e) {}
    }
    if (!target) throw new Error('Edge CDP 未就绪');
    const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 });
    await new Promise(r => ws.on('open', r));
    let id = 0; const pend = new Map();
    ws.on('message', m => { const j = JSON.parse(m); if (pend.has(j.id)) { pend.get(j.id)(j); pend.delete(j.id); } });
    const cmd = (method, params = {}) => new Promise(res => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });

    await cmd('Page.enable');
    // 登录并注入 token
    await cmd('Page.navigate', { url: `${BASE}/login.html` });
    await sleep(1500);
    await cmd('Runtime.evaluate', { expression: `
        fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({username:'admin',password:'admin123'})}).then(r=>r.json()).then(d=>{
          localStorage.setItem('token',d.token); localStorage.setItem('user',JSON.stringify(d.user)); return 'ok';})`,
        awaitPromise: true });

    for (const [page, name, w, h] of PAGES) {
        await cmd('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1.5, mobile: false });
        await cmd('Page.navigate', { url: `${BASE}/${page}` });
        await sleep(5000);                                   // 等图表/热力图渲染
        const shot = await cmd('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
        fs.writeFileSync(`${OUT_DIR}/${name}.png`, Buffer.from(shot.result.data, 'base64'));
        console.log('截图完成:', name, `${w}x${h}`);
    }
    ws.close(); process.exit(0);
})().catch(e => { console.error('失败:', e.message); process.exit(1); });
