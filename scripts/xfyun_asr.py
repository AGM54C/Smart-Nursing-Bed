#!/usr/bin/env python3
"""
讯飞实时语音转写大模型 ASR - Node.js 桥接脚本
用法: python3 xfyun_asr.py <wav_file_path>
输出: 识别结果文本到 stdout
基于讯飞官方 Python demo 改写
"""
import sys
import os
import hashlib
import hmac
import base64
import json
import time
import struct
import threading
import urllib.parse
import uuid
import datetime

try:
    from websocket import create_connection
except ImportError:
    print("", end="")  # 输出空字符串
    sys.exit(0)

# 从环境变量读取密钥
APP_ID = os.environ.get('XFYUN_APP_ID', '')
API_KEY = os.environ.get('XFYUN_API_KEY', '')
API_SECRET = os.environ.get('XFYUN_API_SECRET', '')

WS_URL = "wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1"
FRAME_SIZE = 1280
FRAME_INTERVAL = 0.04  # 40ms


def read_wav_as_pcm16k(filepath):
    """读取 WAV 文件, 提取 PCM 数据并降采样到 16kHz"""
    with open(filepath, 'rb') as f:
        data = f.read()

    # 检查是否是 WAV 文件
    if len(data) > 44 and data[:4] == b'RIFF':
        sample_rate = struct.unpack_from('<I', data, 24)[0]
        num_channels = struct.unpack_from('<H', data, 22)[0]
        bits_per_sample = struct.unpack_from('<H', data, 34)[0]

        # 找到 data chunk
        data_offset = 44
        for i in range(36, min(len(data) - 8, 200)):
            if data[i:i+4] == b'data':
                data_offset = i + 8
                break

        pcm = data[data_offset:]

        # 转为单声道
        if num_channels > 1:
            import array
            samples = array.array('h')
            frame_bytes = (bits_per_sample // 8) * num_channels
            for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes):
                samples.append(struct.unpack_from('<h', pcm, i)[0])
            pcm = struct.pack(f'<{len(samples)}h', *samples)

        # 降采样到 16kHz
        if sample_rate != 16000 and sample_rate > 16000:
            import array
            ratio = sample_rate / 16000
            src_samples = struct.unpack(f'<{len(pcm)//2}h', pcm)
            dst_count = int(len(src_samples) / ratio)
            dst_samples = []
            for i in range(dst_count):
                src_idx = int(i * ratio)
                dst_samples.append(src_samples[src_idx])
            pcm = struct.pack(f'<{len(dst_samples)}h', *dst_samples)
            sys.stderr.write(f"[ASR] Resampled: {sample_rate}Hz -> 16000Hz ({len(data)} -> {len(pcm)} bytes)\n")

        return pcm
    else:
        # 假设是裸 PCM 16kHz
        return data


def generate_auth_url():
    """生成鉴权 WebSocket URL"""
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(beijing_tz)
    utc_str = now.strftime("%Y-%m-%dT%H:%M:%S%z")

    raw_params = {
        "accessKeyId": API_KEY,
        "appId": APP_ID,
        "audio_encode": "pcm_s16le",
        "lang": "autodialect",
        "samplerate": "16000",
        "utc": utc_str,
        "uuid": uuid.uuid4().hex
    }

    # 签名: 排序 → URL编码 → 拼接 → HmacSHA1(apiSecret)
    sorted_params = dict(sorted(raw_params.items()))
    base_str = "&".join([
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted_params.items()
    ])

    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        base_str.encode("utf-8"),
        hashlib.sha1
    ).digest()
    raw_params["signature"] = base64.b64encode(signature).decode("utf-8")

    params_str = urllib.parse.urlencode(raw_params)
    return f"{WS_URL}?{params_str}"


def transcribe(audio_path):
    """执行语音转写, 返回识别文本"""
    pcm_data = read_wav_as_pcm16k(audio_path)
    if not pcm_data or len(pcm_data) < 100:
        return ""

    ws_url = generate_auth_url()
    full_text = ""
    session_id = None

    try:
        ws = create_connection(ws_url, timeout=15)
        sys.stderr.write(f"[ASR] Connected, sending {len(pcm_data)} bytes PCM\n")

        # 启动接收线程
        recv_done = threading.Event()

        def recv_thread():
            nonlocal full_text, session_id
            while not recv_done.is_set():
                try:
                    msg = ws.recv()
                    if not msg:
                        break
                    if isinstance(msg, str):
                        msg_json = json.loads(msg)
                        sys.stderr.write(f"[ASR] recv: {json.dumps(msg_json, ensure_ascii=False)[:200]}\n")

                        # 提取 sessionId
                        if msg_json.get('msg_type') == 'action' and 'sessionId' in msg_json.get('data', {}):
                            session_id = msg_json['data']['sessionId']

                        # 提取识别结果
                        if msg_json.get('msg_type') == 'result' and msg_json.get('res_type') == 'asr':
                            d = msg_json.get('data', {})
                            cn = d.get('cn', {})
                            st = cn.get('st', {})
                            if st.get('type') == '0':  # 最终结果
                                for rt in st.get('rt', []):
                                    for ws_item in rt.get('ws', []):
                                        for cw in ws_item.get('cw', []):
                                            full_text += cw.get('w', '')
                except Exception as e:
                    sys.stderr.write(f"[ASR] recv error: {e}\n")
                    break

        t = threading.Thread(target=recv_thread, daemon=True)
        t.start()

        # 发送音频帧
        offset = 0
        start_time = time.time()
        frame_idx = 0
        while offset < len(pcm_data):
            end = min(offset + FRAME_SIZE, len(pcm_data))
            ws.send_binary(pcm_data[offset:end])
            offset = end
            frame_idx += 1

            # 精确控制发送节奏
            expected_time = start_time + frame_idx * FRAME_INTERVAL
            sleep_time = expected_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)

        # 发送结束标识
        end_msg = {"end": True}
        if session_id:
            end_msg["sessionId"] = session_id
        ws.send(json.dumps(end_msg))
        sys.stderr.write(f"[ASR] All frames sent, waiting for results...\n")

        # 等待结果 (最多10秒)
        t.join(timeout=10)
        recv_done.set()

        try:
            ws.close()
        except:
            pass

    except Exception as e:
        sys.stderr.write(f"[ASR] Error: {e}\n")

    return full_text


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python3 xfyun_asr.py <wav_file>\n")
        sys.exit(1)

    audio_file = sys.argv[1]
    if not os.path.exists(audio_file):
        sys.stderr.write(f"File not found: {audio_file}\n")
        print("")
        sys.exit(1)

    result = transcribe(audio_file)
    # 只输出纯文本到 stdout (Node.js 读取这个)
    print(result, end="")
