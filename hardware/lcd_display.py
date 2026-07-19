#!/usr/bin/env python3
"""
智能护理病床 - 3.5寸触摸屏 床旁控制面板 v2.0

三页循环切换:
  Page 0: 生命体征  — 病人/家属用，大字体展示心率/血氧/体温/血压/睡姿/受压风险
  Page 1: 快捷操作  — 呼叫护士 / 床头升降 / 翻身提醒确认
  Page 2: 系统状态  — 导航/WiFi/MQTT/决策日志，护士/运维用

触摸驱动安装 (树莓派首次):
  sudo apt-get install -y python3-evdev
  # 确认触摸设备路径：
  sudo evtest
  # 通常是 /dev/input/event0 或 event1

输出方式: Pillow 绘图 → /dev/fb1 (RGB565)
刷新率: 正常 1fps，进入控制页时 5fps（响应更快）
"""

import time
import threading
import math

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[LCD] ⚠️ Pillow not available, run: pip install Pillow")

try:
    import evdev
    from evdev import InputDevice, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    print("[LCD] ⚠️ evdev not available, run: pip install evdev  (or: sudo apt install python3-evdev)")

from config import LCD_ENABLED, LCD_WIDTH, LCD_HEIGHT

# ─── 颜色主题 ───
C_BG        = '#0b0c1e'
C_HEADER    = '#12133a'
C_CARD      = '#141527'
C_BORDER    = '#2a2b4a'
C_TEXT      = '#dde1ff'
C_DIM       = '#6b7080'
C_ACCENT    = '#7b8cff'
C_GREEN     = '#4ecca3'
C_RED       = '#ff5c5c'
C_YELLOW    = '#ffd366'
C_ORANGE    = '#ff9a3c'
C_PURPLE    = '#c77dff'
C_BLUE      = '#38bdf8'

# 生命体征正常范围（用于告警检测）
VITAL_RANGES = {
    'heart_rate':       (50, 100),
    'blood_oxygen':     (95, 100),
    'temperature':      (36.0, 37.5),
    'blood_pressure_sys': (90, 140),
}

