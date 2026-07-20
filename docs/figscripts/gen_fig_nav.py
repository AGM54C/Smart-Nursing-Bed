# -*- coding: utf-8 -*-
"""
图二-7 自主寻房导航系统 — ICRA/自动驾驶风格 (v2: 大字号可读版)
(a) 感知-规划-控制流水线 + FSM + 急停旁路 (走廊走线不穿框)
(b) 病区俯视 BEV: 循迹路径 + 三锚点定位 + 避障扇区
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
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

fig = plt.figure(figsize=(11.8, 6.9))
gs = fig.add_gridspec(2, 1, height_ratios=[1.30, 1.0], hspace=0.12,
                      left=0.005, right=0.995, top=0.99, bottom=0.05)

# ═══════════════ (a) 流水线 ═══════════════
ax = fig.add_subplot(gs[0]); ax.set_xlim(0, 13.6); ax.set_ylim(0, 4.42); ax.axis('off')

def box(x, y, w, h, title, rows, style, tfs=8.2, rfs=6.8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.06',
                                fc=style['fc'], ec=style['ec'], lw=1.15, zorder=3))
    ax.text(x + w/2, y + h - 0.24, title, ha='center', va='center', fontsize=tfs,
            weight='bold', color=INK, zorder=4)
    ry = y + h - 0.42
    for r in rows:
        ry -= 0.315
        ax.text(x + w/2, ry, r, ha='center', va='center', fontsize=rfs, color='#333', zorder=4)

def arr(p1, p2, color=INK, lw=1.7, ls='-', ms=11, z=6, cs=None):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='-|>', mutation_scale=ms, color=color,
                                 lw=lw, ls=ls, shrinkA=1.5, shrinkB=3, zorder=z,
                                 connectionstyle=cs or 'arc3,rad=0'))

def elbow(pts, color=INK, lw=1.4, ls='-', ms=10):
    for i in range(len(pts) - 2):
        ax.plot([pts[i][0], pts[i+1][0]], [pts[i][1], pts[i+1][1]], color=color, lw=lw,
                ls=ls, zorder=6, solid_capstyle='round')
    arr(pts[-2], pts[-1], color=color, lw=lw, ls=ls, ms=ms)

# 阶段底色带
for x0, x1, lab, c in [(1.90, 5.15, '感知与定位', '#eaf3ea'), (5.35, 9.10, '决策与规划', '#fdf3e7'),
                        (9.30, 11.75, '运动控制', '#f0eaf6')]:
    ax.add_patch(Rectangle((x0, 0.10), x1 - x0, 3.92, fc=c, ec='none', zorder=1))
    ax.text((x0 + x1)/2, 4.18, lab, ha='center', fontsize=9.2, weight='bold', color='#4a4a4a', zorder=2)
ax.text(0.91, 4.18, '传感器套件', ha='center', fontsize=9.2, weight='bold', color='#4a4a4a')

# 传感器列 (5个, h 0.74)
sensors = [('3× TCRT5000', '循迹 100Hz', 3.28), ('NearLink ×3', '测距 10Hz', 2.46),
           ('3× HC-SR04', '超声 20Hz', 1.64), ('RC522 RFID', '病房卡', 0.82),
           ('8×8 压力垫', '载人检测', 0.00)]
for t, s, y in sensors:
    box(0.10, y, 1.62, 0.74, t, [s], C_SENS, tfs=7.2, rfs=6.2)

# 感知与定位 (两行两列, h 1.45)
box(2.05, 2.25, 1.42, 1.45, '循迹检测', ['三路二值化', '偏差 e∈[-2,2]', '丢线检测'], C_PERC)
box(3.62, 2.25, 1.42, 1.45, '融合定位', ['三边测距', 'RSSI校准', '精度±0.3m'], C_PERC)
box(2.05, 0.50, 1.42, 1.45, '障碍检测', ['三向超声', '30cm减速', '15cm急停'], C_PERC)
box(3.62, 0.50, 1.42, 1.45, '目标识别', ['RFID匹配', '301/302/303', '载人校验'], C_PERC)

# 决策与规划
box(5.55, 2.25, 3.35, 1.45, '导航状态机 (FSM)', [], C_PLAN)
states = ['IDLE', 'FOLLOW', 'AVOID', 'ARRIVE']
sx = [5.98, 6.82, 7.66, 8.50]
for i, (s, x) in enumerate(zip(states, sx)):
    ax.add_patch(FancyBboxPatch((x - 0.37, 2.52), 0.74, 0.42, boxstyle='round,pad=0.02,rounding_size=0.12',
                                fc='white', ec='#d79b00', lw=1.0, zorder=5))
    ax.text(x, 2.73, s, ha='center', va='center', fontsize=6.4, weight='bold', zorder=6)
    if i < 3:
        arr((x + 0.40, 2.73), (sx[i+1] - 0.40, 2.73), lw=1.0, ms=7, color='#b07514', z=6)
arr((7.66, 2.49), (6.82, 2.49), lw=0.9, ms=6, color='#b07514', z=6, cs='arc3,rad=0.4')
box(5.55, 0.50, 1.60, 1.45, '模式仲裁', ['自动: 循迹', '遥控: Web接管', '模式互斥锁'], C_PLAN)
box(7.30, 0.50, 1.60, 1.45, '路径管理', ['病房拓扑图', '床位匹配', '到站停车'], C_PLAN)

# 运动控制
box(9.45, 2.25, 2.15, 1.45, 'PID 速度调节', ['e → PWM差速', 'Kp12 Ki0.5 Kd3', '50Hz控制环'], C_CTRL)
box(9.45, 0.50, 2.15, 1.45, '安全监控', ['载人锁定禁走', '急停最高优先', '超时看门狗'], C_CTRL)

# 执行器
box(11.95, 2.25, 1.55, 1.45, '4× 直流电机', ['2× L298N', '差速转向'], C_ACT)
box(11.95, 0.50, 1.55, 1.45, '状态反馈', ['LCD显示', '云端上报'], C_ACT)

# 流水线箭头
arr((1.72, 3.65), (2.05, 3.30))                                        # TCRT → 循迹
elbow([(1.72, 2.83), (1.89, 2.83), (1.89, 2.12), (3.92, 2.12), (3.92, 2.25)])   # NearLink → 融合定位
arr((1.72, 2.01), (2.05, 1.55))                                        # HC-SR04 → 障碍
elbow([(1.72, 1.19), (1.84, 1.19), (1.84, 2.02), (3.84, 2.02), (3.84, 1.95)])   # RFID → 目标识别
elbow([(1.72, 0.37), (3.98, 0.37), (3.98, 0.50)],
      ls=(0, (3, 2)), lw=1.1)                                          # 压力垫 → 目标识别
arr((3.47, 2.98), (3.62, 2.98), lw=1.2)
arr((5.04, 2.98), (5.55, 3.00))
arr((5.04, 1.22), (5.55, 1.28))
arr((7.15, 1.22), (7.30, 1.22), lw=1.2)
arr((8.90, 2.98), (9.45, 2.98))
arr((8.90, 1.22), (9.45, 1.22))
arr((10.52, 1.95), (10.52, 2.25), lw=1.0, ls=(0, (3, 2)))
ax.text(10.70, 2.09, '联锁', fontsize=6.0, color='#555')
arr((11.60, 2.98), (11.95, 2.98))
arr((11.60, 1.22), (11.95, 1.22))
# 急停旁路: 障碍检测底 → 底部走廊 → 安全监控底
ax.plot([2.76, 2.76, 9.20], [0.50, 0.18, 0.18], color='#c0392b', lw=1.5,
        ls=(0, (5, 2.4)), zorder=7, solid_capstyle='round')
arr((9.20, 0.18), (9.55, 0.48), color='#c0392b', lw=1.5, ls=(0, (5, 2.4)), z=7, ms=9)
ax.text(6.35, 0.02, '急停旁路 <20ms · 绕过规划层 · 最高优先级', ha='center', fontsize=6.8,
        color='#c0392b', weight='bold', zorder=7)

# ═══════════════ (b) 病区俯视 BEV ═══════════════
bx = fig.add_subplot(gs[1]); bx.set_xlim(0, 13.6); bx.set_ylim(0, 3.3); bx.axis('off')
bx.text(0.10, 3.06, '(b) 病区俯视图 · 三锚点定位 + 循迹路径', fontsize=9.2, weight='bold', color=INK)

bx.add_patch(Rectangle((0.6, 0.9), 12.4, 0.85, fc='#f0f0ee', ec='#999', lw=1.0, zorder=1))
bx.text(12.72, 1.32, '走廊', fontsize=7.2, color='#777', va='center')
rooms = [('301', 1.6), ('302', 5.1), ('303', 8.6)]
for name, x in rooms:
    bx.add_patch(Rectangle((x, 1.90), 2.6, 1.00, fc='#fbfbf9', ec='#999', lw=1.0, zorder=1))
    bx.text(x + 0.32, 2.66, name, fontsize=8.0, weight='bold', color='#555')
    bx.add_patch(Rectangle((x + 1.12, 1.80), 0.36, 0.12, fc='#e2b93d', ec='#8a6d1a', lw=0.7, zorder=3))
    bx.text(x + 1.30, 2.06, 'RFID', fontsize=5.8, ha='center', color='#8a6d1a', zorder=3)
    bx.add_patch(Rectangle((x + 1.75, 2.10), 0.70, 0.55, fc='#dae8fc', ec='#6c8ebf', lw=0.8, zorder=2))
    bx.text(x + 2.10, 2.37, '床', fontsize=6.4, ha='center', zorder=3)

path_y = 1.32
bx.plot([1.0, 12.4], [path_y, path_y], color='#2d6a4f', lw=2.2, zorder=2)
for name, x in rooms:
    bx.plot([x + 1.30, x + 1.30], [path_y, 1.92], color='#2d6a4f', lw=1.8, ls=(0, (4, 2)), zorder=2)
bx.text(11.05, 1.06, '磁条/色带引导线', fontsize=6.6, color='#2d6a4f')

anchors = [(2.2, 2.85), (6.8, 0.52), (11.2, 2.85)]
for i, (x, y) in enumerate(anchors):
    for r, a in [(0.50, 0.35), (0.88, 0.18)]:
        bx.add_patch(Circle((x, y), r, fc='none', ec='#2e6da4', lw=0.8, alpha=a, zorder=2))
    bx.add_patch(Polygon([(x-0.11, y-0.10), (x+0.11, y-0.10), (x, y+0.14)],
                         fc='#2e6da4', ec='none', zorder=4))
    bx.text(x + 0.18, y + 0.06, f'锚点A{i+1}', fontsize=6.4, color='#2e6da4', zorder=4)

cart_x = 3.9
bx.add_patch(FancyBboxPatch((cart_x - 0.48, path_y - 0.22), 0.96, 0.44,
                            boxstyle='round,pad=0.02,rounding_size=0.08',
                            fc='#ffe6cc', ec='#d79b00', lw=1.2, zorder=5))
bx.text(cart_x, path_y, '护理床', ha='center', va='center', fontsize=6.6, weight='bold', zorder=6)
bx.add_patch(FancyArrowPatch((cart_x + 0.50, path_y), (cart_x + 1.10, path_y),
                             arrowstyle='-|>', mutation_scale=10, color='#d79b00', lw=1.6, zorder=5))
for x, y in anchors:
    bx.plot([cart_x, x], [path_y, y], ls=(0, (2, 2)), color='#2e6da4', lw=0.8, alpha=0.75, zorder=3)
bx.text(2.55, 0.52, '三边测距解算 (x,y) ±0.3m', fontsize=6.4, color='#2e6da4', ha='center')

obs_x = 6.15
bx.add_patch(Circle((obs_x, path_y), 0.14, fc='#c0392b', ec='none', zorder=4))
bx.text(obs_x - 0.02, 1.58, '障碍物', fontsize=6.4, color='#c0392b', ha='center', zorder=4)
w1 = Arc((cart_x + 0.55, path_y), 3.3, 1.6, theta1=-26, theta2=26, color='#c0392b', lw=0.9, ls='--', zorder=3)
bx.add_patch(w1)
bx.text(5.28, 0.42, '超声扇区: 30cm减速 · 15cm急停', fontsize=6.2, color='#c0392b', ha='center', zorder=4)

bx.add_patch(Circle((5.1 + 1.30, path_y), 0.10, fc='none', ec='#1e6641', lw=1.5, zorder=5))
bx.text(5.1 + 1.30, 1.62, '目标: 302', fontsize=6.6, color='#1e6641', ha='center', weight='bold', zorder=5)

for i, (c, ls, t) in enumerate([('#2d6a4f', '-', '循迹路径'), ('#2e6da4', ':', 'NearLink测距'),
                                 ('#c0392b', '--', '避障扇区'), ('#8a6d1a', '-', 'RFID到站识别')]):
    x0 = 7.55 + i * 1.62
    bx.plot([x0, x0 + 0.36], [0.18, 0.18], color=c, ls=ls, lw=1.6)
    bx.text(x0 + 0.44, 0.18, t, fontsize=6.2, va='center', color='#333')

ax.text(6.8, -0.30, '(a) 感知 — 规划 — 控制流水线', ha='center', fontsize=9.2, weight='bold', color=INK)

fig.savefig('D:/IOT/figures/fig2_7_nav.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close(fig)
print('生成: fig2_7_nav.png')
