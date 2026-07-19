#!/usr/bin/env node
/**
 * 导出 5 个专科护理智能体的提示词 — 用于在涂鸦「AI 智能体开发平台」建智能体时直接复制粘贴
 *
 * 用法: node scripts/export_agent_prompts.js          # 全部
 *       node scripts/export_agent_prompts.js diabetes # 只看一个
 */
const path = require('path');
const Database = require('better-sqlite3');

const db = new Database(path.join(__dirname, '..', 'db', 'nursing.db'), { readonly: true });
const filter = process.argv[2];

const rows = filter
    ? db.prepare('SELECT * FROM agent_configs WHERE agent_name = ?').all(filter)
    : db.prepare('SELECT * FROM agent_configs').all();

if (!rows.length) {
    console.error(`未找到智能体${filter ? ` "${filter}"` : ''} (可选: quadriplegia/diabetes/post_stroke/copd/general)`);
    process.exit(1);
}

for (const a of rows) {
    console.log('═'.repeat(60));
    console.log(`【${a.display_name}】 ${a.icon || ''}`);
    console.log(`  业务标识 agentKey : ${a.agent_name}`);
    console.log(`  对应 .env 变量    : TUYA_AGENT_ID_${a.agent_name.toUpperCase()}`);
    console.log(`  适用疾病          : ${a.disease_type}`);
    console.log('─'.repeat(60));
    console.log('▼ 系统提示词 (建智能体时粘贴到「提示词/人设」):');
    console.log(a.system_prompt.trim());
    console.log();
}
console.log('═'.repeat(60));
console.log('平台入口: platform.tuya.com → 开发者工作台 → AI 智能体开发 → 创建智能体');
console.log('建好后把每个智能体的 agent_id 填入 .env 对应变量, 再设 LLM_PROVIDER=tuya');
