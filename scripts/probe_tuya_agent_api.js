#!/usr/bin/env node
/**
 * 涂鸦智能体平台配置一键体检 — 迁移到哪一步、卡在哪、下一步做什么, 跑一次全知道
 *
 * 用法: node scripts/probe_tuya_agent_api.js ["测试问题"]
 *
 * 检查项:
 *   [1] 云项目授权密钥 (TUYA_ACCESS_ID/SECRET) → 能否换到 access_token
 *   [2] 5 个专科智能体 ID 配置情况 (TUYA_AGENT_ID_*)
 *   [3] 智能体对话接口探测 (候选路径逐个试, 探通输出应固化的 TUYA_AGENT_CHAT_PATH)
 *   [4] SiliconFlow 兜底链路 (涂鸦没就绪时演示靠它)
 *
 * 背景: 官方《智能体开放接口》文档未公开端点路径 ("开放能力持续完善中"),
 *       真实路径需在 platform.tuya.com → 云开发 → API Explorer 订阅智能体服务后查看。
 *       本脚本先按命名惯例探测常见形态; 全部失败就按输出指引去 API Explorer 抄真实路径。
 */
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const tuya = require('../services/tuya_openapi');

const QUESTION = process.argv.slice(2).join(' ') || '请用一句话介绍你自己。';
const AGENT_VARS = [
    ['TUYA_AGENT_ID', '默认智能体 (兜底)'],
    ['TUYA_AGENT_ID_QUADRIPLEGIA', '瘫痪护理'],
    ['TUYA_AGENT_ID_DIABETES', '糖尿病护理'],
    ['TUYA_AGENT_ID_POST_STROKE', '脑卒中康复'],
    ['TUYA_AGENT_ID_COPD', '呼吸慢病'],
    ['TUYA_AGENT_ID_GENERAL', '综合护理'],
];
// 与 services/llm.js 保持一致
const CANDIDATE_PATHS = [
    '/v2.0/cloud/agent/{agent_id}/chat',
    '/v1.0/cloud/agent/{agent_id}/chat',
    '/v2.0/ai/agents/{agent_id}/chat',
    '/v1.0/ai/agents/{agent_id}/chat',
    '/v2.0/cloud/ai-agent/{agent_id}/chat',
    '/v1.0/cloud/ai-agent/{agent_id}/chat',
];

const ok = s => console.log(`  ✅ ${s}`);
const bad = s => console.log(`  ❌ ${s}`);
const info = s => console.log(`  ・ ${s}`);

