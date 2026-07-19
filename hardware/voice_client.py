#!/usr/bin/env python3
"""
智能护理病床 - 语音AI双模式客户端 v3.0 (VAD + Multi-Agent Swarm)

特性:
  - 始终监听，无需按键
  - 基于能量的 VAD (Voice Activity Detection)：检测到人声自动录音，静音自动停止
  - USB麦克风自动检测，采样率自动适配
  - ffplay 音频播放（兼容所有格式）
  - [v3.0] 可选 Coordinator Agent 路由: 陪聊模式使用 CompanionAgent 专属提示词

双模式:
  模式1 - 语音AI陪聊 (唤醒词: "护理助手", 退出词: "结束聊天")
  模式2 - 自然语言控制 NLC (唤醒词: "病床控制", 退出词: "退出控制")

用法:
  python voice_client.py --server http://your-server:3000 --patient 1
"""

import os
import sys
import wave
import time
import json
import struct
import base64
import tempfile
import argparse
import threading
import subprocess

try:
    import pyaudio
except ImportError:
    print("❌ 请安装 pyaudio: sudo apt install python3-pyaudio")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("❌ 请安装 requests: sudo apt install python3-requests")
    sys.exit(1)


# ─── Configuration ───
DEFAULT_SERVER = "http://localhost:3000"
try:
    from local_secrets import DEVICE_API_KEY   # 真实值在 local_secrets.py, 不入库
except ImportError:
    DEVICE_API_KEY = "改成你的设备密钥"
LOCAL_FLASK_URL = "http://localhost:5000"

# Audio
CHANNELS = 1
CHUNK_SIZE = 1024
FORMAT = pyaudio.paInt16

# VAD Configuration
VAD_ENERGY_THRESHOLD = 500     # 能量阈值：高于此值认为有人说话
VAD_SILENCE_TIMEOUT = 1.8      # 说完话后的静音时长(秒)，触发停止录音
VAD_MIN_SPEECH_DURATION = 0.5  # 最短有效语音(秒)
VAD_MAX_DURATION = 30          # 最长录音(秒)
VAD_PRE_SPEECH_BUFFER = 0.3   # 预缓冲(秒)：保留说话前的一小段音频

# ─── Wake / Exit Words ───
WAKE_WORD_CHAT = "护理助手"
EXIT_WORD_CHAT = "结束聊天"
WAKE_WORD_NLC = "病床控制"
EXIT_WORD_NLC = "退出控制"

# ─── SOS 急救关键词 (任何模式即时触发, 无需唤醒词, 不经LLM零延迟) ───
SOS_KEYWORDS = ["救命", "快来人", "来人啊", "叫医生", "叫护士", "急救",
                "呼吸困难", "喘不上气", "胸口疼", "胸痛", "心脏难受",
                "疼死了", "摔倒了", "帮帮我"]
SOS_COOLDOWN = 30   # 秒: 冷却期内命中不重复上报

# ─── Mode Constants ───
MODE_IDLE = "idle"
MODE_CHAT = "chat"
MODE_NLC = "nlc"

MODE_LABELS = {
    MODE_IDLE: '🔵 待机',
    MODE_CHAT: '🟢 陪聊',
    MODE_NLC:  '🟡 控制',
}


