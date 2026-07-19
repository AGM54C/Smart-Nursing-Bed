/**
 * 统一 LLM 网关 — 服务端所有 AI 调用的唯一出口 (2026-07 涂鸦迁移新增, 07-19 kimi-k3 三级降级)
 *
 * 降级链 (上一级任何失败自动落到下一级, 演示永不中断; LLM_FALLBACK=off 关闭降级):
 *
 *   LLM_PROVIDER=tuya   : 涂鸦智能体 → Moonshot kimi-k3 → SiliconFlow
 *   LLM_PROVIDER=openai : Moonshot kimi-k3 → SiliconFlow
 *
 *   涂鸦智能体 — 「智能体开放接口」(云项目签名鉴权, 消耗涂鸦大模型额度)
 *     系统提示词配置在平台侧智能体上, 本地 system 消息默认不发送 (TUYA_SEND_SYSTEM=1 可折叠进正文)
 *     配置: TUYA_ACCESS_ID + TUYA_ACCESS_SECRET + TUYA_AGENT_ID(可按科室细分, 见 resolveAgentId)
 *     ⚠️ 官方文档未公开对话端点路径("开放能力持续完善中") → 内置候选路径探测,
 *        TUYA_AGENT_CHAT_PATH 可锁定; 一键体检: node scripts/probe_tuya_agent_api.js
 *
 *   Moonshot kimi-k3 — 主力大模型 (K2.5 已下架, 2026-07 切 K3)
 *     配置: MOONSHOT_API_KEY (+ MOONSHOT_MODEL 默认 kimi-k3, MOONSHOT_BASE_URL 默认官方)
 *     未配 key 时本级自动跳过。K3 特性适配:
 *       - 始终开启思考模式 → 只拼 delta.content, reasoning_content 自动忽略
 *       - temperature/top_p 为固定值 → 不显式传入
 *       - 长度参数用 max_completion_tokens (K3 文档口径)
 *       - 思考模式时延高 → 语音链路(带 opts.model 快模型覆盖的调用)跳过本级直走 SiliconFlow
 *
 *   SiliconFlow — 保底 (KIMI_* 变量, 兼容历史命名; KIMI_MODEL 默认 deepseek-ai/DeepSeek-V3)
 *
 * 唯一入口:
 *   chat(messages, opts) -> Promise<string|null>
 *     messages: [{role:'system'|'user'|'assistant', content}]
 *     opts.timeoutMs    超时毫秒; 超时 resolve opts.fallback (默认 null); 传 0 = 不限时 (报告生成用)
 *     opts.maxTokens    默认 2000
 *     opts.temperature  默认 1 (kimi-k3 级忽略 — 官方固定值)
 *     opts.agentKey     业务侧智能体名 (quadriplegia/diabetes/.../pressure_agent), tuya 级用它挑 agent_id
 *     opts.fallback     超时兜底返回值 (agents.js 的 no_action JSON 用)
 *     opts.model        快模型覆盖 (语音链路 VOICE_LLM_MODEL): 只作用于 SiliconFlow 级并跳过 kimi-k3 级
 */
const https = require('https');

function provider() { return (process.env.LLM_PROVIDER || 'openai').toLowerCase(); }
function fallbackEnabled() { return (process.env.LLM_FALLBACK || 'on').toLowerCase() !== 'off'; }

