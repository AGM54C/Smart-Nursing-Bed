# -*- coding: utf-8 -*-
"""
图二-2 多智能体协同会诊框架 — 仿 framework(1).pdf 的 case-study 版式 (v2: 大字号可读版)
真实输入 → Tier1 分诊路由 → Tier2 并行专科会诊 → Tier3 冲突消解 → 最终干预 + 闭环
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, FancyBboxPatch

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
INK = '#1a1a1a'

fig, ax = plt.subplots(figsize=(12.0, 6.76))
ax.set_xlim(0, 14.2); ax.set_ylim(0, 8.0); ax.axis('off')

def tier_box(x, y, w, h, title, fc, ec, title_fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.08',
                                fc=fc, ec=ec, lw=1.4, zorder=1))
    ax.add_patch(FancyBboxPatch((x + 0.12, y + h - 0.46), w - 0.24, 0.38,
                                boxstyle='round,pad=0.01,rounding_size=0.05',
                                fc=title_fc, ec='none', zorder=2))
    ax.text(x + w/2, y + h - 0.27, title, ha='center', va='center',
            fontsize=10.2, weight='bold', color=INK, zorder=3)

def stage_box(x, y, w, h, title, lines, fs=7.2, title_fs=8.2):
    ax.add_patch(Rectangle((x, y), w, h, fc='white', ec='#555555', lw=0.9, ls='--', zorder=2))
    ax.text(x + w/2, y + h - 0.24, title, ha='center', va='center',
            fontsize=title_fs, weight='bold', color=INK, zorder=3)
    ty = y + h - 0.52
    for ln, c in lines:
        ax.text(x + 0.12, ty, ln, ha='left', va='top', fontsize=fs, color=c, zorder=3)
        ty -= 0.38

def arr(p1, p2, lw=2.2, color=INK, ls='-', ms=13, z=6):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='-|>', mutation_scale=ms,
                                 color=color, lw=lw, ls=ls, shrinkA=1.5, shrinkB=3, zorder=z))

# ═════════ 输入 (左上, 米黄) ═════════
tier_box(0.15, 4.55, 3.45, 3.30, '输入：患者实时数据', '#fdf3d0', '#8a6d1a', '#f4df96')
ax.text(0.32, 7.18, '张建国 · 62岁 · 高位截瘫\nA-101床 · quadriplegia',
        fontsize=7.4, va='top', linespacing=1.5)
grid = np.array([
    [0,0,8,14,14,8,0,0],[0,6,12,16,16,12,6,0],[9,18,22,14,14,22,18,9],
    [4,10,16,12,12,16,10,4],[2,6,9,8,8,9,6,2],[6,14,26,29,29,26,14,6],
    [3,9,12,9,9,12,9,3],[0,2,10,18,18,10,2,0]]) * 100
GX1, GX2, GY1, GY2 = 0.35, 1.62, 5.20, 6.47
ax.imshow(grid, cmap='turbo', vmin=0, vmax=4095, extent=[GX1, GX2, GY1, GY2],
          aspect='auto', zorder=3, interpolation='nearest')
ax.add_patch(Rectangle((GX1, GY1), GX2-GX1, GY2-GY1, fc='none', ec='#666', lw=0.9, zorder=4))
ax.text((GX1+GX2)/2, GY2 + 0.13, '8×8 压力矩阵', fontsize=6.8, ha='center', zorder=4)
cw, ch = (GX2-GX1)/8, (GY2-GY1)/8
hx, hy = GX1 + 3*cw, GY2 - 6*ch
ax.add_patch(Rectangle((hx, hy), 2*cw, ch, fc='none', ec='white', lw=1.2, ls='--', zorder=5))
ax.annotate('骶尾 2868', xy=(hx + cw, hy + ch/2), xytext=(GX1 + 0.06, GY1 - 0.34),
            fontsize=6.8, color='#c0392b', weight='bold', zorder=6,
            arrowprops=dict(arrowstyle='->', color='#c0392b', lw=0.9))
ax.text(2.55, 6.72, '实时体征', fontsize=7.6, weight='bold')
for i, (t, c) in enumerate([('SpO2 88% ↓', '#c0392b'), ('RR 22次 ↑', '#c0392b'),
                            ('HR 96 bpm', '#444'), ('受压 47min ↑', '#c0392b'),
                            ('体温 36.5°C', '#444')]):
    ax.text(2.55, 6.38 - i * 0.34, t, fontsize=7.2, color=c,
            weight='bold' if '↓' in t or '↑' in t else 'normal')
ax.text(0.32, 4.70, '触发: 2项异常 → 上报 Coordinator', fontsize=6.8,
        color='#8a6d1a', style='italic')

# ═════════ Tier 1: 分诊路由 (右上, 蓝) ═════════
tier_box(3.95, 5.35, 10.05, 2.50, 'Tier 1：NursingCoordinator 分诊路由', '#e7f1f8', '#31708f', '#bcd8ea')
stage_box(4.15, 5.50, 3.05, 2.00, 'Stage 1: 特征提取', [
    ('L0 规则扫描 (9条):', '#333'),
    ('SpO2 88 < 94  √命中', '#c0392b'),
    ('受压 47 > 45min √命中', '#c0392b'),
    ('其余指标正常 ×', '#7a7a7a')])
stage_box(7.40, 5.50, 3.15, 2.00, 'Stage 2: 分诊广播', [
    ('AgentMailbox 广播:', '#333'),
    ('急救·体征·褥疮 激活', '#1e6641'),
    ('情绪陪伴 不激活', '#9a9a9a'),
    ('(优先级 0/2/3/7)', '#7a7a7a')])
stage_box(10.75, 5.50, 3.05, 2.00, 'Stage 3: 上下文组装', [
    ('PatientMemory 记忆:', '#333'),
    ('病史 C4-C5脊髓损伤', '#555'),
    ('上次翻身 47min前', '#555'),
    ('→ 结构化 Prompt', '#31708f')])

# ═════════ Tier 2: 并行专科会诊 (右下, 绿) ═════════
tier_box(8.05, 0.75, 6.00, 4.20, 'Tier 2：专科 Agent 并行会诊', '#e8f5ec', '#2d6a4f', '#c3e6cf')
agents = [
    (8.22, 2.72, '急救分诊 Agent', [
        ('action: escalate_check', '#333'),
        ('urgency: med · conf 0.82', '#8a6d1a'),
        ('"未达急救线85, 监测"', '#555')]),
    (11.12, 2.72, '体征监护 Agent', [
        ('action: semi_fowler', '#333'),
        ('urgency: high · conf 0.91', '#c0392b'),
        ('"低氧, 半卧位通气"', '#555')]),
    (8.22, 0.92, '褥疮预防 Agent', [
        ('action: turn_left_30', '#333'),
        ('urgency: high · conf 0.88', '#c0392b'),
        ('"骶尾超压, 需减压"', '#555')]),
    (11.12, 0.92, '情绪陪伴 Agent', [
        ('(本轮未激活)', '#9a9a9a')]),
]
for x, y, name, lines in agents:
    fc = '#f7f7f7' if '未激活' in lines[0][0] else 'white'
    ax.add_patch(Rectangle((x, y), 2.80, 1.68, fc=fc, ec='#2d6a4f', lw=0.9, zorder=2))
    ax.text(x + 1.40, y + 1.42, name, ha='center', fontsize=8.0, weight='bold', zorder=3)
    ty = y + 1.12
    for ln, c in lines:
        ax.text(x + 0.12, ty, ln, fontsize=6.8, color=c, va='top', zorder=3)
        ty -= 0.36
ax.text(11.05, 0.46, 'JSON输出: {action, reasoning, confidence, urgency}',
        ha='center', fontsize=6.8, color='#2d6a4f', style='italic')

# ═════════ Tier 3: 冲突消解 (中下, 紫) ═════════
tier_box(4.10, 0.75, 3.65, 4.20, 'Tier 3：冲突消解与聚合', '#efe8f5', '#6b4b8a', '#dccbec')
stage_box(4.28, 2.72, 3.28, 1.62, '冲突检测与仲裁', [
    ('半卧位 vs 左侧卧 冲突', '#c0392b'),
    ('urgency×conf 加权', '#333'),
    ('→ 左侧卧30°+床头15°', '#1e6641')])
stage_box(4.28, 0.95, 3.28, 1.62, '安全门控', [
    ('参数沙箱 倾角≤30° √', '#333'),
    ('critical → L3人工审核', '#6b4b8a'),
    ('其余 → 自动执行', '#1e6641')])

# ═════════ 最终干预 (左下, 粉) ═════════
tier_box(0.15, 0.75, 3.60, 3.45, '最终干预裁决', '#fdeaea', '#a94442', '#f5c6c6')
ax.add_patch(FancyBboxPatch((0.55, 3.10), 2.75, 0.48, boxstyle='round,pad=0.02,rounding_size=0.08',
                            fc='#2d6a4f', ec='none', zorder=3))
ax.text(1.93, 3.34, '执行：左侧卧30°减压', ha='center', va='center', color='white',
        fontsize=8.4, weight='bold', zorder=4)
for i, (t, c) in enumerate([
        ('动作: 气囊左倾30°+床头15°', '#333'),
        ('告警: L2黄色 → 护士站', '#333'),
        ('证据: 骶尾2868 · SpO2 88', '#777'),
        ('复评: 5min后 SpO2 93% ↑', '#1e6641')]):
    ax.text(0.35, 2.72 - i * 0.44, t, fontsize=7.2, color=c,
            weight='bold' if '↑' in t else 'normal')

# ═════════ 主流程箭头 ═════════
arr((3.62, 6.20), (3.93, 6.55))                       # 输入 → Tier1
arr((12.30, 5.33), (12.30, 4.97))                     # Tier1 → Tier2
arr((8.03, 2.85), (7.77, 2.85))                       # Tier2 → Tier3
arr((4.08, 2.40), (3.77, 2.40))                       # Tier3 → 最终
# 重询回路: Tier3 顶 → 层间走廊 → Tier2 顶
ax.plot([6.80, 6.80, 8.80], [4.97, 5.13, 5.13], ls='--', color='#6b4b8a', lw=1.1, zorder=5)
arr((8.80, 5.13), (8.80, 4.99), lw=1.1, ls='--', color='#6b4b8a', ms=9)
ax.text(7.80, 5.26, '低一致性重询 (max 2轮)', fontsize=6.6, color='#6b4b8a', ha='center')
# 闭环复评
arr((1.93, 4.22), (1.93, 4.53), lw=1.6, ls='--', color='#2d6a4f', ms=11)
ax.text(2.68, 4.37, '闭环复评', fontsize=7.0, color='#2d6a4f', weight='bold')

fig.savefig('D:/IOT/figures/fig2_2_swarm_case.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close(fig)
print('生成: fig2_2_swarm_case.png')