class VoiceClient:
    def __init__(self, server_url, patient_id, **kwargs):
        self.server_url = server_url.rstrip('/')
        self.patient_id = patient_id
        self.audio = pyaudio.PyAudio()
        self.mode = MODE_IDLE
        self.running = False
        self._last_sos_time = 0   # SOS冷却计时

        # v3.0: 可选 NursingCoordinator (由 main.py 注入, 用于获取 CompanionAgent 提示词)
        # 如果 coordinator 未注入, 完全走原有路径, 不影响任何功能
        self.coordinator = kwargs.get('coordinator', None)

        # Auto-detect hardware
        self.input_device_index = self._find_usb_mic()
        self.sample_rate = self._find_sample_rate()

    def _find_usb_mic(self):
        """Auto-detect USB microphone."""
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            name = info.get('name', '').lower()
            if 'usb' in name and info.get('maxInputChannels', 0) > 0:
                print(f"  🎤 USB麦克风: [{i}] {info['name']}")
                return i
        print("  ⚠️ 未找到USB麦克风，使用默认设备")
        return None

    def _find_sample_rate(self):
        """Find supported sample rate."""
        for rate in [16000, 48000, 44100]:
            try:
                ok = self.audio.is_format_supported(
                    rate, input_device=self.input_device_index,
                    input_channels=CHANNELS, input_format=FORMAT)
                if ok:
                    print(f"  🎵 采样率: {rate}Hz")
                    return rate
            except Exception:
                continue
        print("  ⚠️ 默认48000Hz")
        return 48000

    # ─────────────────────────────────────────────
    #  VAD: 基于能量的语音活动检测
    # ─────────────────────────────────────────────

    def _get_energy(self, data):
        """Calculate RMS energy of audio chunk."""
        values = struct.unpack(f'{len(data)//2}h', data)
        rms = (sum(v * v for v in values) / len(values)) ** 0.5
        return rms

    def vad_record(self):
        """
        VAD录音：始终监听，检测到人声开始录，静音自动停。
        返回 (frames, duration) 或 (None, 0)
        """
        stream = self.audio.open(
            format=FORMAT, channels=CHANNELS,
            rate=self.sample_rate, input=True,
            input_device_index=self.input_device_index,
            frames_per_buffer=CHUNK_SIZE
        )

        # 预缓冲环形队列
        pre_buffer_chunks = int(VAD_PRE_SPEECH_BUFFER * self.sample_rate / CHUNK_SIZE)
        pre_buffer = []

        print(f"\n  {MODE_LABELS.get(self.mode, '?')} 正在监听... ", end='', flush=True)

        # Phase 1: 等待语音开始
        speech_started = False
        frames = []

        while self.running:
            try:
                data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            except Exception:
                break

            energy = self._get_energy(data)

            if not speech_started:
                # 维护预缓冲
                pre_buffer.append(data)
                if len(pre_buffer) > pre_buffer_chunks:
                    pre_buffer.pop(0)

                if energy > VAD_ENERGY_THRESHOLD:
                    speech_started = True
                    frames = list(pre_buffer)  # 包含说话前的一小段
                    frames.append(data)
                    silence_start = None
                    print("🎤 录音中", end='', flush=True)
            else:
                # Phase 2: 录音中，检测静音结束
                frames.append(data)

                if energy < VAD_ENERGY_THRESHOLD:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > VAD_SILENCE_TIMEOUT:
                        print(" ✓")
                        break
                else:
                    silence_start = None
                    # 简单的音量指示
                    level = min(int(energy / 500), 5)
                    print('▊' * level, end='', flush=True)

                # 超时保护
                duration = len(frames) * CHUNK_SIZE / self.sample_rate
                if duration > VAD_MAX_DURATION:
                    print(" (超时)")
                    break

        stream.stop_stream()
        stream.close()

        if not frames:
            return None, 0

        duration = len(frames) * CHUNK_SIZE / self.sample_rate
        if duration < VAD_MIN_SPEECH_DURATION:
            return None, 0

        print(f"  📏 录音 {duration:.1f}s")
        return frames, duration

    def save_wav(self, frames):
        """Save frames to WAV file."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        wf = wave.open(temp_file.name, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(self.audio.get_sample_size(FORMAT))
        wf.setframerate(self.sample_rate)
        wf.writeframes(b''.join(frames))
        wf.close()
        return temp_file.name

    # ─────────────────────────────────────────────
    #  Audio Playback (ffplay)
    # ─────────────────────────────────────────────

    def play_audio(self, audio_base64):
        """Play base64-encoded audio via ffplay."""
        if not audio_base64:
            return

        try:
            audio_data = base64.b64decode(audio_base64)
            if len(audio_data) < 100:
                print("  ⚠️ 音频数据太短，跳过播放")
                return

            tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            tmp.write(audio_data)
            tmp.close()

            print(f"  🔊 播放回复 ({len(audio_data)//1024}KB)")

            if sys.platform == 'linux':
                # ffplay 最可靠
                ret = os.system(f'ffplay -nodisp -autoexit -loglevel quiet "{tmp.name}" 2>/dev/null')
                if ret != 0:
                    # fallback: ffmpeg 转 wav 再 aplay
                    wav = tmp.name.replace('.mp3', '.wav')
                    os.system(f'ffmpeg -y -i "{tmp.name}" -ar 48000 "{wav}" 2>/dev/null && aplay -D plughw:2,0 "{wav}" 2>/dev/null')
                    try: os.unlink(wav)
                    except: pass
            elif sys.platform == 'win32':
                os.system(f'start /wait "" "{tmp.name}"')

            try: os.unlink(tmp.name)
            except: pass

        except Exception as e:
            print(f"  ⚠️ 播放错误: {e}")

    # ─────────────────────────────────────────────
    #  Network: ASR + Chat + NLC
    # ─────────────────────────────────────────────

    def upload_chat(self, wav_path, asr_only=False):
        """Upload audio for ASR + AI chat."""
        url = f"{self.server_url}/api/voice/device/chat"
        try:
            with open(wav_path, 'rb') as f:
                files = {'audio': ('recording.wav', f, 'audio/wav')}
                data = {'patient_id': str(self.patient_id)}
                if asr_only:
                    data['asr_only'] = '1'
                headers = {'X-Device-Key': DEVICE_API_KEY}
                response = requests.post(url, files=files, data=data,
                                         headers=headers, timeout=60)
            if response.status_code != 200:
                print(f"  ❌ 服务器错误 ({response.status_code})")
                return None
            return response.json()
        except requests.exceptions.ConnectionError:
            print(f"  ❌ 无法连接 {self.server_url}")
            return None
        except requests.exceptions.Timeout:
            print("  ❌ 请求超时")
            return None
        except Exception as e:
            print(f"  ❌ 请求失败: {e}")
            return None

    def upload_command(self, wav_path):
        """Upload audio for NLC command parsing."""
        url = f"{self.server_url}/api/voice/device/command"
        try:
            with open(wav_path, 'rb') as f:
                files = {'audio': ('recording.wav', f, 'audio/wav')}
                data = {'patient_id': str(self.patient_id)}
                headers = {'X-Device-Key': DEVICE_API_KEY}
                response = requests.post(url, files=files, data=data,
                                         headers=headers, timeout=60)
            if response.status_code != 200:
                print(f"  ❌ 服务器错误 ({response.status_code})")
                return None
            return response.json()
        except Exception as e:
            print(f"  ❌ 请求失败: {e}")
            return None

    def execute_hardware_action(self, action, params=None):
        """Execute hardware action via local Flask."""
        if action == 'none':
            return
        try:
            payload = {'action': action}
            if action == 'nav_rfid' and params and params.get('room'):
                payload['room'] = params['room']
            resp = requests.post(f"{LOCAL_FLASK_URL}/api/cmd", json=payload, timeout=5)
            if resp.status_code == 200:
                print(f"  ⚡ 执行: {action}")
        except Exception as e:
            print(f"  ⚠️ 硬件: {e}")

    # ─────────────────────────────────────────────
    #  Streaming Chat (WebSocket)
    # ─────────────────────────────────────────────

    def stream_chat(self, wav_path):
        """Stream audio via WebSocket for real-time ASR→LLM→TTS pipeline.
        Returns recognized text (str) or None on error."""
        try:
            import websocket as ws_lib
        except ImportError:
            print("  ⚠️ websocket-client 未安装, 回退到 HTTP 模式")
            result = self.upload_chat(wav_path)
            if not result:
                return None
            if result.get('text_in'):
                print(f"  👤 \"{result['text_in']}\"")
            if result.get('text_out'):
                print(f"  🤖 \"{result['text_out']}\"")
            self.play_audio(result.get('audio_base64'))
            return result.get('text_in', '')

        ws_url = self.server_url.replace('http://', 'ws://').replace('https://', 'wss://')
        ws_url += '/ws/voice-stream'

        recognized_text = ''
        llm_text = ''
        audio_chunks = []
        done_event = threading.Event()
        error_occurred = [False]

        # WebSocket 连接
        try:
            ws = ws_lib.create_connection(ws_url, timeout=60)
        except Exception as e:
            print(f"  ❌ WebSocket 连接失败: {e}")
            # 回退到 HTTP
            result = self.upload_chat(wav_path)
            if not result:
                return None
            self.play_audio(result.get('audio_base64'))
            return result.get('text_in', '')

        # 发送配置
        ws.send(json.dumps({
            "type": "config",
            "patient_id": self.patient_id,
            "sample_rate": self.sample_rate
        }))

        # 接收线程
        def recv_loop():
            nonlocal recognized_text, llm_text
            audio_file = None
            playing = False

            while not done_event.is_set():
                try:
                    data = ws.recv()
                    if not data:
                        break

                    if isinstance(data, bytes):
                        # TTS 音频二进制帧
                        audio_chunks.append(data)
                        # 累积到一定量后播放
                        total = sum(len(c) for c in audio_chunks)
                        if total > 8000 and not playing:
                            playing = True
                            # 先播放已收到的部分
                            self._play_audio_chunks(list(audio_chunks))
                            audio_chunks.clear()
                    else:
                        msg = json.loads(data)
                        msg_type = msg.get('type', '')

                        if msg_type == 'ready':
                            pass
                        elif msg_type == 'asr':
                            recognized_text = msg.get('text', '')
                            if recognized_text:
                                print(f"  👤 \"{recognized_text}\"")
                        elif msg_type == 'llm_text':
                            sentence = msg.get('text', '')
                            llm_text += sentence
                        elif msg_type == 'done':
                            # 播放剩余音频
                            if audio_chunks:
                                self._play_audio_chunks(list(audio_chunks))
                                audio_chunks.clear()
                            if llm_text:
                                print(f"  🤖 \"{llm_text}\"")
                            done_event.set()
                            break
                        elif msg_type == 'error':
                            print(f"  ❌ 服务端错误: {msg.get('message', '')}")
                            error_occurred[0] = True
                            done_event.set()
                            break
                except Exception as e:
                    if not done_event.is_set():
                        print(f"  ⚠️ 接收错误: {e}")
                    break

        recv_thread = threading.Thread(target=recv_loop, daemon=True)
        recv_thread.start()

        # 读取 WAV 文件, 发送 PCM 帧
        try:
            with open(wav_path, 'rb') as f:
                wav_data = f.read()

            # 跳过 WAV 头, 提取 PCM
            if len(wav_data) > 44 and wav_data[:4] == b'RIFF':
                pcm_data = wav_data[44:]
            else:
                pcm_data = wav_data

            # 按 4096 字节分帧发送
            FRAME_SIZE = 4096
            for i in range(0, len(pcm_data), FRAME_SIZE):
                chunk = pcm_data[i:i+FRAME_SIZE]
                b64 = base64.b64encode(chunk).decode()
                ws.send(json.dumps({"type": "audio", "data": b64}))
                # 小延迟避免淹没
                time.sleep(0.01)

            # 发送结束
            ws.send(json.dumps({"type": "end"}))

        except Exception as e:
            print(f"  ❌ 发送错误: {e}")

        # 等待完成
        done_event.wait(timeout=60)

        try:
            ws.close()
        except:
            pass

        # 清理临时文件
        try:
            os.unlink(wav_path)
        except:
            pass

        if error_occurred[0]:
            return None
        return recognized_text

    def _play_audio_chunks(self, chunks):
        """播放一组二进制音频块 (mp3)"""
        if not chunks:
            return
        try:
            audio_data = b''.join(chunks)
            if len(audio_data) < 100:
                return

            tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            tmp.write(audio_data)
            tmp.close()

            if sys.platform == 'linux':
                os.system(f'ffplay -nodisp -autoexit -loglevel quiet "{tmp.name}" 2>/dev/null')
            elif sys.platform == 'win32':
                os.system(f'start /wait "" "{tmp.name}"')

            try:
                os.unlink(tmp.name)
            except:
                pass
        except Exception as e:
            print(f"  ⚠️ 播放错误: {e}")

    # ─────────────────────────────────────────────
    #  Wake / Exit word detection
    # ─────────────────────────────────────────────

    def check_wake_exit(self, text):
        """Check for mode switching keywords."""
        if not text:
            return None
        if EXIT_WORD_CHAT in text and self.mode == MODE_CHAT:
            return MODE_IDLE
        if EXIT_WORD_NLC in text and self.mode == MODE_NLC:
            return MODE_IDLE
        if WAKE_WORD_CHAT in text:
            return MODE_CHAT
        if WAKE_WORD_NLC in text:
            return MODE_NLC
        return None

    # ─────────────────────────────────────────────
    #  SOS 急救词直通告警
    # ─────────────────────────────────────────────

    def check_sos(self, text):
        """SOS检测: 本地关键词匹配, 不经LLM, 命中立即critical告警+本地语音安抚"""
        if not text:
            return False
        hit = next((kw for kw in SOS_KEYWORDS if kw in text), None)
        if not hit:
            return False
        if time.time() - self._last_sos_time < SOS_COOLDOWN:
            print(f"  🆘 SOS再次命中「{hit}」(冷却期内, 不重复上报)")
            return True
        self._last_sos_time = time.time()
        print(f"\n  ╔═══════════════════════════════════════╗")
        print(f"  ║  🆘 SOS! 急救关键词:「{hit}」")
        print(f"  ║  ⚡ 直通 critical 告警 → 护士站")
        print(f"  ╚═══════════════════════════════════════╝")
        # 异步上报, 不阻塞语音循环
        threading.Thread(target=self._send_sos_alert,
                         args=(text, hit), daemon=True).start()
        self._speak_local("已收到您的呼救，正在通知护士站，请保持冷静。")
        return True

    def _send_sos_alert(self, text, keyword):
        """直通云端告警API (设备X-API-Key认证, 无需JWT)"""
        try:
            resp = requests.post(
                f"{self.server_url}/api/alerts",
                json={
                    "patient_id": self.patient_id,
                    "alert_type": "critical",
                    "metric": "voice_sos",
                    "value": None,
                    "threshold": keyword,
                    "message": f"🆘 语音SOS呼救: 「{text.strip()[:60]}」",
                },
                headers={"X-API-Key": DEVICE_API_KEY},
                timeout=8,
            )
            print(f"  🆘 SOS告警已上报 (HTTP {resp.status_code})")
        except Exception as e:
            print(f"  ⚠️ SOS告警上报失败: {e}")

    def _speak_local(self, text):
        """零依赖本地即时语音: 预置wav(aplay) → espeak-ng → 仅打印"""
        wav = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "sounds", "sos_ack.wav")
        try:
            if os.path.exists(wav):
                subprocess.Popen(["aplay", "-q", wav])
                return
            subprocess.Popen(["espeak-ng", "-v", "cmn", "-s", "160", text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print(f"  🔈 (本地TTS不可用) {text}")

    # ─────────────────────────────────────────────
    #  Main Loop
    # ─────────────────────────────────────────────

    def process_once(self):
        """One round: VAD record → upload → process → play."""
        # VAD 录音
        frames, duration = self.vad_record()
        if frames is None:
            return

        wav_path = self.save_wav(frames)

        try:
            if self.mode == MODE_IDLE:
                # 待机：只做 ASR 检查唤醒词（asr_only 跳过 LLM+TTS，快速返回）
                result = self.upload_chat(wav_path, asr_only=True)
                if not result:
                    return

                text_in = result.get('text_in', '')
                if text_in:
                    print(f"  🔍 识别: \"{text_in}\"")

                # SOS急救词优先于一切模式逻辑
                if self.check_sos(text_in):
                    return

                mode_change = self.check_wake_exit(text_in)
                if mode_change == MODE_CHAT:
                    self.mode = MODE_CHAT
                    print(f"\n  ╔═══════════════════════════════════════╗")
                    print(f"  ║  🎤 进入【语音陪聊】模式              ║")
                    print(f"  ║  说「{EXIT_WORD_CHAT}」退出              ║")
                    print(f"  ╚═══════════════════════════════════════╝")
                    self.play_audio(result.get('audio_base64'))
                elif mode_change == MODE_NLC:
                    self.mode = MODE_NLC
                    print(f"\n  ╔═══════════════════════════════════════╗")
                    print(f"  ║  🎮 进入【语音控制】模式              ║")
                    print(f"  ║  说「{EXIT_WORD_NLC}」退出              ║")
                    print(f"  ╚═══════════════════════════════════════╝")

            elif self.mode == MODE_CHAT:
                # 陪聊模式 - 流式 WebSocket (含 HTTP 回退)
                text_in = self.stream_chat(wav_path)
                if text_in is None:
                    return

                self.check_sos(text_in)   # 陪聊中喊救命同样直通告警

                mode_change = self.check_wake_exit(text_in)

                if mode_change == MODE_IDLE:
                    self.mode = MODE_IDLE
                    print("  👋 已退出陪聊模式")
                    return
                elif mode_change == MODE_NLC:
                    self.mode = MODE_NLC
                    print("  🎮 切换到语音控制模式")
                    return

            elif self.mode == MODE_NLC:
                # 语音控制模式
                result = self.upload_command(wav_path)
                if not result:
                    return

                text_in = result.get('text_in', '')

                # SOS优先: 呼救时不执行任何硬件动作
                if self.check_sos(text_in):
                    return

                mode_change = self.check_wake_exit(text_in)

                if mode_change == MODE_IDLE:
                    self.mode = MODE_IDLE
                    print("  👋 已退出控制模式")
                    return
                elif mode_change == MODE_CHAT:
                    self.mode = MODE_CHAT
                    print("  🎤 切换到陪聊模式")
                    return

                action = result.get('action', 'none')
                reply = result.get('reply', '')
                if text_in:
                    print(f"  👤 \"{text_in}\"")
                print(f"  🎯 {action} → \"{reply}\"")

                if action != 'none':
                    self.execute_hardware_action(action, result.get('params'))
                self.play_audio(result.get('audio_base64'))

        finally:
            try: os.unlink(wav_path)
            except: pass

    def run_loop(self):
        """Alias for run() - called by main.py"""
        return self.run()

    def _stdin_listener(self):
        """键盘/管道兜底通道: 输入文本直接过SOS检测 (输入 s = 模拟喊救命)。
        麦克风故障时演示仍可触发完整SOS链路 (真实告警POST+推送)。"""
        try:
            for line in sys.stdin:
                text = line.strip()
                if not text:
                    continue
                if text.lower() == 's':
                    text = "救命"
                print(f"  ⌨️ 键盘输入: \"{text}\"")
                if not self.check_sos(text):
                    print("  (未命中SOS关键词; 键盘通道仅用于SOS演示)")
        except Exception:
            pass   # 无stdin环境(systemd后台)静默退出

    def _mic_available(self):
        """开机自检: 尝试打开一次输入流, 判断麦克风是否可用"""
        try:
            s = self.audio.open(format=FORMAT, channels=CHANNELS,
                                rate=self.sample_rate, input=True,
                                input_device_index=self.input_device_index,
                                frames_per_buffer=CHUNK_SIZE)
            s.close()
            return True
        except Exception as e:
            print(f"  ⚠️ 麦克风自检失败: {e}")
            return False

    def run(self):
        """Main loop: always listening."""
        print(f"""
  ╔══════════════════════════════════════════════╗
  ║  🏥 智能护理病床 · AI语音助手 v3.0 (Swarm)  ║
  ║  服务器: {self.server_url:<35s} ║
  ║  患者ID: {str(self.patient_id):<35s} ║
  ╠══════════════════════════════════════════════╣
  ║  🎤 说「{WAKE_WORD_CHAT}」→ 语音陪聊              ║
  ║  🎮 说「{WAKE_WORD_NLC}」→ 语音控制              ║
  ║  🆘 说「救命」等急救词 → 直通告警            ║
  ║  ⌨️  键盘输入 s + 回车 → 模拟SOS (兜底)      ║
  ║  ⏹  Ctrl+C 退出                              ║
  ╚══════════════════════════════════════════════╝