// ═══════════════ OpenAI 兼容端点通用实现 ═══════════════
// stream:true + 按行解析 SSE (实测可绕开长响应 socket hang up); 思考型模型的
// delta.reasoning_content 不在解析路径上, 天然只拼最终答案 delta.content
function openaiCompatChat(messages, { maxTokens, temperature, endpoint }) {
    return new Promise((resolve, reject) => {
        const payload = {
            model: endpoint.model,
            messages,
            stream: true,
        };
        if (endpoint.isK3) {
            // kimi-k3: temperature/top_p 固定值不传; 长度参数用 max_completion_tokens
            payload.max_completion_tokens = maxTokens;
        } else {
            payload.max_tokens = maxTokens;
            payload.temperature = temperature;
        }
        const postData = JSON.stringify(payload);
        const url = new URL(endpoint.base + '/chat/completions');
        const req = https.request({
            hostname: url.hostname, port: 443, path: url.pathname, method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${endpoint.key}`,
                'Content-Length': Buffer.byteLength(postData),
            },
        }, (res) => {
            let raw = '';
            res.on('data', c => raw += c);
            res.on('end', () => {
                if (res.statusCode !== 200) {
                    try { reject(new Error(JSON.parse(raw)?.error?.message || `HTTP ${res.statusCode}`)); }
                    catch (e) { reject(new Error(`HTTP ${res.statusCode}`)); }
                    return;
                }
                // 逐行拼接 SSE 的 delta.content
                let content = '';
                for (const line of raw.split('\n')) {
                    const trimmed = line.trim();
                    if (!trimmed.startsWith('data: ')) continue;
                    const data = trimmed.slice(6);
                    if (data === '[DONE]') break;
                    try {
                        const delta = JSON.parse(data).choices?.[0]?.delta?.content;
                        if (delta) content += delta;
                    } catch (e) {}
                }
                if (content) return resolve(content);
                // 个别端点会无视 stream 参数直接回非流式 JSON — 兜底解析
                try {
                    const j = JSON.parse(raw);
                    const c = j.choices?.[0]?.message?.content;
                    if (c) return resolve(c);
                    if (j.error) return reject(new Error(j.error.message || 'API error'));
                } catch (e) {}
                reject(new Error('Empty response from LLM'));
            });
        });
        req.on('error', reject);
        req.write(postData);
        req.end();
    });
}

// ── 各级端点配置 ──
function moonshotEndpoint() {
    if (!process.env.MOONSHOT_API_KEY) return null;      // 未配 key → 本级跳过
    return {
        name: 'kimi-k3',
        base: process.env.MOONSHOT_BASE_URL || 'https://api.moonshot.cn/v1',
        key: process.env.MOONSHOT_API_KEY,
        model: process.env.MOONSHOT_MODEL || 'kimi-k3',
        isK3: true,
    };
}
function siliconflowEndpoint(modelOverride) {
    return {
        name: 'siliconflow',
        base: process.env.KIMI_BASE_URL || 'https://api.siliconflow.cn/v1',
        key: process.env.KIMI_API_KEY,
        model: modelOverride || process.env.KIMI_MODEL || 'deepseek-ai/DeepSeek-V3',
        isK3: false,
    };
}

// ═══════════════ 涂鸦智能体开放接口 ═══════════════
// 业务智能体名 -> 平台 agent_id: 先找 TUYA_AGENT_ID_<大写名>, 找不到用 TUYA_AGENT_ID 兜底
// 例: quadriplegia -> TUYA_AGENT_ID_QUADRIPLEGIA, pressure_agent -> TUYA_AGENT_ID_PRESSURE_AGENT
function resolveAgentId(agentKey) {
    if (agentKey) {
        const specific = process.env[`TUYA_AGENT_ID_${String(agentKey).toUpperCase()}`];
        if (specific) return specific;
    }
    const def = process.env.TUYA_AGENT_ID;
    if (!def) throw new Error('未配置 TUYA_AGENT_ID (平台「AI 智能体开发」列表里复制智能体 ID)');
    return def;
}

// 候选对话路径 — 按涂鸦 OpenAPI 命名惯例排列, 探通即缓存。
// 官方未公开真实路径 (见文件头注释), API Explorer 查到后填 TUYA_AGENT_CHAT_PATH 直接锁定。
const TUYA_CANDIDATE_PATHS = [
    '/v2.0/cloud/agent/{agent_id}/chat',
    '/v1.0/cloud/agent/{agent_id}/chat',
    '/v2.0/ai/agents/{agent_id}/chat',
    '/v1.0/ai/agents/{agent_id}/chat',
    '/v2.0/cloud/ai-agent/{agent_id}/chat',
    '/v1.0/cloud/ai-agent/{agent_id}/chat',
];
// 判定为「路径/权限不对, 换下一个试」的错误码:
// 1106 权限非法(未订阅服务也报这个) / 1108 uri path invalid / 1004 签名错(个别网关对未知路径返回)
const TUYA_TRY_NEXT_CODES = new Set([1106, 1108, 1004]);
let _tuyaWorkingPath = null;          // 进程内缓存探通的路径

// 多轮消息折叠成单条 query — 平台侧智能体自带人设与系统提示词
function flattenMessages(messages) {
    const parts = [];
    for (const m of messages) {
        if (m.role === 'system') {
            if (process.env.TUYA_SEND_SYSTEM === '1') parts.push(`[系统指令]\n${m.content}`);
            continue;   // 默认跳过: 提示词已配在平台智能体上, 重复发送浪费额度
        }
        if (m.role === 'assistant') parts.push(`[助手上文]\n${m.content}`);
        else parts.push(m.content);
    }
    return parts.join('\n\n');
}

// 涂鸦返回体形态未定 — 递归找第一个像回答的字符串字段
function extractAnswer(result) {
    if (result == null) return null;
    if (typeof result === 'string') return result;
    if (typeof result !== 'object') return null;
    for (const key of ['answer', 'content', 'reply', 'message', 'text', 'output', 'data', 'result']) {
        if (key in result) {
            const v = extractAnswer(result[key]);
            if (v) return v;
        }
    }
    // OpenAI 透传形态
    const c = result.choices?.[0]?.message?.content;
    if (c) return c;
    return null;
}

async function tuyaChatOnce(path, agentId, query) {
    const tuya = require('./tuya_openapi');
    return tuya.request('POST', path.replace('{agent_id}', agentId), {
        agent_id: agentId,
        query,
        stream: false,
    });
}

async function tuyaChat(messages, { agentKey }) {
    const agentId = resolveAgentId(agentKey);
    const query = flattenMessages(messages);
    const pinned = process.env.TUYA_AGENT_CHAT_PATH;    // 锁定路径 (API Explorer 里查到的真实值)
    const paths = pinned ? [pinned] : (_tuyaWorkingPath ? [_tuyaWorkingPath] : TUYA_CANDIDATE_PATHS);

    const failures = [];
    for (const p of paths) {
        const resp = await tuyaChatOnce(p, agentId, query);
        if (resp.success) {
            const answer = extractAnswer(resp.result);
            if (!answer) throw new Error(`涂鸦智能体返回成功但解析不到回答: ${JSON.stringify(resp.result).slice(0, 200)}`);
            if (!pinned && _tuyaWorkingPath !== p) {
                _tuyaWorkingPath = p;
                console.log(`[llm] 涂鸦智能体对话路径探测成功: ${p} (固化请在 .env 设 TUYA_AGENT_CHAT_PATH=${p})`);
            }
            return answer;
        }
        failures.push(`${p} → code=${resp.code} ${resp.msg}`);
        if (!TUYA_TRY_NEXT_CODES.has(Number(resp.code))) {
            // 非路径类错误 (额度耗尽/参数错/服务端异常) — 没必要再试别的路径
            throw new Error(`涂鸦智能体 API 失败: ${failures[failures.length - 1]}`);
        }
    }
    throw new Error(`涂鸦智能体对话路径均不可用:\n  ${failures.join('\n  ')}\n` +
        `  → 平台「云开发→API Explorer」搜索智能体对话接口, 把真实路径填入 .env 的 TUYA_AGENT_CHAT_PATH`);
}

// ═══════════════ 统一入口 ═══════════════
// promise 在 ms 内没结果就 reject (与外层 resolve(fallback) 的 race 语义不同 — 这里要触发降级)
function rejectAfter(promise, ms, label) {
    if (!ms) return promise;
    let timer;
    return Promise.race([
        promise.finally(() => clearTimeout(timer)),
        new Promise((_, rej) => { timer = setTimeout(() => rej(new Error(`${label} 超时 ${ms}ms`)), ms); }),
    ]);
}

async function chat(messages, opts = {}) {
    const {
        timeoutMs = 30000,
        maxTokens = 2000,
        temperature = 1,
        agentKey = null,
        fallback = null,
        model = null,          // 快模型覆盖 (语音链路): 跳过 kimi-k3 级, 只作用于 SiliconFlow 级
    } = opts;

    const call = (async () => {
        // ── 组装降级链 ──
        const tiers = [];
        if (provider() === 'tuya') {
            const tuyaBudget = Number(process.env.TUYA_TIMEOUT_MS) ||
                (timeoutMs ? Math.min(15000, Math.max(5000, Math.floor(timeoutMs / 2))) : 30000);
            tiers.push({
                name: '涂鸦智能体',
                run: () => rejectAfter(tuyaChat(messages, { agentKey }), tuyaBudget, '涂鸦智能体'),
            });
        }
        const k3 = moonshotEndpoint();
        if (k3 && !model) {    // 语音快模型调用跳过 K3 (思考模式时延高)
            tiers.push({
                name: `kimi-k3(${k3.model})`,
                run: () => openaiCompatChat(messages, { maxTokens, temperature, endpoint: k3 }),
            });
        }
        tiers.push({
            name: 'SiliconFlow',
            run: () => openaiCompatChat(messages, { maxTokens, temperature, endpoint: siliconflowEndpoint(model) }),
        });

        // ── 逐级尝试, 失败降级 ──
        let lastErr = null;
        for (let i = 0; i < tiers.length; i++) {
            const isLast = i === tiers.length - 1;
            try {
                return await tiers[i].run();
            } catch (err) {
                lastErr = err;
                if (!fallbackEnabled() || isLast) throw err;
                console.warn(`[llm] ${tiers[i].name} 不可用, 降级 ${tiers[i + 1].name}: ${String(err.message).split('\n')[0]}`);
            }
        }
        throw lastErr;   // 理论到不了, 防御
    })();

    if (!timeoutMs) return call;            // timeoutMs=0: 不限时 (长报告生成)
    return Promise.race([
        call,                               // 出错时 race 会 reject, 由调用方 catch
        new Promise(resolve => setTimeout(() => resolve(fallback), timeoutMs)),
    ]);
}

module.exports = { chat, provider };
