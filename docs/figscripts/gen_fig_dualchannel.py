# -*- coding: utf-8 -*-
"""
图二-4 大模型与规则引擎双通道决策架构 — 仿 Hyperion (arXiv 2512.21730) Fig.6 系统总览:
边缘/云端双虚线容器 + 编号数据流 + 快/慢双通道时延标注 + 决策融合器 + 降级回路
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, FancyBboxPatch, Circle, Polygon

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
INK = '#1a1a1a'
FAST = '#c0392b'   # 快通道 (规则)
SLOW = '#2e6da4'   # 慢通道 (LLM)

fig, ax = plt.subplots(figsize=(13.2, 5.9))
ax.set_xlim(0, 13.2); ax.set_ylim(0, 5.9); ax.axis('off')

def comp(x, y, w, h, title, sub, fc, ec, tfs=7.2, sfs=5.7):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.07',
                                fc=fc, ec=ec, lw=1.1, zorder=3))
    cy = y + h - 0.26 if sub else y + h/2
    ax.text(x + w/2, cy, title, ha='center', va='center', fontsize=tfs, weight='bold',
            color=INK, zorder=4)
    if sub:
        ax.text(x + w/2, y + (h - 0.42)/2, sub, ha='center', va='center', fontsize=sfs,
                color='#3a3a3a', zorder=4, linespacing=1.45)

def num(x, y, n, color=INK):
    ax.add_patch(Circle((x, y), 0.148, fc=color, ec='none', zorder=7))
    ax.text(x, y - 0.005, str(n), ha='center', va='center', fontsize=6.4,
            color='white', weight='bold', zorder=8)

def arr(p1, p2, color=INK, lw=1.6, ls='-', ms=11, z=6, connstyle=None):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='-|>', mutation_scale=ms, color=color,
                                 lw=lw, ls=ls, shrinkA=1, shrinkB=1, zorder=z,
                                 connectionstyle=connstyle or 'arc3,rad=0'))

def lat_badge(x, y, txt, color):
    ax.add_patch(FancyBboxPatch((x - 0.52, y - 0.13), 1.04, 0.26,
                                boxstyle='round,pad=0.02,rounding_size=0.10',
                                fc='white', ec=color, lw=1.0, zorder=6))
    ax.text(x, y, txt, ha='center', va='center', fontsize=5.8, color=color,
            weight='bold', zorder=7)

# ═════════ 容器: 边缘端 / 云端 ═════════
ax.add_patch(Rectangle((0.15, 0.45), 8.10, 4.95, fc='#fbfbf9', ec='#666', lw=1.3, ls=(0, (5, 3)), zorder=1))
ax.text(0.42, 5.14, '边缘端 · 树莓派 4B', fontsize=8.6, weight='bold', color=INK, style='italic')
ax.add_patch(Rectangle((8.75, 0.45), 4.30, 4.95, fc='#f7fafd', ec='#666', lw=1.3, ls=(0, (5, 3)), zorder=1))
ax.text(9.02, 5.14, '云端 · LLM 网关', fontsize=8.6, weight='bold', color=INK, style='italic')

# ═════════ ① 输入 ═════════
comp(0.45, 2.45, 1.55, 1.55, '多模态输入', '体征流 1Hz\n8×8压力矩阵\n睡姿分类结果', '#fdf6e3', '#8a6d1a')
num(0.62, 3.85, 1)

# ═════════ ② 规则引擎 (快通道, 上路) ═════════
comp(2.60, 3.45, 2.55, 1.45, '规则引擎 (快通道)', '9条硬编码规则 · 三级阈值\n帧间差分翻身检测\n确定性有界响应', '#fdeaea', FAST)
num(2.77, 4.74, 2)
lat_badge(4.62, 5.06, '<10 ms', FAST)

# ═════════ ③ 复杂度路由 ═════════
dx, dy = 6.45, 2.95
ax.add_patch(Polygon([(dx-0.95, dy), (dx, dy+0.62), (dx+0.95, dy), (dx, dy-0.62)],
                     fc='#efe8f5', ec='#6b4b8a', lw=1.2, zorder=3))
ax.text(dx, dy+0.12, '复杂度路由', ha='center', fontsize=6.6, weight='bold', zorder=4)
ax.text(dx, dy-0.16, '单因素? 多因素?', ha='center', fontsize=5.4, color='#555', zorder=4)
num(5.62, 3.42, 3)

# ═════════ ④ 云端 LLM 深度分析 (慢通道) ═════════
comp(9.05, 3.30, 3.70, 1.45, 'LLM 深度分析 (慢通道)', '多因素关联推理 · 个性化建议\n结构化JSON输出 · 证据链解释', '#e7f1f8', SLOW)
num(9.22, 4.59, 4)
lat_badge(12.20, 5.06, '1~3 s', SLOW)

# ═════════ ⑤ 三级降级链 ═════════
chain = [('涂鸦 AI Agent', '第一级 · 专科智能体'),
         ('Moonshot Kimi K3', '第二级 · 通用大模型'),
         ('SiliconFlow DeepSeek', '第三级 · 保底推理')]
for i, (t, s) in enumerate(chain):
    y = 2.10 - i * 0.62
    ax.add_patch(Rectangle((9.35, y), 3.10, 0.50, fc='white', ec=SLOW, lw=0.9, zorder=3))
    ax.text(9.55, y + 0.25, t, va='center', fontsize=6.0, weight='bold', zorder=4)
    ax.text(12.32, y + 0.25, s, va='center', ha='right', fontsize=5.2, color='#777', zorder=4)
    if i < 2:
        arr((10.90, y), (10.90, y - 0.115), color=SLOW, lw=1.0, ms=8)
ax.text(11.05, 2.86, '降级链 (services/llm.js) · 上级超时8s自动切换', ha='center',
        fontsize=5.8, color=SLOW, weight='bold', zorder=4)
num(9.02, 2.86, 5)

# ═════════ ⑥ 决策融合器 ═════════
comp(2.60, 0.75, 2.55, 1.45, '决策融合器', '规则优先安全兜底\nLLM增强语义解释\n参数沙箱二次校验', '#e8f5ec', '#2d6a4f')
num(2.77, 2.04, 6)

# ═════════ ⑦ 执行器 ═════════
comp(0.45, 0.75, 1.55, 1.45, '执行器', '气囊/推杆动作\n三级告警下发\n报告生成', '#f5f5f5', '#555')
num(0.62, 2.04, 7)

# ═════════ 数据流 ═════════
arr((2.00, 3.60), (2.60, 3.95), color=FAST, lw=2.0)                    # ①→② 快通道
arr((5.15, 4.17), (6.45, 3.57), color=FAST, lw=2.0)                    # ②→③
arr((2.00, 2.85), (5.50, 2.95), color='#555', lw=1.3, ls=(0, (4, 2)))  # ①→③ 原始特征
# ③→④ 多因素上云 (跨容器)
arr((7.40, 2.95), (9.05, 3.85), color=SLOW, lw=2.0, connstyle='arc3,rad=-0.18')
ax.text(8.28, 3.72, '多因素/模糊案例', fontsize=5.6, color=SLOW, ha='center', rotation=18)
# ③→⑥ 简单案例直接下行
arr((6.45, 2.33), (5.15, 1.62), color=FAST, lw=2.0)
ax.text(6.10, 1.78, '单因素异常\n直接执行', fontsize=5.4, color=FAST, ha='center')
# ④/⑤→⑥ LLM结果回边缘 (跨容器)
arr((9.05, 3.38), (5.15, 1.28), color=SLOW, lw=2.0, connstyle='arc3,rad=0.12')
ax.text(7.05, 1.30, 'JSON决策+置信度', fontsize=5.6, color=SLOW, ha='center', rotation=12)
# ⑥→⑦
arr((2.60, 1.48), (2.00, 1.48), lw=2.0)
# LLM超时降级回路 (红虚线): ④ 底 → ② 底
arr((9.35, 3.10), (4.40, 3.45), color=FAST, lw=1.2, ls=(0, (4, 2.4)),
    connstyle='arc3,rad=0.28')
ax.text(6.62, 4.35, 'LLM超时/失败 → 规则兜底 (演示不中断)', fontsize=5.6, color=FAST,
        style='italic', ha='center')
# ⑦ 闭环: 执行后体征复评 (执行器顶 → 输入底)
arr((1.22, 2.20), (1.22, 2.45), color='#2d6a4f', lw=1.3, ls=(0, (3, 2)), ms=9)
ax.text(1.94, 2.32, '闭环复评', fontsize=5.4, color='#2d6a4f', ha='center')

# 图例
lx = 10.95
for i, (c, ls, t) in enumerate([(FAST, '-', '快通道 (规则, <10ms)'), (SLOW, '-', '慢通道 (LLM, 1~3s)'),
                                 (FAST, (0, (4, 2.4)), '降级/兜底回路')]):
    y = 0.86 - i * 0.0  # 单行排布
for i, (c, ls, t) in enumerate([(FAST, '-', '快通道·规则 <10ms'), (SLOW, '-', '慢通道·LLM 1~3s'),
                                 (FAST, (0, (4, 2.4)), '超时降级回路')]):
    x0 = 4.35 + i * 2.6
    ax.plot([x0, x0 + 0.40], [0.28, 0.28], color=c, ls=ls, lw=1.6, zorder=5, clip_on=False)
    ax.text(x0 + 0.50, 0.28, t, fontsize=5.8, va='center', color='#333', zorder=5)

fig.savefig('D:/IOT/figures/fig2_4_dualchannel.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close(fig)
print('生成: fig2_4_dualchannel.png')
