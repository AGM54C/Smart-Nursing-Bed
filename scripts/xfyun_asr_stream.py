#!/usr/bin/env python3
"""
讯飞 ASR 流式桥接 - stdin 接收 PCM 音频帧, stdout 输出识别文本
协议:
  stdin:  4字节长度(little-endian) + PCM数据 (循环) | "END\n" 结束
  stdout: 每次识别出最终结果输出一行 JSON: {"text":"xxx","final":true/false}
  最后输出: {"text":"完整文本","done":true}
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
    json.dump({"text": "", "done": True}, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()
    sys.exit(0)

APP_ID = os.environ.get('XFYUN_APP_ID', '')
API_KEY = os.environ.get('XFYUN_API_KEY', '')
API_SECRET = os.environ.get('XFYUN_API_SECRET', '')
WS_URL = "wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1"
FRAME_SIZE = 1280
FRAME_INTERVAL = 0.04


def generate_auth_url():
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(beijing_tz)
    utc_str = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    raw_params = {
        "accessKeyId": API_KEY, "appId": APP_ID,
        "audio_encode": "pcm_s16le", "lang": "autodialect",
        "samplerate": "16000", "utc": utc_str, "uuid": uuid.uuid4().hex
    }
    sorted_params = dict(sorted(raw_params.items()))
    base_str = "&".join([
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted_params.items()
    ])
    signature = hmac.new(
        API_SECRET.encode("utf-8"), base_str.encode("utf-8"), hashlib.sha1
    ).digest()
    raw_params["signature"] = base64.b64encode(signature).decode("utf-8")
    return f"{WS_URL}?{urllib.parse.urlencode(raw_params)}"


def resample_to_16k(pcm_bytes, src_rate):
    """简单降采样 (无依赖)"""
    if src_rate <= 16000:
        return pcm_bytes
    ratio = src_rate / 16000
    src_samples = struct.unpack(f'<{len(pcm_bytes)//2}h', pcm_bytes)
    dst_count = int(len(src_samples) / ratio)
    dst = [src_samples[int(i * ratio)] for i in range(dst_count)]
    return struct.pack(f'<{len(dst)}h', *dst)


def emit(obj):
    """向 stdout 写一行 JSON"""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    # 从 stdin 第一行读取配置 (JSON)
    config_line = sys.stdin.readline().strip()
    try:
        config = json.loads(config_line)
    except:
        config = {}

    sample_rate = config.get("sample_rate", 48000)
    sys.stderr.write(f"[ASR-STREAM] Started, sample_rate={sample_rate}\n")

    # 连接讯飞 WebSocket
    try:
        ws_url = generate_auth_url()
        ws = create_connection(ws_url, timeout=15)
    except Exception as e:
        sys.stderr.write(f"[ASR-STREAM] Connect error: {e}\n")
        emit({"text": "", "done": True})
        return

    sys.stderr.write("[ASR-STREAM] Connected to iFlytek\n")

    full_text = ""
    session_id = None
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
                    if msg_json.get('msg_type') == 'action' and 'sessionId' in msg_json.get('data', {}):
                        session_id = msg_json['data']['sessionId']
                    if msg_json.get('msg_type') == 'result' and msg_json.get('res_type') == 'asr':
                        d = msg_json.get('data', {})
                        cn = d.get('cn', {})
                        st = cn.get('st', {})
                        if st.get('type') == '0':  # 最终结果
                            seg_text = ""
                            for rt in st.get('rt', []):
                                for ws_item in rt.get('ws', []):
                                    for cw in ws_item.get('cw', []):
                                        seg_text += cw.get('w', '')
                            full_text += seg_text
                            emit({"text": seg_text, "final": True})
            except Exception as e:
                if not recv_done.is_set():
                    sys.stderr.write(f"[ASR-STREAM] recv error: {e}\n")
                break

    t = threading.Thread(target=recv_thread, daemon=True)
    t.start()

    # 从 stdin 读取音频帧并转发
    frame_count = 0
    start_time = time.time()

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if line == "END":
            break
        if line.startswith("AUDIO:"):
            # base64 编码的 PCM 帧
            try:
                pcm_frame = base64.b64decode(line[6:])
                # 降采样到16kHz
                pcm_16k = resample_to_16k(pcm_frame, sample_rate)
                # 按帧大小拆分发送
                offset = 0
                while offset < len(pcm_16k):
                    end = min(offset + FRAME_SIZE, len(pcm_16k))
                    ws.send_binary(pcm_16k[offset:end])
                    offset = end
                    frame_count += 1
                    # 控制节奏
                    expected = start_time + frame_count * FRAME_INTERVAL
                    sleep_t = expected - time.time()
                    if sleep_t > 0.005:
                        time.sleep(sleep_t)
            except Exception as e:
                sys.stderr.write(f"[ASR-STREAM] send error: {e}\n")

    # 发送结束标识
    end_msg = {"end": True}
    if session_id:
        end_msg["sessionId"] = session_id
    try:
        ws.send(json.dumps(end_msg))
    except:
        pass

    sys.stderr.write(f"[ASR-STREAM] Audio done, waiting for final results...\n")
    t.join(timeout=8)
    recv_done.set()

    try:
        ws.close()
    except:
        pass

    emit({"text": full_text, "done": True})
    sys.stderr.write(f"[ASR-STREAM] Final: \"{full_text}\"\n")


if __name__ == "__main__":
    main()
