# -*- coding: utf-8 -*-
"""
图四-3 系统数据传输协议栈与网络拓扑 — 通信顶会 (SIGCOMM/MobiCom/INFOCOM) 论文风格
  (a) 网络拓扑与承载链路: 感知/边缘/云/应用 四层列式布局, 链路标注协议·端口·QoS,
      实线=数据面 / 虚线=控制面 / 点线=媒体流
  (b) 端到端协议栈: 边缘网关 MQTT→HTTPS 协议转换双半栈 + U 型数据路径
"""
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, Circle

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
OUT = r'D:/IOT/figures'

# ── 论文级配色 (低饱和 + 深描边) ──
INK   = '#1a1a1a'
C_BLUE   = dict(fc='#dae8fc', ec='#6c8ebf')   # 感知
C_GREEN  = dict(fc='#d5e8d4', ec='#82b366')   # 边缘
C_ORANGE = dict(fc='#ffe6cc', ec='#d79b00')   # 云 ECS
C_PURPLE = dict(fc='#e1d5e7', ec='#9673a6')   # 涂鸦云
C_GRAY   = dict(fc='#f5f5f5', ec='#666666')   # 终端
ACCENT   = '#b85450'                          # 局域网低时延路径
LINK     = '#3d3d3d'

def node(ax, x, y, w, h, title, rows, style, title_fs=7.6, row_fs=6.2, row_h=0.46):
    ax.add_patch(Rectangle((x, y), w, h, fc=style['fc'], ec=style['ec'], lw=1.1, zorder=2))
    ax.text(x + w/2, y + h - 0.30, title, ha='center', va='center',
            fontsize=title_fs, weight='bold', color=INK, zorder=4)
    ry = y + h - 0.62
    for r in rows:
        ry -= row_h + 0.10
        ax.add_patch(Rectangle((x + 0.10, ry), w - 0.20, row_h, fc='white',
                               ec='#8a8a8a', lw=0.6, zorder=3))
        ax.text(x + w/2, ry + row_h/2, r, ha='center', va='center',
                fontsize=row_fs, color='#2d2d2d', zorder=4)
    return ry  # y of last row bottom

def edge_lbl(ax, x, y, lines, fs=6.0, color=LINK):
    txt = '\n'.join(lines)
    ax.text(x, y, txt, ha='center', va='center', fontsize=fs, color=color, zorder=6,
            linespacing=1.25,
            bbox=dict(boxstyle='round,pad=0.18', fc='white', ec='none', alpha=0.92))

def arrow(ax, p1, p2, ls='-', color=LINK, lw=1.25, both=False, z=5):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='<|-|>' if both else '-|>',
                                 mutation_scale=7, ls=ls, color=color, lw=lw,
                                 shrinkA=0, shrinkB=0, zorder=z))

def badge(ax, x, y, n, r=0.135):
    ax.add_patch(Circle((x, y), r, fc=INK, ec='none', zorder=7))
    ax.text(x, y - 0.004, n, ha='center', va='center', fontsize=5.8,
            color='white', weight='bold', zorder=8)

def elbow(ax, pts, ls, color, lw=1.25):
    for i in range(len(pts) - 1):
        last = i == len(pts) - 2
        if last:
            arrow(ax, pts[i], pts[i+1], ls=ls, color=color, lw=lw)
        else:
            ax.plot([pts[i][0], pts[i+1][0]], [pts[i][1], pts[i+1][1]],
                    ls=ls, color=color, lw=lw, zorder=5, solid_capstyle='round')

fig = plt.figure(figsize=(13.4, 5.9))
gs = fig.add_gridspec(1, 2, width_ratios=[1.66, 1.0], wspace=0.06,
                      left=0.005, right=0.995, top=0.985, bottom=0.055)

# ═══════════════════ (a) 网络拓扑与承载链路 ═══════════════════
ax = fig.add_subplot(gs[0]); ax.set_xlim(0, 10.4); ax.set_ylim(0, 7.35); ax.axis('off')

# 四层列头
tiers = [('感知层', 0.15, 2.35), ('边缘层', 2.65, 4.95), ('云平台层', 5.25, 7.55), ('应用层', 7.85, 10.25)]
for name, x0, x1 in tiers:
    ax.add_patch(Rectangle((x0, 6.78), x1 - x0, 0.42, fc='#ececec', ec='none', zorder=1))
    ax.text((x0 + x1)/2, 6.99, name, ha='center', va='center', fontsize=7.2,
            weight='bold', color='#4a4a4a')
    ax.plot([x0, x1], [6.78, 6.78], color='#bdbdbd', lw=0.8, zorder=1)

