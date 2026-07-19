/**
 * 涂鸦云 OpenAPI 通用客户端 (云项目授权密钥签名, 非设备三元组!)
 *
 * 鉴权方式: 涂鸦 v2 签名 (HMAC-SHA256), 官方文档「API 使用指南 → 请求签名」
 *   https://developer.tuya.com/cn/docs/iot/api-reference?id=Ka7qb7vhber64
 *
 * 环境变量:
 *   TUYA_OPENAPI_BASE   默认 https://openapi.tuyacn.com (中国数据中心)
 *   TUYA_ACCESS_ID      云项目「授权密钥」Access ID/Client ID
 *   TUYA_ACCESS_SECRET  云项目 Access Secret/Client Secret
 *
 * 用法:
 *   const tuya = require('./tuya_openapi');
 *   const resp = await tuya.request('POST', '/v2.0/cloud/agent/xxx/chat', { query: '你好' });
 *   // resp = { success, result, code, msg, t }
 */
const https = require('https');
const crypto = require('crypto');

const EMPTY_BODY_SHA256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';

function baseUrl() { return process.env.TUYA_OPENAPI_BASE || 'https://openapi.tuyacn.com'; }
function accessId() { return process.env.TUYA_ACCESS_ID || ''; }
function accessSecret() { return process.env.TUYA_ACCESS_SECRET || ''; }

function sha256Hex(s) { return crypto.createHash('sha256').update(s, 'utf8').digest('hex'); }
function hmacUpper(msg) {
    return crypto.createHmac('sha256', accessSecret()).update(msg, 'utf8').digest('hex').toUpperCase();
}

/**
 * 底层签名请求。pathWithQuery 里如带 query 参数, 必须按字典序排好 (签名要求)。
 */
function rawRequest(method, pathWithQuery, bodyObj, accessToken) {
    return new Promise((resolve, reject) => {
        const body = bodyObj ? JSON.stringify(bodyObj) : '';
        const t = Date.now().toString();
        // stringToSign = Method\nsha256(body)\n(签名头,留空)\npath
        const stringToSign = [
            method.toUpperCase(),
            body ? sha256Hex(body) : EMPTY_BODY_SHA256,
            '',
            pathWithQuery,
        ].join('\n');
        const sign = hmacUpper(accessId() + (accessToken || '') + t + stringToSign);

        const url = new URL(baseUrl());
        const headers = {
            'client_id': accessId(),
            'sign': sign,
            't': t,
            'sign_method': 'HMAC-SHA256',
            'Content-Type': 'application/json',
        };
        if (accessToken) headers['access_token'] = accessToken;
        if (body) headers['Content-Length'] = Buffer.byteLength(body);

        const req = https.request({
            hostname: url.hostname, port: 443, path: pathWithQuery,
            method: method.toUpperCase(), headers, timeout: 30000,
        }, (res) => {
            let data = '';
            res.on('data', c => data += c);
            res.on('end', () => {
                try { resolve(JSON.parse(data)); }
                catch (e) { reject(new Error(`Tuya OpenAPI 非 JSON 响应 (HTTP ${res.statusCode}): ${data.slice(0, 200)}`)); }
            });
        });
        req.on('timeout', () => { req.destroy(new Error('Tuya OpenAPI 请求超时')); });
        req.on('error', reject);
        if (body) req.write(body);
        req.end();
    });
}

// ─── access_token 缓存 (有效期约 2 小时, 提前 60s 刷新) ───
let _token = null;
let _tokenExpireAt = 0;

async function getToken() {
    if (_token && Date.now() < _tokenExpireAt) return _token;
    if (!accessId() || !accessSecret()) {
        throw new Error('未配置 TUYA_ACCESS_ID / TUYA_ACCESS_SECRET (云项目授权密钥, 在平台「云开发」项目里查看)');
    }
    const resp = await rawRequest('GET', '/v1.0/token?grant_type=1', null, null);
    if (!resp.success) {
        throw new Error(`获取涂鸦 access_token 失败: code=${resp.code} msg=${resp.msg}`);
    }
    _token = resp.result.access_token;
    _tokenExpireAt = Date.now() + (resp.result.expire_time - 60) * 1000;
    return _token;
}

/**
 * 带 token 的业务请求; token 过期(code 1010/1011/1012)自动刷新重试一次。
 */
async function request(method, path, bodyObj) {
    let token = await getToken();
    let resp = await rawRequest(method, path, bodyObj, token);
    if (!resp.success && [1010, 1011, 1012].includes(resp.code)) {
        _token = null;                      // token 失效, 强刷一次
        token = await getToken();
        resp = await rawRequest(method, path, bodyObj, token);
    }
    return resp;
}

module.exports = { request, getToken };
