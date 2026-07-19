#!/usr/bin/env python3
"""
智能护理病床 - RC522 RFID读卡器

读取13.56MHz RFID卡/标签, 用于识别病房

双保险定位体系:
  - NearLink (Hi3863 SLE): 连续测距, 提供实时距离感知和减速控制
  - RFID (RC522):          病房门口物理标签, 提供到达的二次确认
  两者任一触发即判定到达, 双重命中为最高置信度
"""

import time
import threading

try:
    from mfrc522 import SimpleMFRC522
    import RPi.GPIO as GPIO
except ImportError:
    print("[RFID] ⚠️ mfrc522 not available, using mock mode")
    SimpleMFRC522 = None

from config import *


class RFIDReader:
    """RC522 RFID 读卡器"""

    def __init__(self):
        self._reader = None
        self._last_id = None
        self._last_text = None
        self._running = False
        self._lock = threading.Lock()
        self._callback = None

        if SimpleMFRC522:
            try:
                self._reader = SimpleMFRC522()
                print("[RFID] RC522 Initialized (SPI0)")
            except Exception as e:
                print(f"[RFID] Init failed: {e}")
        else:
            print("[RFID] Mock mode (no hardware)")

    def read_card(self, timeout=2.0):
        """
        尝试读取RFID卡
        返回: (id, text) 或 (None, None)
        """
        if not self._reader:
            return None, None

        try:
            # SimpleMFRC522.read() 是阻塞的
            # 用线程+超时实现非阻塞读取
            result = [None, None]

            def _do_read():
                try:
                    id, text = self._reader.read_no_block()
                    if id:
                        result[0] = id
                        result[1] = text.strip() if text else ""
                except Exception:
                    pass

            t = threading.Thread(target=_do_read, daemon=True)
            t.start()
            t.join(timeout=timeout)

            if result[0]:
                with self._lock:
                    self._last_id = result[0]
                    self._last_text = result[1]
                return result[0], result[1]

        except Exception as e:
            print(f"[RFID] Read error: {e}")

        return None, None

    def read_card_simple(self):
        """
        简单读取 (阻塞直到读到卡)
        适用于写卡准备阶段
        """
        if not self._reader:
            return None, None

        try:
            id, text = self._reader.read()
            return id, text.strip() if text else ""
        except Exception as e:
            print(f"[RFID] Read error: {e}")
            return None, None

    def write_card(self, text):
        """
        写数据到RFID卡
        用于准备病房标签: write_card("302")
        """
        if not self._reader:
            print("[RFID] No reader available")
            return False

        try:
            print(f"[RFID] Place card on reader to write: '{text}'")
            self._reader.write(text)
            print(f"[RFID] Written successfully: '{text}'")
            return True
        except Exception as e:
            print(f"[RFID] Write error: {e}")
            return False

    def get_last_read(self):
        """获取上次读取结果"""
        with self._lock:
            return self._last_id, self._last_text

    def check_room(self, target_room):
        """
        检查当前RFID是否匹配目标病房
        返回: True/False/None(未检测到卡)
        """
        _, text = self.read_card(timeout=0.5)
        if text is None:
            return None

        match = text == str(target_room)
        if match:
            print(f"[RFID] ✅ Room {target_room} MATCHED!")
        return match

    # ─── 后台持续扫描 ───

    def start_continuous(self, callback=None, interval=0.5):
        """
        启动后台持续扫描
        callback(id, text) 在读到卡时调用
        """
        self._running = True
        self._callback = callback

        def _scan_loop():
            while self._running:
                id, text = self.read_card(timeout=0.3)
                if id and self._callback:
                    self._callback(id, text)
                time.sleep(interval)

        t = threading.Thread(target=_scan_loop, daemon=True)
        t.start()
        print(f"[RFID] Continuous scanning started ({interval}s interval)")

    def stop_continuous(self):
        self._running = False

    def cleanup(self):
        self.stop_continuous()


# ─── 工具函数 ───

def prepare_room_cards():
    """
    交互式准备病房RFID卡
    在Demo前运行，逐张写入病房号
    """
    reader = RFIDReader()
    rooms = ["301", "302", "303"]

    for room in rooms:
        input(f"\n放置病房 {room} 的RFID白卡, 然后按Enter...")
        if reader.write_card(room):
            print(f"  ✅ 病房 {room} 写入成功")
        else:
            print(f"  ❌ 病房 {room} 写入失败")

    reader.cleanup()
    print("\n所有病房卡准备完成!")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "write":
        prepare_room_cards()
    else:
        print("═══ RFID 读卡测试 ═══")
        reader = RFIDReader()
        print("请将RFID卡靠近读卡器...")
        try:
            while True:
                id, text = reader.read_card(timeout=1.0)
                if id:
                    print(f"  📇 ID={id}, Text='{text}'")
                time.sleep(0.5)
        except KeyboardInterrupt:
            reader.cleanup()