# Tab 热区定义（底栏 y=285~320，各占1/3宽）
TAB_Y_START = 285
TAB_ZONES = [
    (0,         LCD_WIDTH // 3,     0),   # Page 0 热区
    (LCD_WIDTH // 3, LCD_WIDTH * 2 // 3, 1),
    (LCD_WIDTH * 2 // 3, LCD_WIDTH,  2),
]

# Page 1 按钮热区 [label, x1, y1, x2, y2, action_key]
PAGE1_BUTTONS = [
    ('呼叫护士',  10,  60, 460, 130, 'call_nurse'),
    ('↑ 升床',   10, 145, 225, 205, 'bed_raise'),
    ('↓ 降床',  245, 145, 460, 205, 'bed_lower'),
    ('停止',     10, 220, 460, 275, 'bed_stop'),
]


# ─────────────────────────────────────────────
class LCDDisplay:
    """3.5寸 SPI TFT LCD 多页触摸控制面板"""

    def __init__(self):
        self.width  = LCD_WIDTH
        self.height = LCD_HEIGHT
        self._running   = False
        self._thread    = None
        self._touch_thread = None
        self._data_getter  = None
        self._action_cb    = None   # 按键动作回调 fn(action_key)

        self._page   = 0            # 当前页 0/1/2
        self._blink  = True         # 告警闪烁状态
        self._frame  = 0

        # Pillow 画布
        if PIL_AVAILABLE:
            self.image = Image.new('RGB', (self.width, self.height), C_BG)
            self.draw  = ImageDraw.Draw(self.image)
            self._load_fonts()
        else:
            self.image = None
            self.draw  = None

        # evdev 触摸
        self._touch_dev = None
        if EVDEV_AVAILABLE:
            self._find_touch_device()

        print(f"[LCD] v2.0 initialized ({self.width}×{self.height}), "
              f"touch={'yes' if self._touch_dev else 'no'}")

    # ══════════════════════════════════════════
    #  初始化
    # ══════════════════════════════════════════

    def _load_fonts(self):
        """加载文泉驿中文字体（树莓派），fallback 到默认字体"""
        font_paths = [
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        def _try_font(size):
            for p in font_paths:
                try:
                    return ImageFont.truetype(p, size)
                except OSError:
                    pass
            return ImageFont.load_default()

        self.font_xl     = _try_font(40)   # 大数值
        self.font_large  = _try_font(28)
        self.font_medium = _try_font(20)
        self.font_small  = _try_font(15)
        self.font_tiny   = _try_font(12)

    def _find_touch_device(self):
        """自动扫描 evdev 触摸设备"""
        for path in ('/dev/input/event0', '/dev/input/event1',
                     '/dev/input/event2', '/dev/input/event3'):
            try:
                dev = InputDevice(path)
                caps = dev.capabilities()
                # 判断是否有 ABS_X / ABS_Y（触摸屏特征）
                if ecodes.EV_ABS in caps:
                    self._touch_dev = dev
                    print(f"[LCD] Touch device: {dev.name} @ {path}")
                    return
            except Exception:
                pass
        print("[LCD] No touch device found. Install: sudo apt-get install -y python3-evdev")

    # ══════════════════════════════════════════
    #  数据 & 回调
    # ══════════════════════════════════════════

    def set_data_source(self, getter_func):
        """
        设置数据源函数。
        getter_func() 返回 dict:
          {vitals, battery, nav, analysis}
        """
        self._data_getter = getter_func

    def set_action_callback(self, callback):
        """
        设置按键回调。
        callback(action_key: str) — 由触摸事件触发后在主循环线程调用。
        action_key 可为: call_nurse / bed_raise / bed_lower / bed_stop / page_N
        """
        self._action_cb = callback

    def _get_data(self):
        if self._data_getter:
            try:
                return self._data_getter()
            except Exception:
                pass
        return {}

    def _is_alert(self, key, value):
        """判断某生命体征是否超出正常范围"""
        if value is None or value == '--':
            return False
        lo, hi = VITAL_RANGES.get(key, (None, None))
        if lo is None:
            return False
        try:
            return not (lo <= float(value) <= hi)
        except (ValueError, TypeError):
            return False

    # ══════════════════════════════════════════
    #  渲染工具
    # ══════════════════════════════════════════

    def _rect(self, x1, y1, x2, y2, fill=C_CARD, outline=C_BORDER, radius=8):
        """带圆角的矩形（Pillow 9+ 支持 radius）"""
        try:
            self.draw.rounded_rectangle([x1, y1, x2, y2], radius=radius,
                                        fill=fill, outline=outline)
        except AttributeError:
            self.draw.rectangle([x1, y1, x2, y2], fill=fill, outline=outline)

    def _text(self, x, y, txt, font=None, fill=C_TEXT, anchor='la'):
        font = font or self.font_small
        self.draw.text((x, y), txt, font=font, fill=fill, anchor=anchor)

    def _centered_text(self, cx, y, txt, font=None, fill=C_TEXT):
        font = font or self.font_small
        bbox = font.getbbox(txt)
        w = bbox[2] - bbox[0]
        self.draw.text((cx - w // 2, y), txt, font=font, fill=fill)

    # ══════════════════════════════════════════
    #  顶栏（通用）
    # ══════════════════════════════════════════

    def _draw_header(self, battery):
        """绘制顶部信息栏"""
        self._rect(0, 0, self.width, 36, fill=C_HEADER, outline=C_HEADER, radius=0)

        self._text(10, 4, "🛏 智能护理病床", font=self.font_medium, fill=C_ACCENT)

        time_str = time.strftime("%H:%M")
        self._text(self.width - 110, 8, time_str, font=self.font_small, fill=C_DIM)

        bat = battery.get('percent', '--')
        bat_color = C_GREEN if isinstance(bat, (int, float)) and bat > 20 else C_RED
        self._text(self.width - 55, 8, f"🔋{bat}%", font=self.font_small, fill=bat_color)

    # ══════════════════════════════════════════
    #  底部 Tab 栏（通用）
    # ══════════════════════════════════════════

    def _draw_tabs(self):
        tabs = [("📊 体征", 0), ("🎮 操作", 1), ("🔧 状态", 2)]
        tw = self.width // 3
        self._rect(0, TAB_Y_START, self.width, self.height,
                   fill=C_HEADER, outline=C_HEADER, radius=0)
        for i, (label, page_idx) in enumerate(tabs):
            x1 = i * tw
            x2 = x1 + tw - 2
            active = (self._page == page_idx)
            fill    = C_ACCENT if active else C_HEADER
            fg      = '#fff'   if active else C_DIM
            self._rect(x1 + 2, TAB_Y_START + 2, x2, self.height - 2,
                       fill=fill, outline=C_BORDER, radius=6)
            self._centered_text((x1 + x2) // 2, TAB_Y_START + 8,
                                label, font=self.font_small, fill=fg)

    # ══════════════════════════════════════════
    #  Page 0：生命体征
    # ══════════════════════════════════════════

    def _render_page0(self, data):
        vitals   = data.get('vitals', {})
        analysis = data.get('analysis', {})

        # ── 大数值卡片 ──
        cards = [
            ('heart_rate',       '♥ 心率',  vitals.get('heart_rate', '--'),  'bpm',   C_RED,    10,   40, 230, 130),
            ('blood_oxygen',     '🫁 血氧',  vitals.get('blood_oxygen', '--'), '%',    C_BLUE,  245,   40, 465, 130),
            ('temperature',      '🌡 体温',  vitals.get('temperature', '--'),  '°C',   C_YELLOW, 10,  138, 230, 215),
            ('blood_pressure_sys','💉 血压',
             f"{vitals.get('blood_pressure_sys','--')}/{vitals.get('blood_pressure_dia','--')}",
             'mmHg', C_GREEN, 245, 138, 465, 215),
        ]

        for key, label, val, unit, color, x1, y1, x2, y2 in cards:
            alert = self._is_alert(key, val if '/' not in str(val) else vitals.get(key))
            bg = C_RED if (alert and self._blink) else C_CARD
            self._rect(x1, y1, x2, y2, fill=bg, outline=C_RED if alert else C_BORDER)
            self._text(x1 + 8, y1 + 6, label, font=self.font_tiny, fill=C_DIM)
            self._centered_text((x1 + x2) // 2, y1 + 22,
                                str(val), font=self.font_xl, fill=color)
            self._text(x2 - 8 - len(unit) * 7, y2 - 20, unit,
                       font=self.font_tiny, fill=C_DIM)

        # ── 睡姿 + 受压风险 ──
        posture_map = {
            'supine': '仰卧', 'left': '左侧卧', 'right': '右侧卧',
            'prone': '俯卧', 'sitting': '坐起', 'empty': '床空'
        }
        posture_raw = vitals.get('sleep_posture', '--')
        posture_str = posture_map.get(posture_raw, posture_raw)

        ulcer     = analysis.get('ulcer_risk', {}) or {}
        risk_lv   = ulcer.get('level', 'none')
        risk_cfg  = {'none': (C_GREEN, '● 无风险'),
                     'low':  (C_YELLOW, '● 低风险'),
                     'medium': (C_ORANGE, '● 中风险'),
                     'high': (C_RED, '● 高风险 ⚠')}
        risk_color, risk_label = risk_cfg.get(risk_lv, (C_DIM, '未知'))

        self._rect(10, 222, 230, 278, fill=C_CARD, outline=C_BORDER)
        self._text(18, 228, "🛌 姿态", font=self.font_tiny, fill=C_DIM)
        self._centered_text(120, 242, posture_str, font=self.font_medium, fill=C_TEXT)

        self._rect(245, 222, 465, 278, fill=C_CARD, outline=C_BORDER)
        self._text(253, 228, "受压风险", font=self.font_tiny, fill=C_DIM)
        self._centered_text(355, 242, risk_label, font=self.font_medium, fill=risk_color)

    # ══════════════════════════════════════════
    #  Page 1：快捷操作
    # ══════════════════════════════════════════

    def _render_page1(self, data):
        for (label, x1, y1, x2, y2, _key) in PAGE1_BUTTONS:
            is_nurse = (_key == 'call_nurse')
            bg      = '#3a0a0a' if is_nurse else C_CARD
            outline = C_RED    if is_nurse else C_BORDER
            fg      = C_RED    if is_nurse else C_TEXT
            font    = self.font_large if is_nurse else self.font_medium
            self._rect(x1, y1, x2, y2, fill=bg, outline=outline, radius=10)
            self._centered_text((x1 + x2) // 2, y1 + (y2 - y1) // 2 - 14,
                                label, font=font, fill=fg)

        # 翻身次数提示
        changes = (data.get('analysis') or {}).get('change_stats', {}) or {}
        turns   = changes.get('total_changes', 0)
        self._text(10, 42, f"今日翻身：{turns} 次",
                   font=self.font_small, fill=C_DIM)

    # ══════════════════════════════════════════
    #  Page 2：系统状态
    # ══════════════════════════════════════════

    def _render_page2(self, data):
        nav      = data.get('nav', {}) or {}
        vitals   = data.get('vitals', {}) or {}
        analysis = data.get('analysis', {}) or {}

        rows = [
            ("🧭 导航模式",  nav.get('mode', '--')),
            ("🚦 导航状态",  nav.get('state', '--')),
            ("📡 前方障碍",  f"{(nav.get('distances') or {}).get('front', '--')} cm"),
            ("🌡 传感源",    vitals.get('posture_source', '--')),
            ("🧠 AI置信",    f"{(analysis.get('posture') or {}).get('confidence', 0):.0%}"
                              if analysis.get('posture') else "--"),
            ("⏱ 时间",       time.strftime("%Y-%m-%d %H:%M")),
        ]

        y = 42
        for label, val in rows:
            self._rect(10, y, 460, y + 34, fill=C_CARD, outline=C_BORDER, radius=6)
            self._text(18, y + 8, label, font=self.font_small, fill=C_DIM)
            self._text(200, y + 8, str(val), font=self.font_small, fill=C_TEXT)
            y += 38

    # ══════════════════════════════════════════
    #  主渲染循环
    # ══════════════════════════════════════════

    def _render_frame(self):
        if not self.draw:
            return

        data    = self._get_data()
        battery = data.get('battery', {}) or {}

        # 闪烁时钟（约 0.5Hz）
        self._blink = (self._frame // 2) % 2 == 0
        self._frame += 1

        # 清屏
        self.draw.rectangle([0, 0, self.width, self.height], fill=C_BG)

        # 顶栏
        self._draw_header(battery)

        # 页面内容
        if self._page == 0:
            self._render_page0(data)
        elif self._page == 1:
            self._render_page1(data)
        else:
            self._render_page2(data)

        # 底部 Tab
        self._draw_tabs()

    def _output_to_lcd(self):
        """将 Pillow 图像输出到 /dev/fb1 (RGB565)"""
        if not self.image:
            return
        try:
            with open('/dev/fb1', 'wb') as fb:
                px = self.image.convert('RGB')
                raw = bytearray()
                for y in range(self.height):
                    for x in range(self.width):
                        r, g, b = px.getpixel((x, y))
                        rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                        raw += rgb565.to_bytes(2, 'little')
                fb.write(bytes(raw))
        except FileNotFoundError:
            # 开发机上无 /dev/fb1，保存为预览 PNG
            self.image.save('/tmp/lcd_preview.png')
        except PermissionError:
            pass

    def _display_loop(self):
        while self._running:
            try:
                self._render_frame()
                self._output_to_lcd()
            except Exception as e:
                print(f"[LCD] Render error: {e}")
            # 操作页刷新更快（5fps），其他页 1fps
            time.sleep(0.2 if self._page == 1 else 1.0)

    # ══════════════════════════════════════════
    #  触摸事件线程
    # ══════════════════════════════════════════

    def _touch_loop(self):
        """读取 evdev 触摸事件，映射到操作"""
        if not self._touch_dev:
            return

        abs_info_x = self._touch_dev.absinfo(ecodes.ABS_X)
        abs_info_y = self._touch_dev.absinfo(ecodes.ABS_Y)

        raw_x, raw_y   = 0, 0
        touch_down      = False

        for event in self._touch_dev.read_loop():
            if not self._running:
                break

            if event.type == ecodes.EV_ABS:
                if event.code == ecodes.ABS_X:
                    raw_x = event.value
                elif event.code == ecodes.ABS_Y:
                    raw_y = event.value

            elif event.type == ecodes.EV_KEY:
                if event.code == ecodes.BTN_TOUCH:
                    touch_down = (event.value == 1)

            elif event.type == ecodes.EV_SYN and touch_down:
                # 归一化到屏幕坐标
                sx = int((raw_x - abs_info_x.min) /
                         max(abs_info_x.max - abs_info_x.min, 1) * self.width)
                sy = int((raw_y - abs_info_y.min) /
                         max(abs_info_y.max - abs_info_y.min, 1) * self.height)
                touch_down = False
                self._handle_touch(sx, sy)

    def _handle_touch(self, sx, sy):
        """根据触摸坐标派发操作"""
        # ── Tab 栏切换 ──
        if sy >= TAB_Y_START:
            for x1, x2, page_idx in TAB_ZONES:
                if x1 <= sx < x2:
                    if self._page != page_idx:
                        self._page = page_idx
                        print(f"[LCD] → Page {page_idx}")
                    return

        # ── Page 1 按钮 ──
        if self._page == 1:
            for (label, bx1, by1, bx2, by2, action_key) in PAGE1_BUTTONS:
                if bx1 <= sx <= bx2 and by1 <= sy <= by2:
                    print(f"[LCD] Button: {label} ({action_key})")
                    if self._action_cb:
                        try:
                            self._action_cb(action_key)
                        except Exception as e:
                            print(f"[LCD] Action callback error: {e}")
                    return

    # ══════════════════════════════════════════
    #  公开接口
    # ══════════════════════════════════════════

    def start(self, data_getter=None, action_callback=None):
        """启动显示线程 + 触摸线程"""
        if not LCD_ENABLED:
            print("[LCD] Disabled in config")
            return
        if not PIL_AVAILABLE:
            print("[LCD] Cannot start without Pillow")
            return

        if data_getter:
            self._data_getter = data_getter
        if action_callback:
            self._action_cb = action_callback

        self._running = True

        self._thread = threading.Thread(target=self._display_loop, daemon=True,
                                        name="lcd-render")
        self._thread.start()

        if EVDEV_AVAILABLE and self._touch_dev:
            self._touch_thread = threading.Thread(target=self._touch_loop, daemon=True,
                                                  name="lcd-touch")
            self._touch_thread.start()

        print("[LCD] Started (render + touch)")

    def stop(self):
        self._running = False
        print("[LCD] Stopped")

    def switch_page(self, page: int):
        """外部强制切换页面（供语音命令等调用）"""
        self._page = page % 3

    def show_message(self, text, color='#fff', duration=3):
        """在屏幕中央显示全屏消息，duration秒后恢复"""
        if not self.draw:
            return
        def _show():
            self.draw.rectangle([0, 0, self.width, self.height], fill=C_BG)
            self._centered_text(self.width // 2, self.height // 2 - 24,
                                text, font=self.font_large, fill=color)
            self._output_to_lcd()
            time.sleep(duration)
        threading.Thread(target=_show, daemon=True).start()


# ─────────────────────────────────────────────
#  呼叫护士 动作处理（供 main.py 调用）
# ─────────────────────────────────────────────

def make_call_nurse_handler(lcd_display, voice_client=None, mqtt_pub_fn=None, patient_id=1):
    """
    生成"呼叫护士"的综合处理函数。
    - 语音播报（如果 voice_client 可用）
    - MQTT 发布告警消息
    - LCD 全屏闪烁提示

    用法（在 main.py 中）:
        from lcd_display import LCDDisplay, make_call_nurse_handler
        lcd = LCDDisplay()
        handler = make_call_nurse_handler(lcd, voice_client=vc, mqtt_pub_fn=publish_command)
        lcd.start(data_getter=..., action_callback=handler)
    """
    def _handler(action_key):
        if action_key == 'call_nurse':
            print("[LCD] 🚨 呼叫护士！")

            # 1. 语音播报
            if voice_client:
                try:
                    voice_client.speak("患者需要帮助，请护士前往查看。")
                except Exception as e:
                    print(f"[LCD] Voice error: {e}")

            # 2. MQTT 告警
            if mqtt_pub_fn:
                try:
                    import json
                    mqtt_pub_fn("alert", {
                        "type": "call_nurse",
                        "patient_id": patient_id,
                        "message": "患者呼叫护士",
                        "timestamp": time.time(),
                        "level": "urgent"
                    })
                except Exception as e:
                    print(f"[LCD] MQTT error: {e}")

            # 3. LCD 全屏红色提示
            if lcd_display:
                lcd_display.show_message("🚨 呼叫护士中...", color=C_RED, duration=3)

        elif action_key == 'bed_raise':
            print("[LCD] ↑ 床头升")
            # 由外层传入的控制函数处理，此处只打印日志示例

        elif action_key == 'bed_lower':
            print("[LCD] ↓ 床头降")

        elif action_key == 'bed_stop':
            print("[LCD] ■ 停止")

    return _handler


# ─────────────────────────────────────────────
#  触摸屏驱动安装说明
# ─────────────────────────────────────────────

TOUCH_INSTALL_GUIDE = """
═══ 3.5寸触摸屏安装指南 (树莓派) ═══

1. 安装 LCD 内核驱动（以 Waveshare 3.5寸 A型 为例）:
   git clone https://github.com/waveshare/LCD-show.git
   cd LCD-show
   sudo ./LCD35-show   # 或根据型号选择对应脚本
   # 重启后 /dev/fb1 出现, 触摸设备为 /dev/input/event0

2. 安装 Python 依赖:
   sudo apt-get update
   sudo apt-get install -y python3-evdev python3-pil
   pip install evdev Pillow

3. 确认触摸设备:
   sudo evtest
   # 选择对应设备，触摸屏幕查看坐标输出

4. 赋予读取权限（无需 sudo 运行）:
   sudo usermod -aG input $(whoami)
   # 重新登录生效
"""


# ─────────────────────────────────────────────
#  独立测试入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("═══ LCD Display v2.0 Test ═══")
    print(TOUCH_INSTALL_GUIDE)

    lcd = LCDDisplay()

    import math

    def mock_data():
        t = time.time()
        return {
            "vitals": {
                "heart_rate":         72 + int(5 * math.sin(t / 3)),
                "blood_oxygen":       97,
                "temperature":        36.5,
                "blood_pressure_sys": 122,
                "blood_pressure_dia": 78,
                "sleep_posture":      "supine",
                "posture_source":     "cnn",
            },
            "battery":  {"percent": 85},
            "nav":      {"mode": "idle", "state": "stopped",
                         "distances": {"front": 45}},
            "analysis": {
                "posture":      {"posture": "supine", "confidence": 0.93, "method": "cnn"},
                "ulcer_risk":   {"level": "low"},
                "change_stats": {"total_changes": 3},
            }
        }

    def mock_action(action_key):
        print(f"[TEST] Action triggered: {action_key}")
        if action_key == 'call_nurse':
            print("[TEST] → 语音播报 + MQTT 告警（模拟）")

    lcd.start(data_getter=mock_data, action_callback=mock_action)

    print("按 Ctrl+C 退出。在开发机上预览图片: /tmp/lcd_preview.png")
    print("按数字键切换页面 (0/1/2):")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        lcd.stop()
        print("Stopped.")