(async () => {
    console.log('══════════ 涂鸦智能体迁移体检 ══════════\n');
    let tuyaReady = false;

    // ── [1] 云项目密钥 ──
    console.log('[1] 云项目授权密钥 (platform.tuya.com → 云开发 → 项目 → 授权密钥)');
    if (!process.env.TUYA_ACCESS_ID || !process.env.TUYA_ACCESS_SECRET) {
        bad('TUYA_ACCESS_ID / TUYA_ACCESS_SECRET 未配置');
    } else {
        try {
            await tuya.getToken();
            ok(`密钥有效, access_token 获取成功 (${process.env.TUYA_OPENAPI_BASE || 'https://openapi.tuyacn.com'})`);
        } catch (e) {
            bad(`获取 token 失败: ${e.message}`);
            info('排查: ①Access ID/Secret 是否抄错 ②数据中心是否中国区 ③云项目是否开通「IoT 核心」服务');
        }
    }

    // ── [2] 智能体 ID ──
    console.log('\n[2] 智能体 ID (platform.tuya.com → 开发者工作台 → AI 智能体开发)');
    const configured = [];
    for (const [envVar, label] of AGENT_VARS) {
        const v = process.env[envVar];
        if (v) { ok(`${label.padEnd(12)} ${envVar} = ${v}`); configured.push(v); }
        else bad(`${label.padEnd(12)} ${envVar} 未配置`);
    }
    if (!configured.length) {
        info('提示词一键导出: node scripts/export_agent_prompts.js (建智能体时逐个粘贴)');
    }

    // ── [3] 对话接口探测 ──
    console.log('\n[3] 智能体对话接口探测');
    if (!configured.length) {
        info('跳过 (没有可测的智能体 ID)');
    } else {
        const agentId = configured[0];
        const pinned = process.env.TUYA_AGENT_CHAT_PATH;
        const paths = pinned ? [pinned] : CANDIDATE_PATHS;
        if (pinned) info(`已锁定 TUYA_AGENT_CHAT_PATH=${pinned}, 只测它`);
        for (const p of paths) {
            const path = p.replace('{agent_id}', agentId);
            process.stdout.write(`  → POST ${path}  `);
            try {
                const resp = await tuya.request('POST', path, { agent_id: agentId, query: QUESTION, stream: false });
                if (resp.success) {
                    console.log('✅ 通!');
                    console.log(`\n  🎉 涂鸦智能体链路打通! 回答预览:\n     ${JSON.stringify(resp.result).slice(0, 300)}`);
                    if (!pinned) console.log(`\n  📌 固化到 .env (免每次探测):\n     TUYA_AGENT_CHAT_PATH=${p}`);
                    tuyaReady = true;
                    break;
                }
                console.log(`code=${resp.code} ${resp.msg}`);
            } catch (e) { console.log(`异常: ${e.message}`); }
        }
        if (!tuyaReady) {
            info('全部候选路径未通。去 platform.tuya.com → 云开发 → 项目 → 服务 API:');
            info('  ① 订阅名称含「智能体/AI Agent」的开放服务 (code=1106 多半是没订阅)');
            info('  ② API Explorer → 智能体 → 对话接口, 把真实路径抄到 .env 的 TUYA_AGENT_CHAT_PATH');
            info('  ③ 若 Explorer 里也没有智能体接口 = 开放能力未对你的账号放开, 找赛事群/涂鸦支持开通');
        }
    }

    // ── [4] SiliconFlow 兜底 ──
    console.log('\n[4] SiliconFlow 兜底链路 (LLM_PROVIDER=tuya 失败时自动降级到它)');
    info(`KIMI_BASE_URL = ${process.env.KIMI_BASE_URL}`);
    info(`KIMI_MODEL    = ${process.env.KIMI_MODEL}`);
    try {
        const saved = process.env.LLM_PROVIDER;
        process.env.LLM_PROVIDER = 'openai';                    // 强制直测 openai 端点
        const { chat } = require('../services/llm');
        const t0 = Date.now();
        const a = await chat([{ role: 'user', content: '回复"OK"两个字母即可' }], { timeoutMs: 30000, maxTokens: 10 });
        process.env.LLM_PROVIDER = saved;
        if (a) ok(`兜底可用 (${Date.now() - t0}ms): ${String(a).trim().slice(0, 50)}`);
        else bad('兜底超时 (30s)');
    } catch (e) {
        bad(`兜底失败: ${e.message}`);
        info('检查 KIMI_API_KEY 是否 SiliconFlow 的 key、KIMI_MODEL 在 cloud.siliconflow.cn 模型广场是否存在');
    }

    // ── 总结 ──
    console.log('\n══════════ 结论 ══════════');
    if (tuyaReady) {
        console.log('✅ 涂鸦智能体已打通 — .env 设 LLM_PROVIDER=tuya 即真实走涂鸦, 演示可讲「智能体已迁移至涂鸦平台」');
    } else {
        console.log('🟡 涂鸦侧未就绪 — LLM_PROVIDER=tuya 也不影响演示 (自动降级 SiliconFlow), 按 [2][3] 的指引补平台配置');
    }
    console.log('   改完 .env 后: 本机直接重跑本脚本; ECS 上 pm2 restart nursing-bed --update-env');
})();
