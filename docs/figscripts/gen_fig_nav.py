# -*- coding: utf-8 -*-
"""
图二-7 自主寻房导航系统 — ICRA/自动驾驶论文风格:
左: 传感器套件列 → 中: 感知/定位 → 规划(状态机) → 控制 三段流水线 → 右: 执行器
下: 病房俯视图 (BEV) 展示循迹路径 + 三锚点定位圈 + 避障停车带
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, FancyBboxPatch, Circle, Polygon, Arc

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
INK = '#1a1a1a'
C_SENS = dict(fc='#dae8fc', ec='#6c8ebf')
C_PERC = dict(fc='#d5e8d4', ec='#82b366')
C_PLAN = dict(fc='#ffe6cc', ec='#d79b00')
C_CTRL = dict(fc='#e1d5e7', ec='#9673a6')
C_ACT  = dict(fc='#f5f5f5', ec='#666666')

fig = plt.figure(figsize=(13.6, 7.6))
gs = fig.add_gridspec(2, 1, height_ratios=[1.28, 1.0], hspace=0.10,
                      left=0.005, right=0.995, top=0.99, bottom=0.045)

# ═══════════════ (a) 感知-规划-控制流水线 ═══════════════
ax = fig.add_subplot(gs[0]); ax.set_xlim(0, 13.6); ax.set_ylim(0, 4.3); ax.axis('off')

def box(x, y, w, h, title, rows, style, tfs=6.9, rfs=5.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.06',
                                fc=style['fc'], ec=style['ec'], lw=1.15, zorder=3))
    ax.text(x + w/2, y + h - 0.22, title, ha='center', va='center', fontsize=tfs,
            weight='bold', color=INK, zorder=4)
    ry = y + h - 0.40
    for r in rows:
        ry -= 0.245
        ax.text(x + w/2, ry, r, ha='center', va='center', fontsize=rfs, color='#333', zorder=4)

def arr(p1, p2, color=INK, lw=1.7, ls='-', ms=11, z=6, cs=None):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='-|>', mutation_scale=ms, color=color,
                                 lw=lw, ls=ls, shrinkA=1, shrinkB=1, zorder=z,
                                 connectionstyle=cs or 'arc3,rad=0'))

# 阶段底色带
for x0, x1, lab, c in [(1.90, 5.15, '感知与定位', '#eaf3ea'), (5.35, 9.10, '决策与规划', '#fdf3e7'),
                        (9.30, 11.75, '运动控制', '#f0eaf6')]:
    ax.add_patch(Rectangle((x0, 0.18), x1 - x0, 3.92, fc=c, ec='none', zorder=1))
    ax.text((x0 + x1)/2, 4.00, lab, ha='center', fontsize=7.6, weight='bold', color='#4a4a4a', zorder=2)

# 传感器列
sensors = [('3× TCRT5000', '红外循迹 100Hz', 3.44), ('NearLink 锚点×3', '星闪测距 10Hz', 2.62),
           ('3× HC-SR04', '超声测距 20Hz', 1.80), ('RC522 RFID', '病房卡识读', 0.98),
           ('8×8 压力矩阵', '载人检测 1Hz', 0.26)]
for t, s, y in sensors:
    box(0.10, y, 1.62, 0.66, t, [s], C_SENS, tfs=5.9, rfs=5.0)
ax.text(0.91, 4.00, '传感器套件', ha='center', fontsize=7.6, weight='bold', color='#4a4a4a')

# 感知与定位
box(2.05, 2.30, 1.42, 1.30, '循迹检测', ['三路灰度二值化', '偏差量化 e∈[-2,2]', '丢线检测'], C_PERC)
box(3.62, 2.30, 1.42, 1.30, '融合定位', ['三边测距解算', '锚点RSSI校准', '病房级定位±0.3m'], C_PERC)
box(2.05, 0.55, 1.42, 1.30, '障碍检测', ['三向超声融合', '30cm减速带', '15cm急停带'], C_PERC)
box(3.62, 0.55, 1.42, 1.30, '目标识别', ['RFID病房匹配', '301/302/303', '载人状态校验'], C_PERC)

# 决策与规划: 状态机
box(5.55, 2.42, 3.35, 1.18, '导航状态机 (FSM)', [], C_PLAN)
states = ['IDLE', 'FOLLOW', 'AVOID', 'ARRIVE']
sx = [5.90, 6.72, 7.54, 8.36]
for i, (s, x) in enumerate(zip(states, sx)):
    ax.add_patch(FancyBboxPatch((x - 0.30, 2.62), 0.60, 0.34, boxstyle='round,pad=0.02,rounding_size=0.12',
                                fc='white', ec='#d79b00', lw=0.9, zorder=5))
    ax.text(x, 2.79, s, ha='center', va='center', fontsize=5.2, weight='bold', zorder=6)
    if i < 3:
        arr((x + 0.32, 2.79), (sx[i+1] - 0.32, 2.79), lw=0.9, ms=7, color='#b07514', z=6)
# AVOID → FOLLOW 返回弧
arr((7.54, 2.60), (6.72, 2.60), lw=0.8, ms=6, color='#b07514', z=6, cs='arc3,rad=0.35')
box(5.55, 0.55, 1.55, 1.55, '模式仲裁', ['自动: 预设路径循迹', '遥控: Web远程接管', '模式互斥锁'], C_PLAN)
box(7.35, 0.55, 1.55, 1.55, '路径管理', ['病房拓扑图', '目标床位匹配', '到站精准停车'], C_PLAN)

# 运动控制
box(9.45, 2.30, 2.15, 1.30, 'PID 速度调节', ['e → PWM差速', 'Kp=12 Ki=0.5 Kd=3', '50Hz控制环'], C_CTRL)
box(9.45, 0.55, 2.15, 1.30, '安全监控', ['载人锁定禁走', '急停优先级最高', '超时看门狗'], C_CTRL)

# 执行器
box(11.95, 2.30, 1.55, 1.30, '4× 直流电机', ['2× L298N 驱动', '前后差速转向'], C_ACT)
box(11.95, 0.55, 1.55, 1.30, '状态反馈', ['LCD显示航段', '云端位置上报'], C_ACT)

# 流水线箭头
def elbow(pts, color=INK, lw=1.4, ls='-', ms=10):
    for i in range(len(pts) - 2):
        ax.plot([pts[i][0], pts[i+1][0]], [pts[i][1], pts[i+1][1]], color=color, lw=lw,
                ls=ls, zorder=6, solid_capstyle='round')
    arr(pts[-2], pts[-1], color=color, lw=lw, ls=ls, ms=ms)

arr((1.72, 3.77), (2.05, 3.30))                                   # TCRT → 循迹检测
elbow([(1.72, 2.95), (1.90, 2.95), (1.90, 2.14), (3.90, 2.14), (3.90, 2.30)])   # NearLink → 融合定位 (走行间走廊)
arr((1.72, 2.13), (2.05, 1.40))                                   # HC-SR04 → 障碍检测
elbow([(1.72, 1.31), (1.86, 1.31), (1.86, 1.97), (3.86, 1.97), (3.86, 1.85)])   # RFID → 目标识别 (走行间走廊)
elbow([(1.72, 0.59), (1.90, 0.59), (1.90, 0.47), (3.94, 0.47), (3.94, 0.55)],
      ls=(0, (3, 2)), lw=1.1)                                     # 压力矩阵 → 目标识别 (载人校验)
arr((3.47, 2.95), (3.62, 2.95), lw=1.2)
arr((5.04, 2.95), (5.55, 3.00))          # 感知 → FSM
arr((5.04, 1.20), (5.55, 1.30))          # 障碍/目标 → 仲裁
arr((7.10, 1.30), (7.35, 1.30), lw=1.2)
arr((8.90, 3.00), (9.45, 2.98))          # FSM → PID
arr((8.90, 1.30), (9.45, 1.20))          # 路径 → 安全
arr((10.52, 1.85), (10.52, 2.30), lw=1.0, ls=(0, (3, 2)))  # 安全 → PID 联锁
ax.text(10.68, 2.07, '联锁', fontsize=4.9, color='#555')
arr((11.60, 2.95), (11.95, 2.95))
arr((11.60, 1.20), (11.95, 1.20))
# 急停旁路 (红): 障碍检测 → 安全监控, 从规划层盒子下方绕行
ax.plot([2.76, 2.76, 9.20], [0.55, 0.36, 0.36], color='#c0392b', lw=1.5,
        ls=(0, (5, 2.4)), zorder=7, solid_capstyle='round')
arr((9.20, 0.36), (9.55, 0.55), color='#c0392b', lw=1.5, ls=(0, (5, 2.4)), z=7, ms=9)
ax.text(6.05, 0.22, '急停旁路 <20ms (绕过规划层 · 最高优先级)', ha='center', fontsize=5.6,
        color='#c0392b', weight='bold', zorder=7)

# ═══════════════ (b) 病房俯视 BEV ═══════════════
bx = fig.add_subplot(gs[1]); bx.set_xlim(0, 13.6); bx.set_ylim(0, 3.3); bx.axis('off')
bx.text(0.10, 3.05, '(b) 病区俯视图 · 三锚点定位 + 磁条循迹路径', fontsize=7.6, weight='bold', color=INK)

# 走廊 + 病房
bx.add_patch(Rectangle((0.6, 0.9), 12.4, 0.85, fc='#f0f0ee', ec='#999', lw=1.0, zorder=1))
bx.text(12.75, 1.32, '走廊', fontsize=6.0, color='#777', va='center')
rooms = [('301', 1.6), ('302', 5.1), ('303', 8.6)]
for name, x in rooms:
    bx.add_patch(Rectangle((x, 1.90), 2.6, 1.00, fc='#fbfbf9', ec='#999', lw=1.0, zorder=1))
    bx.text(x + 0.30, 2.72, name, fontsize=6.6, weight='bold', color='#555')
    # 门口 RFID 标签
    bx.add_patch(Rectangle((x + 1.12, 1.80), 0.36, 0.12, fc='#e2b93d', ec='#8a6d1a', lw=0.7, zorder=3))
    bx.text(x + 1.30, 2.06, 'RFID', fontsize=4.6, ha='center', color='#8a6d1a', zorder=3)
    # 床位
    bx.add_patch(Rectangle((x + 1.75, 2.10), 0.70, 0.55, fc='#dae8fc', ec='#6c8ebf', lw=0.8, zorder=2))
    bx.text(x + 2.10, 2.37, '床', fontsize=5.2, ha='center', zorder=3)

# 磁条主路径 (走廊中线) + 入房支路
path_y = 1.32
bx.plot([1.0, 12.4], [path_y, path_y], color='#2d6a4f', lw=2.2, zorder=2)
for name, x in rooms:
    bx.plot([x + 1.30, x + 1.30], [path_y, 1.92], color='#2d6a4f', lw=1.8, ls=(0, (4, 2)), zorder=2)
bx.text(11.6, 1.10, '磁条/色带引导线', fontsize=5.4, color='#2d6a4f')

# NearLink 锚点 ×3 + 测距圆
anchors = [(2.2, 2.85), (6.8, 0.55), (11.2, 2.85)]
for i, (x, y) in enumerate(anchors):
    for r, a in [(0.55, 0.35), (0.95, 0.18)]:
        bx.add_patch(Circle((x, y), r, fc='none', ec='#2e6da4', lw=0.8, alpha=a, zorder=2))
    bx.add_patch(Polygon([(x-0.10, y-0.09), (x+0.10, y-0.09), (x, y+0.13)],
                         fc='#2e6da4', ec='none', zorder=4))
    bx.text(x + 0.16, y + 0.05, f'锚点A{i+1}', fontsize=5.2, color='#2e6da4', zorder=4)

# 病床小车 (当前位姿) + 航向
cart_x = 3.9
bx.add_patch(FancyBboxPatch((cart_x - 0.42, path_y - 0.20), 0.84, 0.40,
                            boxstyle='round,pad=0.02,rounding_size=0.08',
                            fc='#ffe6cc', ec='#d79b00', lw=1.2, zorder=5))
bx.text(cart_x, path_y, '护理床', ha='center', va='center', fontsize=5.4, weight='bold', zorder=6)
bx.add_patch(FancyArrowPatch((cart_x + 0.44, path_y), (cart_x + 1.05, path_y),
                             arrowstyle='-|>', mutation_scale=10, color='#d79b00', lw=1.6, zorder=5))
# 测距虚线到三锚点
for x, y in anchors:
    bx.plot([cart_x, x], [path_y, y], ls=(0, (2, 2)), color='#2e6da4', lw=0.75, alpha=0.75, zorder=3)
bx.text(cart_x - 0.05, 0.62, '三边测距解算 (x, y) ±0.3m', fontsize=5.2, color='#2e6da4', ha='center')

# 障碍 + 检测扇区
obs_x = 6.15
bx.add_patch(Circle((obs_x, path_y), 0.14, fc='#c0392b', ec='none', zorder=4))
bx.text(obs_x, path_y + 0.30, '障碍物', fontsize=5.2, color='#c0392b', ha='center', zorder=4)
w1 = Arc((cart_x + 0.5, path_y), 3.4, 1.7, theta1=-28, theta2=28, color='#c0392b', lw=0.9, ls='--', zorder=3)
bx.add_patch(w1)
bx.text(5.35, 1.78, '超声检测扇区\n30cm减速 · 15cm急停', fontsize=4.9, color='#c0392b', ha='center', zorder=4)

# 目标标记
bx.add_patch(Circle((5.1 + 1.30, 1.32), 0.10, fc='none', ec='#1e6641', lw=1.4, zorder=5))
bx.text(5.1 + 1.30, 1.58, '目标: 302', fontsize=5.2, color='#1e6641', ha='center', weight='bold', zorder=5)

# 图例
for i, (c, ls, t) in enumerate([('#2d6a4f', '-', '循迹路径'), ('#2e6da4', ':', 'NearLink测距'),
                                 ('#c0392b', '--', '避障扇区'), ('#8a6d1a', '-', 'RFID到站识别')]):
    x0 = 0.75 + i * 1.85
    bx.plot([x0, x0 + 0.38], [0.22, 0.22], color=c, ls=ls, lw=1.5)
    bx.text(x0 + 0.48, 0.22, t, fontsize=5.4, va='center', color='#333')

ax.text(6.8, -0.06, '(a) 感知 — 规划 — 控制流水线', ha='center', fontsize=7.8, weight='bold', color=INK)

fig.savefig('D:/IOT/figures/fig2_7_nav.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close(fig)
print('生成: fig2_7_nav.png')
