#!/usr/bin/env node
/**
 * 统一 LLM 网关自测 — 验证当前 .env 的 LLM 配置是否可用
 *
 * 用法: node scripts/test_llm_gateway.js [问题]
 *
 * LLM_PROVIDER=openai → 测 KIMI_BASE_URL/KIMI_API_KEY/KIMI_MODEL (百炼/Moonshot/任意兼容端点)
 * LLM_PROVIDER=tuya   → 测 TUYA_ACCESS_ID/SECRET + TUYA_AGENT_ID (涂鸦智能体开放服务)
 */
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const { chat, provider } = require('../services/llm');

const question = process.argv.slice(2).join(' ') || '用一句话介绍你自己。';

(async () => {
    console.log(`[网关自测] provider = ${provider()}`);
    if (provider() === 'tuya') {
        console.log(`  TUYA_ACCESS_ID   = ${process.env.TUYA_ACCESS_ID ? '已配置' : '❌ 缺失'}`);
        console.log(`  TUYA_AGENT_ID    = ${process.env.TUYA_AGENT_ID || '❌ 缺失'}`);
    } else {
        console.log(`  KIMI_BASE_URL    = ${process.env.KIMI_BASE_URL}`);
        console.log(`  KIMI_MODEL       = ${process.env.KIMI_MODEL}`);
    }
    console.log(`  问题: ${question}\n`);

    const t0 = Date.now();
    try {
        const answer = await chat(
            [{ role: 'system', content: '你是智能护理病床的AI助手。' },
             { role: 'user', content: question }],
            { timeoutMs: 60000, maxTokens: 200 }
        );
        if (answer === null) {
            console.log(`❌ 超时 (60s 无响应)`);
            process.exit(1);
        }
        console.log(`✅ 成功 (${Date.now() - t0}ms):\n${answer}`);
    } catch (err) {
        console.log(`❌ 失败 (${Date.now() - t0}ms): ${err.message}`);
        if (/Arrearage|overdue/.test(err.message)) {
            console.log('   → 阿里云百炼账户欠费。去 dashscope 控制台充值, 或切换 LLM_PROVIDER=tuya 用竞赛赠送的涂鸦额度');
        }
        process.exit(1);
    }
})();
