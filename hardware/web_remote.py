#!/usr/bin/env python3
"""
智能护理病床 - Flask 本地遥控界面 (3页Tab导航 + 自动开启浏览器)

页面:
  P1 🚗 遥控  — 大号方向键，全页操作
  P2 📊 体征  — 体征数据大字显示
  P3 🛏️ 控制  — 床体升降 + 导航控制
"""

import subprocess
import threading
import time
from flask import Flask, render_template_string, jsonify, request

app = Flask(__name__)

navigator   = None
actuator    = None
mqtt_bridge = None

# ══════════════════════════════════════════════
#  HTML — 3页Tab界面，480×320横版触屏优化
# ══════════════════════════════════════════════
HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=480,initial-scale=1,user-scalable=no">
<title>智能护理床</title>
<style>
:root{--bg:#030b1a;--card:rgba(10,22,40,.9);--border:rgba(67,217,173,.2);
  --green:#43d9ad;--blue:#7b8cff;--gold:#f9c74f;--red:#f87171;--dim:rgba(200,216,248,.5);}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
html,body{width:100%;height:100%;background:var(--bg);color:#c8d8f8;
  font-family:'Segoe UI',system-ui,sans-serif;user-select:none;overflow:hidden;}

/* ── 顶栏 ── */
.topbar{height:40px;display:flex;align-items:center;justify-content:space-between;
  padding:0 12px;background:rgba(123,140,255,.1);border-bottom:1px solid var(--border);}
.logo{color:var(--blue);font-weight:700;font-size:14px;}
.ts{font-size:11px;color:var(--green);font-weight:600;}

/* ── Tab导航 ── */
.tabs{display:flex;height:40px;border-bottom:1px solid var(--border);}
.tab{flex:1;display:flex;align-items:center;justify-content:center;gap:5px;
  font-size:13px;font-weight:600;cursor:pointer;color:var(--dim);
  border-bottom:2px solid transparent;transition:.2s;}
.tab.on{color:var(--green);border-bottom-color:var(--green);background:rgba(67,217,173,.07);}

/* ── 页面内容 ── */
.pages{height:calc(100% - 80px);position:relative;}
.page{position:absolute;inset:0;display:none;padding:12px;overflow-y:auto;}
.page.on{display:flex;flex-direction:column;gap:10px;}

/* ── Page 1: 遥控 ── */
.dpad-wrap{flex:1;display:flex;align-items:center;justify-content:center;}
.dpad{display:grid;grid-template-columns:repeat(3,70px);grid-template-rows:repeat(3,70px);gap:6px;}
.bm{border:none;border-radius:12px;color:#fff;font-size:26px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;font-weight:700;}
.bm:active{opacity:.6;transform:scale(.91);}
.mf{background:rgba(33,150,243,.9); grid-column:2;grid-row:1;}
.ml{background:rgba(255,152,0,.85);  grid-column:1;grid-row:2;}
.ms{background:rgba(244,67,54,.95);  grid-column:2;grid-row:2;font-size:20px;}
.mr{background:rgba(255,152,0,.85);  grid-column:3;grid-row:2;}
.mb{background:rgba(255,87,34,.85);  grid-column:2;grid-row:3;}

/* ── Page 2: 体征 ── */
.vgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.vtile{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);
  border-radius:10px;padding:12px 10px;text-align:center;}
.vval{font-size:28px;font-weight:700;color:var(--green);line-height:1;}
.vval.w{color:var(--gold)}.vval.c{color:var(--red)}
.vlbl{font-size:11px;color:var(--dim);margin-top:4px;}
.aist{font-size:11px;color:var(--dim);text-align:center;}

/* ── Page 3: 控制 ── */
.ctrl-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.ctrl-col{display:flex;flex-direction:column;gap:8px;}
.sec-lbl{font-size:11px;font-weight:700;letter-spacing:.08em;
  color:var(--dim);margin-bottom:2px;}
.bc{border:none;border-radius:10px;color:#fff;font-size:14px;font-weight:700;
  height:50px;cursor:pointer;width:100%; transition:opacity .1s;}
.bc:active{opacity:.6;}
.bu{background:rgba(156,39,176,.85);}
.bd{background:rgba(156,39,176,.6);}
.brs{background:rgba(244,67,54,.85);}
.nl{background:rgba(76,175,80,.85);}
.nrf{background:rgba(67,217,173,.4);color:#000;}
.nst{background:rgba(244,67,54,.7);}
.navst{font-size:10px;color:var(--dim);text-align:center;padding:4px;}

/* ── 状态指示 ── */
.dot{width:8px;height:8px;border-radius:50%;background:var(--green);
  display:inline-block;animation:blink .9s infinite;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
</style></head><body>

<!-- 顶栏 -->
<div class="topbar">
  <span class="logo">🛏️ 智能护理床</span>
  <div style="display:flex;gap:14px;align-items:center;">
    <span class="ts"><span id="h-hr">--</span>bpm&nbsp;&nbsp;<span id="h-sp">--</span>%&nbsp;&nbsp;<span id="h-tp">--</span>°C</span>
    <span class="dot"></span>
  </div>
</div>

<!-- Tab导航 -->
<div class="tabs">
  <div class="tab on" id="tab0" onclick="goTab(0)">🚗 遥控</div>
  <div class="tab"    id="tab1" onclick="goTab(1)">📊 体征</div>
  <div class="tab"    id="tab2" onclick="goTab(2)">🛏️ 控制</div>
</div>

<!-- 页面 -->
<div class="pages">

  <!-- P1: D-pad -->
  <div class="page on" id="p0">
    <div class="dpad-wrap">
      <div class="dpad">
        <button class="bm mf"  onmousedown="cmd('forward')"  onmouseup="cmd('stop')"   ontouchstart="cmd('forward')"  ontouchend="cmd('stop')">▲</button>
        <button class="bm ml"  onmousedown="cmd('left')"     onmouseup="cmd('stop')"   ontouchstart="cmd('left')"     ontouchend="cmd('stop')">◄</button>
        <button class="bm ms"  onclick="cmd('stop')">■</button>
        <button class="bm mr"  onmousedown="cmd('right')"    onmouseup="cmd('stop')"   ontouchstart="cmd('right')"    ontouchend="cmd('stop')">►</button>
        <button class="bm mb"  onmousedown="cmd('backward')" onmouseup="cmd('stop')"   ontouchstart="cmd('backward')" ontouchend="cmd('stop')">▼</button>
      </div>
    </div>
    <div class="navst" id="nav-st">导航: 就绪</div>
  </div>

  <!-- P2: 体征 -->
  <div class="page" id="p1">
    <div class="vgrid">
      <div class="vtile"><div class="vval" id="hr">--</div><div class="vlbl">心率 bpm</div></div>
      <div class="vtile"><div class="vval" id="sp">--</div><div class="vlbl">血氧 %</div></div>
      <div class="vtile"><div class="vval" id="tp">--</div><div class="vlbl">体温 °C</div></div>
      <div class="vtile"><div class="vval" id="bp">--/--</div><div class="vlbl">血压 mmHg</div></div>
      <div class="vtile"><div class="vval" id="ulc">--</div><div class="vlbl">受压风险</div></div>
      <div class="vtile"><div class="vval" id="pos" style="font-size:22px">--</div><div class="vlbl">睡姿</div></div>
    </div>
    <div class="aist" id="ai-st">AI: 等待数据</div>
  </div>

  <!-- P3: 床体+导航 -->
  <div class="page" id="p2">
    <div class="ctrl-grid">
      <div class="ctrl-col">
        <div class="sec-lbl">🛏️ 床体升降</div>
        <button class="bc bu"  onclick="cmd('bed_raise')">↑ 靠背升</button>
        <button class="bc bd"  onclick="cmd('bed_lower')">↓ 靠背降</button>
        <button class="bc brs" onclick="cmd('bed_stop')">■ 停止</button>
      </div>
      <div class="ctrl-col">
        <div class="sec-lbl">🧭 自动导航</div>
        <button class="bc nl"  onclick="cmd('nav_line')">循迹导航</button>
        <button class="bc nrf" onclick="navRoom()">RFID 寻房</button>
        <button class="bc nst" onclick="cmd('nav_stop')">停止导航</button>
      </div>
    </div>
    <div class="navst" id="nav-st2">导航: 就绪</div>
  </div>

</div>

<script>
function goTab(i){
  [0,1,2].forEach(function(j){
    document.getElementById('tab'+j).className='tab'+(j===i?' on':'');
    document.getElementById('p'+j).className='page'+(j===i?' on':'');
  });
}
function cmd(a){fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a})}).catch(function(){});}
function navRoom(){
  var r=prompt('目标病房号:','302');
  if(r)fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'nav_rfid',room:r})}).catch(function(){});
}
var PC={supine:'仰卧',prone:'俯卧',left_side:'左侧卧',right_side:'右侧卧',sitting:'坐起',empty:'离床'};
var UC={none:'#43d9ad',low:'#f9c74f',medium:'#ff9800',high:'#f87171'};
function $(id){return document.getElementById(id);}
function tick(){
  fetch('/api/status').then(function(r){return r.json();}).then(function(d){
    var v=d.vitals||{};
    var hr=v.heart_rate, sp=v.blood_oxygen, tp=v.temperature, sy=v.blood_pressure_sys, di=v.blood_pressure_dia;
    $('h-hr').textContent = hr?Math.round(hr):'--';
    $('h-sp').textContent = sp?Math.round(sp):'--';
    $('h-tp').textContent = tp?tp.toFixed(1):'--';
    $('hr').textContent   = hr?Math.round(hr):'--';
    $('sp').textContent   = sp?Math.round(sp):'--';
    $('sp').className     = 'vval'+(sp&&sp<93?' c':'');
    $('tp').textContent   = tp?tp.toFixed(1):'--';
    $('bp').textContent   = sy?sy+'/'+di:'--/--';
    $('pos').textContent  = PC[v.sleep_posture]||v.sleep_posture||'--';
    if(d.analysis){
      var u=d.analysis.ulcer_risk||{};
      $('ulc').textContent=u.level||'none';
      $('ulc').style.color=UC[u.level]||'#43d9ad';
      if(d.analysis.change_stats) {}
      $('ai-st').textContent='AI: '+(d.analysis.occupied?'有人':'空床')+' | 总压:'+Math.round(d.analysis.total_pressure||0);
      if(d.analysis.posture&&d.analysis.posture.posture)
        $('pos').textContent=PC[d.analysis.posture.posture]||d.analysis.posture.posture;
    }
    if(d.nav){
      var ns='导航: '+(d.nav.mode||'?')+' | 前方:'+((d.nav.distances||{}).front||'?')+'cm';
      $('nav-st').textContent=ns; $('nav-st2').textContent=ns;
    }
  }).catch(function(){});
}
setInterval(tick,2000); tick();
</script>
</body></html>"""


# ══════════════════════════════════════════════
#  Flask 路由
# ══════════════════════════════════════════════

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/cmd", methods=["POST"])
def handle_cmd():
    data   = request.json or {}
    action = data.get("action", "")

    if not navigator or not actuator:
        return jsonify({"error": "System not ready"}), 503

    try:
        if   action == "forward":   navigator.manual_forward()
        elif action == "backward":  navigator.manual_backward()
        elif action == "left":      navigator.manual_left()
        elif action == "right":     navigator.manual_right()
        elif action == "stop":      navigator.manual_stop()
        elif action == "nav_line":  navigator.start_line_follow()
        elif action == "nav_rfid":
            from config import RFID_TARGET_ROOM
            navigator.start_rfid_seek(target_room=data.get("room", RFID_TARGET_ROOM))
        elif action == "nav_stop":  navigator.stop()
        elif action == "bed_raise": actuator.raise_bed()
        elif action == "bed_lower": actuator.lower_bed()
        elif action == "bed_stop":  actuator.stop()
        else: return jsonify({"error": f"Unknown action: {action}"}), 400

        return jsonify({"ok": True, "action": action})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/status")
def get_status():
    result = {"vitals": {}, "battery": {}, "nav": {}}
    if mqtt_bridge:
        from mqtt_bridge import get_latest_vitals, get_latest_battery, get_latest_analysis
        result["vitals"]   = get_latest_vitals()
        result["battery"]  = get_latest_battery()
        result["analysis"] = get_latest_analysis()
    if navigator:
        result["nav"] = navigator.get_status()
    return jsonify(result)


# ══════════════════════════════════════════════
#  自动启动浏览器 (非强制全屏，保留窗口关闭按钮)
# ══════════════════════════════════════════════

def _open_browser(port):
    """延迟1.5s等服务器就绪后自动打开Chromium（--app模式：有关闭按钮，无地址栏）"""
    time.sleep(1.5)
    url = f"http://localhost:{port}"

    import os
    env = os.environ.copy()
    # SSH下没有$DISPLAY，手动指向Pi物理屏幕(X11 display :0)
    env.setdefault("DISPLAY", ":0")
    # 自动查找 .Xauthority (登录用户的认证文件)
    for xauth in ["/home/pi/.Xauthority", "/root/.Xauthority",
                  os.path.expanduser("~/.Xauthority")]:
        if os.path.exists(xauth):
            env.setdefault("XAUTHORITY", xauth)
            break

    browsers = [
        ["chromium-browser", f"--app={url}", "--window-size=480,320",
         "--window-position=0,0", "--disable-infobars"],
        ["chromium",         f"--app={url}", "--window-size=480,320",
         "--window-position=0,0", "--disable-infobars"],
        ["midori", url],
        ["epiphany", url],
        ["xdg-open", url],
    ]
    for cmd in browsers:
        try:
            subprocess.Popen(cmd, env=env)
            print(f"[Web] Browser opened on DISPLAY={env['DISPLAY']}: {cmd[0]}")
            return
        except FileNotFoundError:
            continue
    print("[Web] ⚠️  No browser found. Open manually:", url)


def start_web_server(nav, act, bridge, port=5000):
    """启动Web遥控服务器 + 自动打开浏览器"""
    global navigator, actuator, mqtt_bridge
    navigator   = nav
    actuator    = act
    mqtt_bridge = bridge

    # 后台线程跑Flask
    t = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False),
        daemon=True
    )
    t.start()
    print(f"[Web] Remote control at http://0.0.0.0:{port}")

    # 自动打开浏览器（非强制全屏，可点×关闭）
    threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
