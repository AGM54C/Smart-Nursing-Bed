#!/usr/bin/env python3
"""
智能护理病床 - CSI摄像头 MJPEG 视频流

通过HTTP提供实时视频流，可在Web遥控界面或手机浏览器查看
访问地址: http://<树莓派IP>:8080/stream
"""

import io
import time
import threading

try:
    from picamera2 import Picamera2
    from picamera2.encoders import MJPEGEncoder
    from picamera2.outputs import FileOutput
    PICAM_AVAILABLE = True
except ImportError:
    PICAM_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from http.server import HTTPServer, BaseHTTPRequestHandler
from config import CAMERA_ENABLED, CAMERA_RESOLUTION, CAMERA_STREAM_PORT


class StreamBuffer(io.BufferedIOBase):
    """线程安全的帧缓冲区"""
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

    def get_frame(self, timeout=2.0):
        with self.condition:
            self.condition.wait(timeout=timeout)
            return self.frame


# 全局帧缓冲
_stream_buffer = StreamBuffer()
_camera = None
_running = False


def _start_picamera():
    """使用树莓派CSI摄像头"""
    global _camera
    _camera = Picamera2()
    config = _camera.create_video_configuration(
        main={"size": CAMERA_RESOLUTION, "format": "RGB888"},
        buffer_count=4
    )
    _camera.configure(config)
    encoder = MJPEGEncoder(bitrate=5000000)
    _camera.start_recording(encoder, FileOutput(_stream_buffer))
    print(f"[Camera] PiCamera started at {CAMERA_RESOLUTION}")


def _start_usb_camera():
    """使用USB摄像头 (通过OpenCV)"""
    global _running

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RESOLUTION[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])

    if not cap.isOpened():
        print("[Camera] ❌ No camera found")
        return

    print(f"[Camera] USB camera started via OpenCV")

    while _running:
        ret, frame = cap.read()
        if ret:
            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            _stream_buffer.write(jpeg.tobytes())
        time.sleep(0.033)  # ~30fps

    cap.release()


class StreamHandler(BaseHTTPRequestHandler):
    """HTTP请求处理: MJPEG流 + 快照"""

    def _set_cors(self):
        """允许从公网页面访问局域网摄像头 (Chrome Private Network Access)"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')

    def do_OPTIONS(self):
        """处理CORS预检请求"""
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/stream':
            self._handle_stream()
        elif self.path == '/snapshot':
            self._handle_snapshot()
        elif self.path == '/':
            self._handle_index()
        else:
            self.send_error(404)

    def _handle_stream(self):
        """MJPEG连续流"""
        self.send_response(200)
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Cache-Control', 'no-cache')
        self._set_cors()
        self.end_headers()

        try:
            while _running:
                frame = _stream_buffer.get_frame(timeout=2.0)
                if frame is None:
                    continue
                self.wfile.write(b'--frame\r\n')
                self.wfile.write(b'Content-Type: image/jpeg\r\n')
                self.wfile.write(f'Content-Length: {len(frame)}\r\n'.encode())
                self.wfile.write(b'\r\n')
                self.wfile.write(frame)
                self.wfile.write(b'\r\n')
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_snapshot(self):
        """单帧快照"""
        frame = _stream_buffer.get_frame(timeout=3.0)
        if frame:
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(frame)))
            self._set_cors()
            self.end_headers()
            self.wfile.write(frame)
        else:
            self.send_error(503, 'No frame available')

    def _handle_index(self):
        """简单预览页面"""
        html = f"""<!DOCTYPE html>
<html><head><title>Camera</title></head>
<body style="margin:0;background:#000;display:flex;justify-content:center;align-items:center;height:100vh">
<img src="/stream" style="max-width:100%;max-height:100vh">
</body></html>"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass  # 静默HTTP日志


def start_camera_stream(port=None):
    """
    启动摄像头视频流服务 (后台线程)
    访问 http://<IP>:<port>/stream  获取MJPEG流
    访问 http://<IP>:<port>/snapshot  获取单帧JPEG
    """
    global _running

    if not CAMERA_ENABLED:
        print("[Camera] Disabled in config")
        return

    _running = True
    port = port or CAMERA_STREAM_PORT

    # 选择摄像头源
    if PICAM_AVAILABLE:
        _start_picamera()
    elif CV2_AVAILABLE:
        t = threading.Thread(target=_start_usb_camera, daemon=True)
        t.start()
    else:
        print("[Camera] ⚠️ No camera library (picamera2/cv2), mock mode")
        # Mock: 生成黑色帧
        def mock_frames():
            import struct
            while _running:
                # 最小JPEG (1x1黑色像素)
                _stream_buffer.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9')
                time.sleep(1)
        threading.Thread(target=mock_frames, daemon=True).start()

    # 启动HTTP服务器
    server = HTTPServer(('0.0.0.0', port), StreamHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[Camera] Stream at http://0.0.0.0:{port}/stream")
    print(f"[Camera] Snapshot at http://0.0.0.0:{port}/snapshot")


def stop_camera_stream():
    global _running, _camera
    _running = False
    if _camera:
        try:
            _camera.stop_recording()
            _camera.close()
        except Exception:
            pass
    print("[Camera] Stopped")


if __name__ == "__main__":
    print("═══ Camera Stream Test ═══")
    start_camera_stream()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_camera_stream()
