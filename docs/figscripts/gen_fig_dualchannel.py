# -*- coding: utf-8 -*-
"""
图二-4 大模型与规则引擎双通道决策架构 — 仿 Hyperion Fig.6 (v2: 大字号可读版)
边缘/云端双容器 + 编号数据流 + 快/慢通道时延 + 融合器; 降级回路走顶部走廊不穿框
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
FAST = '#c0392b'
SLOW = '#2e6da4'

fig, ax = plt.subplots(figsize=(11.6, 5.45))
ax.set_xlim(0, 13.2); ax.set_ylim(0, 6.2); ax.axis('off')

def comp(x, y, w, h, title, sub, fc, ec, tfs=8.8, sfs=7.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.07',
                                fc=fc, ec=ec, lw=1.15, zorder=3))
    ax.text(x + w/2, y + h - 0.28, title, ha='center', va='center', fontsize=tfs,
            weight='bold', color=INK, zorder=4)
    if sub:
        ax.text(x + w/2, y + (h - 0.50)/2, sub, ha='center', va='center', fontsize=sfs,
                color='#3a3a3a', zorder=4, linespacing=1.55)

def num(x, y, n):
    ax.add_patch(Circle((x, y), 0.165, fc=INK, ec='none', zorder=7))
    ax.text(x, y - 0.005, str(n), ha='center', va='center', fontsize=7.4,
            color='white', weight='bold', zorder=8)

def arr(p1, p2, color=INK, lw=1.7, ls='-', ms=12, z=6, cs=None):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='-|>', mutation_scale=ms, color=color,
                                 lw=lw, ls=ls, shrinkA=1.5, shrinkB=3, zorder=z,
                                 connectionstyle=cs or 'arc3,rad=0'))

def lat_badge(x, y, txt, color):
    ax.add_patch(FancyBboxPatch((x - 0.58, y - 0.16), 1.16, 0.32,
                                boxstyle='round,pad=0.02,rounding_size=0.10',
                                fc='white', ec=color, lw=1.1, zorder=6))
    ax.text(x, y, txt, ha='center', va='center', fontsize=7.2, color=color,
            weight='bold', zorder=7)

# ═════════ 容器 ═════════
ax.add_patch(Rectangle((0.15, 0.45), 8.10, 4.95, fc='#fbfbf9', ec='#666', lw=1.3, ls=(0, (5, 3)), zorder=1))
ax.text(0.42, 5.12, '边缘端 · 树莓派 4B', fontsize=9.6, weight='bold', color=INK, style='italic')
ax.add_patch(Rectangle((8.75, 0.45), 4.30, 4.95, fc='#f7fafd', ec='#666', lw=1.3, ls=(0, (5, 3)), zorder=1))
ax.text(9.02, 5.12, '云端 · LLM 网关', fontsize=9.6, weight='bold', color=INK, style='italic')

# ═════════ 组件 ═════════
comp(0.45, 2.45, 1.60, 1.55, '多模态输入', '体征流 1Hz\n8×8 压力矩阵\n睡姿分类', '#fdf6e3', '#8a6d1a')
num(0.62, 3.85, 1)
comp(2.60, 3.42, 2.60, 1.48, '规则引擎 · 快通道', '9条规则 · 三级阈值\n确定性有界响应', '#fdeaea', FAST)
num(2.77, 4.74, 2)
lat_badge(4.55, 5.14, '<10 ms', FAST)
dx, dy = 6.48, 2.92
ax.add_patch(Polygon([(dx-1.00, dy), (dx, dy+0.62), (dx+1.00, dy), (dx, dy-0.62)],
                     fc='#efe8f5', ec='#6b4b8a', lw=1.2, zorder=3))
ax.text(dx, dy+0.10, '复杂度路由', ha='center', fontsize=7.8, weight='bold', zorder=4)
ax.text(dx, dy-0.20, '单/多因素?', ha='center', fontsize=6.6, color='#555', zorder=4)
num(5.60, 3.44, 3)
comp(9.05, 3.42, 3.70, 1.48, 'LLM 深度分析 · 慢通道', '多因素关联 · 个性化建议\n结构化JSON · 证据链', '#e7f1f8', SLOW)
num(9.22, 4.72, 4)
lat_badge(12.15, 5.14, '1~3 s', SLOW)
chain = [('涂鸦 AI Agent', '一级'), ('Moonshot Kimi K3', '二级'), ('SiliconFlow DeepSeek', '保底')]
for i, (t, s) in enumerate(chain):
    y = 2.16 - i * 0.66
    ax.add_patch(Rectangle((9.30, y), 3.20, 0.54, fc='white', ec=SLOW, lw=0.9, zorder=3))
    ax.text(9.48, y + 0.27, t, va='center', fontsize=7.4, weight='bold', zorder=4)
    ax.text(12.40, y + 0.27, s, va='center', ha='right', fontsize=6.6, color='#777', zorder=4)
    if i < 2:
        arr((10.90, y - 0.005), (10.90, y - 0.115), color=SLOW, lw=1.0, ms=8)
ax.text(10.90, 2.92, '降级链 · 超时8s自动切换', ha='center', fontsize=7.2,
        color=SLOW, weight='bold', zorder=4)
num(9.02, 2.92, 5)
comp(2.60, 0.75, 2.60, 1.48, '决策融合器', '规则优先安全兜底\nLLM增强语义解释', '#e8f5ec', '#2d6a4f')
num(2.77, 2.07, 6)
comp(0.45, 0.75, 1.60, 1.48, '执行器', '气囊/推杆\n三级告警', '#f5f5f5', '#555')
num(0.62, 2.07, 7)

# ═════════ 数据流 ═════════
arr((2.05, 3.62), (2.60, 3.95), color=FAST, lw=2.0)                    # ①→②
arr((5.20, 4.10), (6.48, 3.58), color=FAST, lw=2.0)                    # ②→③ (入菱形顶点)
arr((2.05, 2.88), (5.44, 2.92), color='#555', lw=1.3, ls=(0, (4, 2)))  # ①→③
arr((7.48, 2.92), (9.05, 3.80), color=SLOW, lw=2.0, cs='arc3,rad=-0.15')  # ③→④
ax.text(8.24, 3.62, '多因素案例', fontsize=7.0, color=SLOW, ha='center', rotation=20)
arr((6.48, 2.28), (5.20, 1.66), color=FAST, lw=2.0)                    # ③→⑥
ax.text(6.24, 1.70, '单因素直接执行', fontsize=6.8, color=FAST, ha='center', rotation=25)
arr((9.30, 3.40), (5.20, 1.10), color=SLOW, lw=2.0, cs='arc3,rad=-0.10')  # ④→⑥ (菱形下方绕行)
ax.text(7.55, 1.24, 'JSON决策+置信度', fontsize=7.0, color=SLOW, ha='center', rotation=12)
arr((2.60, 1.49), (2.05, 1.49), lw=2.0)                                # ⑥→⑦
# 降级回路: ④顶 → 顶部走廊 → ②顶 (直角走线, 不穿任何框)
ax.plot([10.90, 10.90, 3.90], [4.90, 5.72, 5.72], ls=(0, (5, 2.4)), color=FAST, lw=1.4,
        zorder=7, solid_capstyle='round')
arr((3.90, 5.72), (3.90, 4.93), color=FAST, lw=1.4, ls=(0, (5, 2.4)), z=7, ms=10)
ax.text(7.40, 5.88, 'LLM超时/失败 → 规则兜底 (演示不中断)', ha='center', fontsize=7.2,
        color=FAST, weight='bold')
# 闭环复评
arr((1.25, 2.23), (1.25, 2.43), color='#2d6a4f', lw=1.4, ls=(0, (3, 2)), ms=10)
ax.text(2.02, 2.33, '闭环复评', fontsize=6.8, color='#2d6a4f', ha='center')

# 图例
for i, (c, ls, t) in enumerate([(FAST, '-', '快通道·规则 <10ms'), (SLOW, '-', '慢通道·LLM 1~3s'),
                                 (FAST, (0, (4, 2.4)), '超时降级回路')]):
    x0 = 3.30 + i * 3.15
    ax.plot([x0, x0 + 0.46], [0.22, 0.22], color=c, ls=ls, lw=1.8, zorder=5, clip_on=False)
    ax.text(x0 + 0.58, 0.22, t, fontsize=7.2, va='center', color='#333', zorder=5)

fig.savefig('D:/IOT/figures/fig2_4_dualchannel.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close(fig)
print('生成: fig2_4_dualchannel.png')
