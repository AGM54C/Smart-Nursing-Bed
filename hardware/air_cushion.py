#!/usr/bin/env python3
"""
智能护理病床 - 气囊减压控制模块

创新点: 检测到受压风险后, 自动充放气改变压力分布,
       实现 感知→预测→执行→验证 的闭环自动减压。

硬件:
  - 5V小气泵 (继电器控制, 1路GPIO)
  - 电磁阀×2 (左/右分区控制, 各1路GPIO)
  - 气囊区域: 左侧/右侧 (铺设在床垫下)

工作原理:
  充气: 气泵ON + 目标区域阀ON → 气囊膨胀 → 抬高对侧身体 → 改变受压分布
  放气: 气泵OFF + 目标区域阀ON → 自然排气
  减压循环: 左充右放 → 等待 → 右充左放 → 恢复 (模拟翻身效果)
"""

import time
import threading
import logging

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[AirCushion] %(message)s')

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

from config import (
    AIR_PUMP_PIN, AIR_VALVE_LEFT, AIR_VALVE_RIGHT,
    AIR_MAX_INFLATE_TIME, AIR_CYCLE_INTERVAL,
    AIR_INFLATE_DURATION, AIR_DEFLATE_DURATION,
    PWM_FREQ
)


class MockGPIO:
    """开发环境 GPIO 模拟"""
    BCM = 11
    OUT = 0
    HIGH = 1
    LOW = 0

    def setmode(self, m): pass
    def setup(self, p, m): pass
    def output(self, p, v):
        log.info("  [MockGPIO] Pin %s → %s", p, "HIGH" if v else "LOW")
    def cleanup(self): pass


