# -*- coding: utf-8 -*-
"""
图二-2 多智能体协同会诊框架 — 仿 framework(1).pdf 的 case-study 版式:
真实输入 (患者体征+压力矩阵) → Tier1 分诊路由 → Tier2 并行专科会诊 (真实JSON输出)
→ Tier3 冲突消解 → 最终干预裁决 + 闭环复评回路
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, Polygon, FancyBboxPatch

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
INK = '#1a1a1a'

fig, ax = plt.subplots(figsize=(14.2, 8.0))
ax.set_xlim(0, 14.2); ax.set_ylim(0, 8.0); ax.axis('off')

def tier_box(x, y, w, h, title, fc, ec, title_fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.08',
                                fc=fc, ec=ec, lw=1.4, zorder=1))
    ax.add_patch(FancyBboxPatch((x + 0.12, y + h - 0.42), w - 0.24, 0.34,
                                boxstyle='round,pad=0.01,rounding_size=0.05',
                                fc=title_fc, ec='none', zorder=2))
    ax.text(x + w/2, y + h - 0.25, title, ha='center', va='center',
            fontsize=8.6, weight='bold', color=INK, zorder=3)

def stage_box(x, y, w, h, title, lines, fs=5.9, title_fs=6.8, ls='--', fc='white'):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec='#555555', lw=0.9, ls=ls, zorder=2))
    ax.text(x + w/2, y + h - 0.20, title, ha='center', va='center',
            fontsize=title_fs, weight='bold', color=INK, zorder=3)
    ty = y + h - 0.44
    for ln, c in lines:
        ax.text(x + 0.10, ty, ln, ha='left', va='top', fontsize=fs, color=c,
                zorder=3, linespacing=1.3)
        ty -= 0.26 * (ln.count('\n') + 1) + 0.02
    return ty

def arr(p1, p2, lw=2.2, color=INK, ls='-', ms=13, z=6):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='-|>', mutation_scale=ms,
                                 color=color, lw=lw, ls=ls, shrinkA=1, shrinkB=1, zorder=z))

# ═════════ 输入 (左上, 米黄) ═════════
tier_box(0.15, 4.55, 3.45, 3.30, '输入：患者实时数据', '#fdf3d0', '#8a6d1a', '#f4df96')
ax.text(0.35, 7.18, '张建国 · 62岁 · 高位截瘫 (C4-C5)\n101房 A-101床 · 责任Agent: quadriplegia',
        fontsize=6.2, va='top', linespacing=1.45)
# 8×8 压力矩阵 inset
grid = np.array([
    [0,0,8,14,14,8,0,0],[0,6,12,16,16,12,6,0],[9,18,22,14,14,22,18,9],
    [4,10,16,12,12,16,10,4],[2,6,9,8,8,9,6,2],[6,14,26,29,29,26,14,6],
    [3,9,12,9,9,12,9,3],[0,2,10,18,18,10,2,0]]) * 100
# 直接画在主坐标系, extent 定位到输入框内 (x 0.38..1.68, y 5.28..6.58)
GX1, GX2, GY1, GY2 = 0.38, 1.68, 5.28, 6.58
ax.imshow(grid, cmap='turbo', vmin=0, vmax=4095, extent=[GX1, GX2, GY1, GY2],
          aspect='auto', zorder=3, interpolation='nearest')
ax.add_patch(Rectangle((GX1, GY1), GX2-GX1, GY2-GY1, fc='none', ec='#666', lw=0.9, zorder=4))
ax.text((GX1+GX2)/2, GY2 + 0.12, '8×8 压力矩阵', fontsize=5.6, ha='center', zorder=4)
# 骶尾高压格标注 (row5 cols3-4 → y 从上往下第6行)
cw, ch = (GX2-GX1)/8, (GY2-GY1)/8
hx, hy = GX1 + 3*cw, GY2 - 6*ch
ax.add_patch(Rectangle((hx, hy), 2*cw, ch, fc='none', ec='white', lw=1.2, ls='--', zorder=5))
ax.annotate('骶尾 2868', xy=(hx + cw, hy + ch/2), xytext=(GX1 + 0.1, GY1 - 0.26),
            fontsize=5.6, color='#c0392b', weight='bold', zorder=6,
            arrowprops=dict(arrowstyle='->', color='#c0392b', lw=0.9))
ax.text(2.72, 6.90, '实时体征', fontsize=6.4, weight='bold')
for i, (t, c) in enumerate([('SpO2  88% ↓', '#c0392b'), ('RR  22次/分 ↑', '#c0392b'),
                            ('HR  96 bpm', '#444'), ('骶尾受压 47min ↑', '#c0392b'),
                            ('体温 36.5°C', '#444')]):
    ax.text(2.72, 6.62 - i * 0.27, t, fontsize=5.9, color=c, weight='bold' if '↓' in t or '↑' in t else 'normal')
ax.text(0.35, 4.70, '触发: L0规则扫描命中 2 项异常 → 上报 Coordinator',
        fontsize=5.8, color='#8a6d1a', style='italic')

# ═════════ Tier 1: 分诊路由 (右上, 蓝) ═════════
tier_box(3.95, 5.35, 10.05, 2.50, 'Tier 1：NursingCoordinator 分诊路由', '#e7f1f8', '#31708f', '#bcd8ea')
stage_box(4.15, 5.50, 3.05, 1.90, 'Stage 1: 特征提取', [
    ('规则阈值扫描 (9条硬编码):', '#333'),
    ('SpO2 88 < 94  √命中', '#c0392b'),
    ('受压 47min > 45min √命中', '#c0392b'),
    ('HR/体温/血糖 正常 ×', '#7a7a7a')])
stage_box(7.40, 5.50, 3.15, 1.90, 'Stage 2: 分诊广播', [
    ('AgentMailbox 异步消息总线', '#333'),
    ('→ 急救分诊  (pri 0) 激活', '#1e6641'),
    ('→ 体征监护  (pri 2) 激活', '#1e6641'),
    ('→ 褥疮预防  (pri 3) 激活', '#1e6641'),
    ('→ 情绪陪伴  (pri 7) 不激活', '#9a9a9a')])
stage_box(10.75, 5.50, 3.05, 1.90, 'Stage 3: 上下文组装', [
    ('PatientMemory 跨会话记忆:', '#333'),
    ('· 病史: C4-C5脊髓损伤', '#555'),
    ('· 上次翻身: 47min前 (左→仰)', '#555'),
    ('· 历史干预有效率 92%', '#555'),
    ('→ 结构化 Prompt + 体征快照', '#31708f')])

# ═════════ Tier 2: 并行专科会诊 (右下, 绿) ═════════
tier_box(8.05, 0.75, 6.00, 4.20, 'Tier 2：专科 Agent 并行会诊', '#e8f5ec', '#2d6a4f', '#c3e6cf')
agents = [
    (8.25, 2.78, '[急救] 急救分诊 Agent', [
        ('action: "escalate_check"', '#333'),
        ('urgency: medium · conf: 0.82', '#8a6d1a'),
        ('"SpO2 88 未达急救线(85),', '#555'),
        (' 密切监测, 暂不抢救"', '#555')]),
    (11.20, 2.78, '[体征] 体征监护 Agent', [
        ('action: "posture_semi_fowler"', '#333'),
        ('urgency: high · conf: 0.91', '#c0392b'),
        ('"低氧+呼吸加快, 建议半卧位', '#555'),
        (' 抬高床头改善通气"', '#555')]),
    (8.25, 0.92, '[褥疮] 褥疮预防 Agent', [
        ('action: "turn_left_30"', '#333'),
        ('urgency: high · conf: 0.88', '#c0392b'),
        ('"骶尾 2868 超阈值+47min,', '#555'),
        (' 需立即左侧卧减压"', '#555')]),
    (11.20, 0.92, '[陪伴] 情绪陪伴 Agent', [
        ('(本轮未激活)', '#9a9a9a')]),
]
for x, y, name, lines in agents:
    fc = '#f7f7f7' if '未激活' in lines[0][0] else 'white'
    ax.add_patch(Rectangle((x, y), 2.72, 1.72, fc=fc, ec='#2d6a4f', lw=0.9, zorder=2))
    ax.text(x + 1.36, y + 1.50, name, ha='center', fontsize=6.6, weight='bold', zorder=3)
    ty = y + 1.22
    for ln, c in lines:
        ax.text(x + 0.10, ty, ln, fontsize=5.5, color=c, va='top', zorder=3)
        ty -= 0.28
ax.text(11.05, 0.50, 'JSON 结构化输出: {action, params, reasoning, confidence, urgency}',
        ha='center', fontsize=5.6, color='#2d6a4f', style='italic')

# ═════════ Tier 3: 冲突消解 (中下, 紫) ═════════
tier_box(4.10, 0.75, 3.65, 4.20, 'Tier 3：冲突消解与聚合', '#efe8f5', '#6b4b8a', '#dccbec')
stage_box(4.28, 3.18, 3.28, 1.30, '冲突检测', [
    ('半卧位(通气)  vs  左侧卧(减压)', '#c0392b'),
    ('urgency×confidence 加权仲裁', '#333'),
    ('→ 左侧卧30° + 床头抬高15°', '#1e6641')], ls='--')
stage_box(4.28, 2.02, 3.28, 1.04, '参数沙箱校验', [
    ('PARAM_BOUNDS: 倾角≤30° √', '#333'),
    ('ToolPermissionChecker 权限 √', '#333')], ls='--')
# 决策菱形
dx, dy = 5.92, 1.35
ax.add_patch(Polygon([(dx-0.85,dy),(dx,dy+0.42),(dx+0.85,dy),(dx,dy-0.42)],
                     fc='#dccbec', ec='#6b4b8a', lw=1.1, zorder=3))
ax.text(dx, dy, 'critical级?', ha='center', va='center', fontsize=6.2, weight='bold', zorder=4)
ax.text(dx, 0.86, '否 → 自动执行', ha='center', fontsize=5.6, color='#1e6641', zorder=4)
ax.add_patch(Rectangle((6.90, 1.02), 0.80, 0.62, fc='white', ec='#6b4b8a', lw=0.9, ls='--', zorder=3))
ax.text(7.30, 1.42, '是→L3', ha='center', fontsize=5.4, color='#6b4b8a', zorder=4)
ax.text(7.30, 1.20, '人工审核', ha='center', fontsize=5.4, color='#6b4b8a', zorder=4)
arr((dx+0.85, dy), (6.90, 1.33), lw=1.0, ms=8)

# ═════════ 最终干预 (左下, 粉) ═════════
tier_box(0.15, 0.75, 3.60, 3.45, '最终干预裁决', '#fdeaea', '#a94442', '#f5c6c6')
ax.add_patch(FancyBboxPatch((0.90, 3.28), 2.0, 0.42, boxstyle='round,pad=0.02,rounding_size=0.08',
                            fc='#2d6a4f', ec='none', zorder=3))
ax.text(1.90, 3.49, '执行：左侧卧30°减压', ha='center', va='center', color='white',
        fontsize=7.0, weight='bold', zorder=4)
for i, (t, c) in enumerate([
        ('动作序列:', '#333'),
        (' ① 气囊交替充放 → 左倾30°', '#555'),
        (' ② 推杆抬高床头 15°', '#555'),
        (' ③ L2黄色预警 → 护士站+家属App', '#555'),
        ('证据链:', '#333'),
        (' 骶尾2868·47min | SpO2 88 | conf 0.91/0.88', '#777'),
        ('闭环反馈: 5min后复评 SpO2 93% ↑', '#1e6641')]):
    ax.text(0.35, 2.98 - i * 0.30, t, fontsize=5.9, color=c,
            weight='bold' if t.endswith(':') or '↑' in t else 'normal')

# ═════════ 主流程箭头 ═════════
arr((3.60, 6.20), (3.95, 6.55))                       # 输入 → Tier1
arr((12.30, 5.35), (12.30, 4.95))                     # Tier1 → Tier2
arr((8.05, 2.85), (7.75, 2.85))                       # Tier2 → Tier3
arr((4.10, 2.40), (3.75, 2.40))                       # Tier3 → 最终
# 重询回路: Tier3 顶 → 层间走廊 → Tier2 顶
ax.plot([6.80, 6.80, 8.80], [4.95, 5.10, 5.10], ls='--', color='#6b4b8a', lw=1.0, zorder=5)
arr((8.80, 5.10), (8.80, 4.97), lw=1.0, ls='--', color='#6b4b8a', ms=8)
ax.text(7.80, 5.23, '低一致性重询 (max 2轮)', fontsize=5.2, color='#6b4b8a', ha='center')
arr((1.95, 4.20), (1.95, 4.55), lw=1.6, ls='--', color='#2d6a4f', ms=11)  # 闭环
ax.text(2.62, 4.36, '闭环复评', fontsize=5.8, color='#2d6a4f', weight='bold')

fig.savefig('D:/IOT/figures/fig2_2_swarm_case.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close(fig)
print('生成: fig2_2_swarm_case.png')