# 节点
node(ax, 0.25, 4.05, 2.0, 2.35, 'ESP32-S3 传感节点',
     ['8×8 织物压力阵列', '心率 · 血氧 · 体温', 'Wi-Fi 802.11n / 2.4G'], C_BLUE)
node(ax, 0.25, 1.30, 2.0, 1.80, '星闪定位锚点 ×3',
     ['NearLink Hi3863', '三边测距 定位'], C_BLUE)
node(ax, 2.80, 1.05, 2.0, 5.35, '树莓派 4B 边缘网关',
     ['Mosquitto Broker :1883', 'MQTT-HTTP Bridge', '边缘AI 推理 (ONNX)',
      'Flask 床旁遥控 :5000', 'mediamtx 视频 :8889', 'NearLink 定位解算'], C_GREEN)
node(ax, 5.40, 4.45, 2.0, 1.95, '阿里云 ECS 云平台',
     ['Express REST :3000', 'SQLite WAL · PM2'], C_ORANGE)
node(ax, 5.40, 1.75, 2.0, 1.95, '涂鸦 IoT 云',
     ['TuyaLink 设备接入', 'AI Agent OpenAPI'], C_PURPLE)
node(ax, 8.00, 5.15, 2.1, 1.25, 'Web 监护控制台', ['REST · SSE · WebRTC'], C_GRAY)
node(ax, 8.00, 3.45, 2.1, 1.25, '鸿蒙 App', ['HarmonyOS 6 · 双地址'], C_GRAY)
node(ax, 8.00, 1.75, 2.1, 1.25, '智能生活 App', ['涂鸦面板 · 远程告警'], C_GRAY)

# ── 主链路 ──
# ① ESP32 → Broker (RPi 顶行 y≈5.53)
arrow(ax, (2.25, 5.35), (2.80, 5.53))
edge_lbl(ax, 2.52, 6.10, ['MQTT 3.1.1 · TCP:1883', 'QoS1 · 6 Topics · 2s 周期'])
badge(ax, 2.52, 5.72, '1')
# 星闪锚点 → RPi 定位解算行 (虚线控制面)
arrow(ax, (2.25, 2.52), (2.80, 2.65), ls=(0, (4, 2.6)), color='#6e6e6e', lw=1.0)
edge_lbl(ax, 2.52, 2.22, ['NearLink 2.4G 测距'], color='#5a5a5a')
# ② RPi → ECS
arrow(ax, (4.80, 5.30), (5.40, 5.30))
edge_lbl(ax, 5.10, 5.86, ['HTTPS REST', 'X-API-Key'])
badge(ax, 5.10, 5.53, '2')
# ③ RPi → 涂鸦云
arrow(ax, (4.80, 2.60), (5.40, 2.60))
edge_lbl(ax, 5.10, 3.16, ['MQTTS · TLS:8883', 'TuyaLink 三元组'])
badge(ax, 5.10, 2.83, '3')
# ④ ECS ↔ 涂鸦云 (Agent 调用, 控制面)
arrow(ax, (6.40, 4.45), (6.40, 3.70), ls=(0, (4, 2.6)), color='#6e6e6e', lw=1.0, both=True)
edge_lbl(ax, 6.52, 4.08, ['OpenAPI · HMAC-SHA256'], color='#5a5a5a')
badge(ax, 5.56, 4.08, '4')
# ⑤ ECS → Web / 鸿蒙
arrow(ax, (7.40, 5.75), (8.00, 5.78))
edge_lbl(ax, 7.70, 6.12, ['REST · JWT / SSE'])
badge(ax, 7.70, 5.50, '5')
arrow(ax, (7.40, 4.90), (8.00, 4.10))
edge_lbl(ax, 7.66, 4.30, ['REST · JWT'])
# ⑥ 涂鸦云 → 智能生活App
arrow(ax, (7.40, 2.38), (8.00, 2.38))
edge_lbl(ax, 7.70, 2.74, ['面板 DP 数据点'])
badge(ax, 7.70, 2.12, '6')
# ⑦ 鸿蒙App → RPi Flask (局域网直连, accent 虚线; 绕右侧走线避开智能生活App)
elbow(ax, [(10.10, 4.05), (10.30, 4.05), (10.30, 0.62), (4.35, 0.62), (4.35, 1.05)],
      ls=(0, (5, 2.4)), color=ACCENT)
edge_lbl(ax, 6.70, 0.62, ['NLC 局域网直连 · 低时延语音/床体控制'], color=ACCENT)
badge(ax, 8.62, 0.62, '7')
# ⑧ Web → mediamtx (WebRTC 媒体流, 点线)
elbow(ax, [(7.78, 5.15), (7.78, 0.30), (3.55, 0.30), (3.55, 1.05)],
      ls=(0, (1.2, 1.6)), color='#2e6da4', lw=1.15)