""")
        self.running = True

        # 键盘兜底通道始终开启 (演示保险)
        threading.Thread(target=self._stdin_listener, daemon=True).start()

        if not self._mic_available():
            # 麦克风故障 → 键盘演示模式, 进程不退出不刷错
            print("  ╔═══════════════════════════════════════╗")
            print("  ║  🎤 麦克风不可用 → 进入键盘演示模式   ║")
            print("  ║  输入 s+回车 触发SOS, 链路完全真实    ║")
            print("  ╚═══════════════════════════════════════╝")
            while self.running:
                try:
                    time.sleep(1)
                except KeyboardInterrupt:
                    print("\n\n  👋 语音助手已退出")
                    break
            return

        print("  🔄 始终监听中，对着麦克风说话即可...\n")
        while self.running:
            try:
                self.process_once()
            except KeyboardInterrupt:
                print("\n\n  👋 语音助手已退出，祝您早日康复！")
                break
            except Exception as e:
                print(f"  ⚠️ 异常: {e}")
                time.sleep(1)

    def cleanup(self):
        self.running = False
        self.audio.terminate()


def main():
    global DEVICE_API_KEY, LOCAL_FLASK_URL, VAD_ENERGY_THRESHOLD

    parser = argparse.ArgumentParser(description='智能护理病床 - AI语音助手 v2.0 (VAD)')
    parser.add_argument('--server', '-s', default=DEFAULT_SERVER,
                        help=f'云端服务器地址 (默认: {DEFAULT_SERVER})')
    parser.add_argument('--patient', '-p', type=int, required=True,
                        help='患者ID')
    parser.add_argument('--key', '-k', default=DEVICE_API_KEY,
                        help='设备API密钥')
    parser.add_argument('--local', default=LOCAL_FLASK_URL,
                        help='本地Flask地址')
    parser.add_argument('--threshold', '-t', type=int, default=VAD_ENERGY_THRESHOLD,
                        help=f'VAD能量阈值 (默认: {VAD_ENERGY_THRESHOLD}, 越小越灵敏)')
    parser.add_argument('--test-sos', action='store_true',
                        help='启动后立即模拟一次SOS呼救 (验证告警链路, 无需麦克风)')

    args = parser.parse_args()

    DEVICE_API_KEY = args.key
    LOCAL_FLASK_URL = args.local
    VAD_ENERGY_THRESHOLD = args.threshold

    client = VoiceClient(args.server, args.patient)

    if args.test_sos:
        print("\n  🧪 --test-sos: 模拟SOS呼救...")
        client.check_sos("救命")

    try:
        client.run()
    finally:
        client.cleanup()


if __name__ == '__main__':
    main()