class AirCushionController:
    """
    气囊减压控制器

    支持:
      - 单区充气/放气 (左/右)
      - 自动减压循环 (交替充放气, 模拟翻身效果)
      - 安全限制 (最大充气时间, 冷却间隔)
      - 闭环验证 (执行后可由压力矩阵验证效果)
    """

    ZONES = {"left": "AIR_VALVE_LEFT", "right": "AIR_VALVE_RIGHT"}

    def __init__(self):
        self._gpio = GPIO if GPIO_AVAILABLE else MockGPIO()
        self._gpio.setmode(self._gpio.BCM)

        # 初始化引脚
        self._pump_pin = AIR_PUMP_PIN
        self._valve_pins = {
            "left": AIR_VALVE_LEFT,
            "right": AIR_VALVE_RIGHT,
        }

        self._gpio.setup(self._pump_pin, self._gpio.OUT)
        for pin in self._valve_pins.values():
            self._gpio.setup(pin, self._gpio.OUT)

        # 确保初始状态: 全部关闭
        self._pump_off()
        self._all_valves_off()

        # 状态
        self._state = "idle"  # idle / inflating / deflating / cycling
        self._lock = threading.Lock()
        self._timer = None
        self._last_cycle_time = 0
        self._cycle_count = 0
        self._action_log = []

        log.info("✅ AirCushionController initialized (pump=%d, valveL=%d, valveR=%d)",
                 self._pump_pin, self._valve_pins["left"], self._valve_pins["right"])

    # ═══════════════════════════════════════
    #  基础操作
    # ═══════════════════════════════════════

    def inflate(self, zone="both", duration=None):
        """
        充气指定区域

        zone: "left" / "right" / "both"
        duration: 充气时长(秒), 受 AIR_MAX_INFLATE_TIME 上限约束
        """
        if duration is None:
            duration = AIR_INFLATE_DURATION
        # 安全上限
        duration = min(duration, AIR_MAX_INFLATE_TIME)

        with self._lock:
            self._state = "inflating"

        log.info("🫧 Inflate zone=%s, duration=%.1fs", zone, duration)
        self._open_valves(zone)
        self._pump_on()

        # 定时停止
        self._cancel_timer()
        self._timer = threading.Timer(duration, self._auto_stop)
        self._timer.start()

        self._log_action("inflate", zone, duration)

    def deflate(self, zone="both", duration=None):
        """
        放气指定区域 (气泵关闭, 阀门开启, 自然排气)
        """
        if duration is None:
            duration = AIR_DEFLATE_DURATION

        with self._lock:
            self._state = "deflating"

        log.info("💨 Deflate zone=%s, duration=%.1fs", zone, duration)
        self._pump_off()
        self._open_valves(zone)

        self._cancel_timer()
        self._timer = threading.Timer(duration, self._auto_stop)
        self._timer.start()

        self._log_action("deflate", zone, duration)

    def stop(self):
        """立即停止所有操作"""
        self._pump_off()
        self._all_valves_off()
        self._cancel_timer()
        with self._lock:
            self._state = "idle"
        log.info("⏹️ Stopped")

    # ═══════════════════════════════════════
    #  自动减压循环 (核心创新)
    # ═══════════════════════════════════════

    def pressure_relief_cycle(self):
        """
        自动减压循环: 交替充放气改变压力分布

        流程:
          1. 左侧充气 5s (抬高左侧, 减轻右侧压力)
          2. 等待 3s
          3. 左侧放气 3s + 右侧充气 5s
          4. 等待 3s
          5. 右侧放气 3s → 恢复原状

        总时长约 22s, 模拟一次温和的体位调整
        """
        # 冷却检查
        now = time.time()
        if now - self._last_cycle_time < AIR_CYCLE_INTERVAL:
            remaining = int(AIR_CYCLE_INTERVAL - (now - self._last_cycle_time))
            log.info("⏳ Cycle cooldown, %ds remaining", remaining)
            return False

        with self._lock:
            if self._state != "idle":
                log.info("⚠️ Already running (%s), skip cycle", self._state)
                return False
            self._state = "cycling"

        self._last_cycle_time = now
        self._cycle_count += 1

        log.info("🔄 Starting pressure relief cycle #%d", self._cycle_count)

        # 在后台线程执行循环 (避免阻塞主线程)
        thread = threading.Thread(target=self._run_cycle, daemon=True)
        thread.start()

        self._log_action("relief_cycle", "both", 22)
        return True

    def _run_cycle(self):
        """执行减压循环 (后台线程)"""
        try:
            # Phase 1: 左侧充气
            log.info("  Phase 1/4: Inflate LEFT")
            self._open_valves("left")
            self._pump_on()
            time.sleep(AIR_INFLATE_DURATION)
            self._pump_off()

            # 等待
            time.sleep(3)

            # Phase 2: 左侧放气
            log.info("  Phase 2/4: Deflate LEFT")
            self._all_valves_off()
            self._open_valves("left")
            time.sleep(AIR_DEFLATE_DURATION)
            self._all_valves_off()

            # Phase 3: 右侧充气
            log.info("  Phase 3/4: Inflate RIGHT")
            self._open_valves("right")
            self._pump_on()
            time.sleep(AIR_INFLATE_DURATION)
            self._pump_off()

            # 等待
            time.sleep(3)

            # Phase 4: 右侧放气, 恢复
            log.info("  Phase 4/4: Deflate RIGHT (restore)")
            self._all_valves_off()
            self._open_valves("right")
            time.sleep(AIR_DEFLATE_DURATION)

        except Exception as e:
            log.error("Cycle error: %s", e)
        finally:
            self._pump_off()
            self._all_valves_off()
            with self._lock:
                self._state = "idle"
            log.info("🔄 Relief cycle #%d complete", self._cycle_count)

    # ═══════════════════════════════════════
    #  内部方法
    # ═══════════════════════════════════════

    def _pump_on(self):
        self._gpio.output(self._pump_pin, self._gpio.HIGH)

    def _pump_off(self):
        self._gpio.output(self._pump_pin, self._gpio.LOW)

    def _open_valves(self, zone):
        if zone == "left" or zone == "both":
            self._gpio.output(self._valve_pins["left"], self._gpio.HIGH)
        if zone == "right" or zone == "both":
            self._gpio.output(self._valve_pins["right"], self._gpio.HIGH)

    def _all_valves_off(self):
        for pin in self._valve_pins.values():
            self._gpio.output(pin, self._gpio.LOW)

    def _auto_stop(self):
        self._pump_off()
        self._all_valves_off()
        with self._lock:
            self._state = "idle"
        log.info("⏹️ Auto-stopped")

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _log_action(self, action, zone, duration):
        self._action_log.append({
            "action": action,
            "zone": zone,
            "duration": duration,
            "time": time.strftime("%H:%M:%S"),
            "cycle": self._cycle_count
        })
        # 保留最近 50 条
        self._action_log = self._action_log[-50:]

    # ═══════════════════════════════════════
    #  状态查询
    # ═══════════════════════════════════════

    def get_state(self):
        with self._lock:
            return self._state

    def get_status(self):
        return {
            "state": self.get_state(),
            "cycle_count": self._cycle_count,
            "last_cycle": self._last_cycle_time,
            "cooldown_remaining": max(0, int(
                AIR_CYCLE_INTERVAL - (time.time() - self._last_cycle_time)
            )),
            "recent_actions": self._action_log[-5:]
        }

    def cleanup(self):
        self.stop()
        log.info("Cleanup done")


# ═══════════════════════════════════════
#  CLI 测试
# ═══════════════════════════════════════

if __name__ == "__main__":
    import sys

    controller = AirCushionController()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "inflate":
            zone = sys.argv[2] if len(sys.argv) > 2 else "both"
            controller.inflate(zone=zone)
            time.sleep(6)
        elif cmd == "deflate":
            zone = sys.argv[2] if len(sys.argv) > 2 else "both"
            controller.deflate(zone=zone)
            time.sleep(4)
        elif cmd == "cycle":
            controller.pressure_relief_cycle()
            time.sleep(25)  # 等待循环完成
        elif cmd == "stop":
            controller.stop()
        else:
            print("未知命令:", cmd)
    else:
        print("用法:")
        print("  python3 air_cushion.py inflate [left|right|both]")
        print("  python3 air_cushion.py deflate [left|right|both]")
        print("  python3 air_cushion.py cycle    # 自动减压循环")
        print("  python3 air_cushion.py stop")

    print(f"\n状态: {controller.get_status()}")
    controller.cleanup()