edge_lbl(ax, 5.95, 0.30, ['WebRTC · SRTP 实时视频'], color='#2e6da4')
badge(ax, 7.45, 0.30, '8')

ax.text(5.2, -0.10, '(a) 网络拓扑与承载链路', ha='center', fontsize=8.4, weight='bold', color=INK)

# ═══════════════════ (b) 端到端协议栈 ═══════════════════
bx = fig.add_subplot(gs[1]); bx.set_xlim(0, 6.4); bx.set_ylim(0, 7.35); bx.axis('off')

X_E, W_E = 0.62, 1.42            # ESP32 栈
X_G, W_G = 2.36, 1.86            # 网关双半栈
X_C, W_C = 4.54, 1.42            # ECS 栈
GXM = X_G + W_G/2                # 网关中线
ROW_H, GAP, Y0 = 0.56, 0.10, 1.30
LAYERS = ['链路层', '网络层', '传输层', '安全层', '应用层']

def cell(x, y, w, txt, style, fs=6.0):
    bx.add_patch(Rectangle((x, y), w, ROW_H, fc=style['fc'], ec=style['ec'], lw=0.9, zorder=3))
    bx.text(x + w/2, y + ROW_H/2, txt, ha='center', va='center', fontsize=fs, color=INK, zorder=4)

ys = {}
for i, name in enumerate(LAYERS):
    y = Y0 + i * (ROW_H + GAP)
    ys[name] = y
    bx.text(0.50, y + ROW_H/2, name, ha='right', va='center', fontsize=6.0, color='#7a7a7a')

# ESP32 栈
cell(X_E, ys['链路层'], W_E, 'Wi-Fi 802.11n', C_BLUE)
cell(X_E, ys['网络层'], W_E, 'IPv4', C_BLUE)
cell(X_E, ys['传输层'], W_E, 'TCP', C_BLUE)
cell(X_E, ys['安全层'], W_E, '— (内网)', C_BLUE)
cell(X_E, ys['应用层'], W_E, 'MQTT 3.1.1', C_BLUE)
# 网关: 下三层整块, 上两层左右半栈
cell(X_G, ys['链路层'], W_G, 'Wi-Fi  |  Ethernet', C_GREEN)
cell(X_G, ys['网络层'], W_G, 'IPv4', C_GREEN)
cell(X_G, ys['传输层'], W_G, 'TCP', C_GREEN)
HW = W_G/2 - 0.03
cell(X_G, ys['安全层'], HW, '—', C_GREEN)
cell(X_G + W_G/2 + 0.03, ys['安全层'], HW, 'TLS 1.2', C_GREEN)
cell(X_G, ys['应用层'], HW, 'MQTT', C_GREEN)
cell(X_G + W_G/2 + 0.03, ys['应用层'], HW, 'HTTP/1.1', C_GREEN)
# ECS 栈
cell(X_C, ys['链路层'], W_C, 'Ethernet', C_ORANGE)
cell(X_C, ys['网络层'], W_C, 'IPv4', C_ORANGE)
cell(X_C, ys['传输层'], W_C, 'TCP', C_ORANGE)
cell(X_C, ys['安全层'], W_C, 'TLS 1.2', C_ORANGE)
cell(X_C, ys['应用层'], W_C, 'HTTP/1.1', C_ORANGE)

# 顶部应用实体
y_app = ys['应用层'] + ROW_H + 0.14
bx.add_patch(Rectangle((X_E, y_app), W_E, ROW_H, fc='white', ec='#8a8a8a', lw=0.8, zorder=3))
bx.text(X_E + W_E/2, y_app + ROW_H/2, '采集固件', ha='center', va='center', fontsize=6.0, zorder=4)
bx.add_patch(Rectangle((X_G, y_app), W_G, ROW_H, fc='#fff2cc', ec='#d6b656', lw=1.0, zorder=3))
bx.text(X_G + W_G/2, y_app + ROW_H/2, 'Bridge 协议转换', ha='center', va='center',
        fontsize=6.2, weight='bold', zorder=4)
bx.add_patch(Rectangle((X_C, y_app), W_C, ROW_H, fc='white', ec='#8a8a8a', lw=0.8, zorder=3))
bx.text(X_C + W_C/2, y_app + ROW_H/2, 'Express API', ha='center', va='center', fontsize=6.0, zorder=4)

# 节点名
bx.text(X_E + W_E/2, y_app + ROW_H + 0.30, 'ESP32-S3', ha='center', fontsize=6.8, weight='bold')
bx.text(X_G + W_G/2, y_app + ROW_H + 0.30, '边缘网关 (树莓派)', ha='center', fontsize=6.8, weight='bold')
bx.text(X_C + W_C/2, y_app + ROW_H + 0.30, '云端 ECS', ha='center', fontsize=6.8, weight='bold')

# 对等层协议 (虚线)
def peer(x1, x2, layer, txt):
    y = ys[layer] + ROW_H/2
    bx.plot([x1, x2], [y, y], ls=(0, (3, 2)), color='#9a9a9a', lw=0.85, zorder=2)
    bx.text((x1 + x2)/2, y + 0.175, txt, ha='center', fontsize=5.4, color='#6a6a6a', zorder=4)
peer(X_E + W_E, X_G, '应用层', 'MQTT · QoS1')
peer(X_G + W_G, X_C, '应用层', 'REST / JSON')
peer(X_E + W_E, X_G, '传输层', 'TCP')
peer(X_G + W_G, X_C, '传输层', 'TCP')

# 物理承载
y_phy = Y0 - 0.42
bx.plot([X_E + W_E/2, X_G + 0.3], [y_phy, y_phy], color=INK, lw=1.1)
bx.plot([X_E + W_E/2, X_E + W_E/2], [Y0, y_phy], color=INK, lw=1.1)
bx.plot([X_G + 0.3, X_G + 0.3], [Y0, y_phy], color=INK, lw=1.1)
bx.text((X_E + W_E/2 + X_G + 0.3)/2, y_phy - 0.20, '无线信道 2.4 GHz', ha='center', fontsize=5.6, color='#4a4a4a')
bx.plot([X_G + W_G - 0.3, X_C + W_C/2], [y_phy, y_phy], color=INK, lw=1.1)
bx.plot([X_G + W_G - 0.3, X_G + W_G - 0.3], [Y0, y_phy], color=INK, lw=1.1)
bx.plot([X_C + W_C/2, X_C + W_C/2], [Y0, y_phy], color=INK, lw=1.1)
bx.text((X_G + W_G - 0.3 + X_C + W_C/2)/2, y_phy - 0.20, '互联网 (公网)', ha='center', fontsize=5.6, color='#4a4a4a')

# U 型数据路径 (蓝色半透明)
DP = '#2e6da4'
u1 = X_E + W_E/2 - 0.25
u2 = X_G + 0.44
u3 = X_G + W_G - 0.44
u4 = X_C + W_C/2 + 0.25
y_top = y_app + ROW_H/2
elbow_pts = [
    (u1, y_top), (u1, y_phy + 0.10), (u2, y_phy + 0.10), (u2, y_top - 0.0),
]
for i in range(len(elbow_pts) - 1):
    bx.plot([elbow_pts[i][0], elbow_pts[i+1][0]], [elbow_pts[i][1], elbow_pts[i+1][1]],
            color=DP, lw=2.2, alpha=0.42, zorder=1, solid_capstyle='round')
bx.plot([u2, u3], [y_top, y_top], color=DP, lw=2.2, alpha=0.42, zorder=1)
pts2 = [(u3, y_top), (u3, y_phy + 0.10), (u4, y_phy + 0.10), (u4, y_top)]
for i in range(len(pts2) - 1):
    bx.plot([pts2[i][0], pts2[i+1][0]], [pts2[i][1], pts2[i+1][1]],
            color=DP, lw=2.2, alpha=0.42, zorder=1, solid_capstyle='round')
bx.add_patch(FancyArrowPatch((u4 - 0.001, y_top - 0.05), (u4, y_top),
                             arrowstyle='-|>', mutation_scale=9, color=DP, alpha=0.75, zorder=2))
bx.text(GXM, y_phy + 0.24, '数据路径', ha='center', fontsize=5.4, color=DP, alpha=0.95)

bx.text(3.2, -0.10, '(b) 端到端协议栈与网关协议转换', ha='center', fontsize=8.4, weight='bold', color=INK)

# 图例 (整图右上, 放 (b) 顶部空白)
ly = 6.85
for i, (ls, c, t) in enumerate([
        ('-', LINK, '数据面'), ((0, (4, 2.6)), '#6e6e6e', '控制面/信令'),
        ((0, (1.2, 1.6)), '#2e6da4', '媒体流'), ((0, (5, 2.4)), ACCENT, '局域网低时延')]):
    x0 = 0.55 + i * 1.52
    bx.plot([x0, x0 + 0.42], [ly, ly], ls=ls, color=c, lw=1.3)
    bx.text(x0 + 0.52, ly, t, ha='left', va='center', fontsize=5.8, color='#3d3d3d')
bx.add_patch(Rectangle((0.38, 6.60), 5.9, 0.5, fc='none', ec='#c9c9c9', lw=0.7))

fig.savefig(f'{OUT}/fig4_3_commlink.png', dpi=200, facecolor='white')
plt.close(fig)
print('生成: fig4_3_commlink.png')
