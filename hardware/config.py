"""
智能护理病床 - 树莓派主控配置文件

⚠️ 收到硬件后, 只需修改本文件中的 WiFi、MQTT、云端地址即可
"""

# ═══════════════════════════════════════════
#  云端 API 配置
# ═══════════════════════════════════════════
CLOUD_SERVER = "http://47.109.61.163:3000"  # 云端服务器地址 (阿里云成都 2核2G, 2026-07新购)
DEVICE_API_KEY = "改成你自己的设备密钥"        # 设备认证密钥 (真实值放 local_secrets.py, 不入库)
PATIENT_ID = 1                               # 默认患者ID

# ═══════════════════════════════════════════
#  MQTT 配置 (本机 Mosquitto Broker)
# ═══════════════════════════════════════════
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "rpi-bed-controller"

# MQTT Topics
TOPIC_VITALS = "bed/vitals"
TOPIC_PRESSURE_MAT = "bed/pressure_mat"
TOPIC_PULSE_WAVE = "bed/pulse_wave"
TOPIC_BATTERY = "bed/battery"
TOPIC_CMD_PREFIX = "bed/cmd"
TOPIC_STATUS = "bed/status"
TOPIC_BREATH = "bed/breath"      # ESP32→4Hz压力总和 (呼吸率频域提取)

# ═══════════════════════════════════════════
#  涂鸦AI云 TuyaLink MQTT配置 (双链路: 本地+云端)
#  树莓派作为网关设备直连涂鸦云 (原华为IoTDA已移除)
#  三元组获取: iot.tuya.com → 产品开发(TuyaLink模式) → 设备管理
#  详细步骤见项目根目录 TUYA_MIGRATION.md
# ═══════════════════════════════════════════
TUYA_ENABLED = True                     # 三元组已配置 (2026-07-16)
TUYA_MQTT_BROKER = "m1.tuyacn.com"      # 中国数据中心 (海外: m1.tuyaus.com / m1.tuyaeu.com)
TUYA_MQTT_PORT = 8883                   # TLS
TUYA_PRODUCT_ID = ""                    # 产品ID (涂鸦平台「设备管理」复制三元组)
TUYA_DEVICE_ID = ""                     # 设备ID
TUYA_DEVICE_SECRET = ""                 # 设备密钥 (⚠️ 敏感! 真实值放 local_secrets.py, 不入库)

# 本地密钥覆盖: 同目录建 local_secrets.py (已 gitignore) 写入真实三元组与 DEVICE_API_KEY
# 必须在 Topics 构建之前导入, 否则 f-string 会拼到空设备ID
try:
    from local_secrets import *          # noqa: F401,F403
except ImportError:
    pass

# TuyaLink Topics (标准物模型格式, {d}=deviceId)
TUYA_TOPIC_REPORT = f"tylink/{TUYA_DEVICE_ID}/thing/property/report"
TUYA_TOPIC_PROPERTY_SET = f"tylink/{TUYA_DEVICE_ID}/thing/property/set"
TUYA_TOPIC_ACTION = f"tylink/{TUYA_DEVICE_ID}/thing/action/execute"
TUYA_TOPIC_ACTION_RESP = f"tylink/{TUYA_DEVICE_ID}/thing/action/execute_response"

# ═══════════════════════════════════════════
#  GPIO 引脚配置 (BCM编号)
# ═══════════════════════════════════════════

# L298N #1 - 前轮电机 (Channel A=左前, Channel B=右前)
MOTOR_LEFT_IN1  = 17
MOTOR_LEFT_IN2  = 27
# 右前轮实测转向相反, 对调 IN1/IN2 引脚做软件反向修正 (原 IN1=22 IN2=23)
MOTOR_RIGHT_IN1 = 23
MOTOR_RIGHT_IN2 = 22
MOTOR_ENA = 12          # PWM调速 (左前轮)
MOTOR_ENB = 16          # PWM调速 (右前轮)

# L298N #2 - 后轮电机 (Channel A=左后, Channel B=右后)
MOTOR_REAR_LEFT_IN1  = 5
MOTOR_REAR_LEFT_IN2  = 6
MOTOR_REAR_RIGHT_IN1 = 9
MOTOR_REAR_RIGHT_IN2 = 10
MOTOR_ENC = 11          # PWM调速 (左后轮)
MOTOR_END = 2           # PWM调速 (右后轮) - GPIO2

# L298N #3 - 电动推杆 (独立驱动, Channel A只用, Channel B空置)
# 与车轮驱动板完全隔离, 避免电机反电动势干扰推杆控制
ACTUATOR_IN1 = 13       # 推杆正转
ACTUATOR_IN2 = 19       # 推杆反转
ACTUATOR_EN  = 26       # PWM调速 (此引脚从循迹传感器组移出)

# 超声波 HC-SR04
ULTRA_FRONT_TRIG = 24
ULTRA_FRONT_ECHO = 25
ULTRA_LEFT_TRIG = 7
ULTRA_LEFT_ECHO = 8
ULTRA_RIGHT_TRIG = 20
ULTRA_RIGHT_ECHO = 21

# 循迹传感器 (5路TCRT5000板, 只接 S1/S3/S5 三路 = 左/中/右)
# GPIO14/15 已让给气囊电磁阀; GPIO26 已划给L298N#3 EN
# ⚠️ 需在 raspi-config 关闭串口console和SPI/I2C (见 接线指南.md)
LINE_SENSORS = [4, 18, 0]   # 从左到右 [L, C, R]

# RFID RC522 — ❌ 已停用: SPI0引脚(8,9,10,11)与后轮电机/左超声波物理冲突
# 定位功能由 NearLink 星闪替代; GPIO3 已划给气囊气泵继电器
RFID_RST = 3            # (遗留常量, 勿再接线)

# ═══════════════════════════════════════════
#  电机参数
# ═══════════════════════════════════════════
PWM_FREQ = 1000         # PWM频率 Hz
MOTOR_SPEED_DEFAULT = 60  # 默认速度 (0-100)
MOTOR_SPEED_SLOW = 35     # 低速 (转弯/接近目标)
MOTOR_SPEED_FAST = 80     # 高速

# ═══════════════════════════════════════════
#  导航参数
# ═══════════════════════════════════════════
OBSTACLE_DISTANCE_STOP = 15    # 停车距离 cm
OBSTACLE_DISTANCE_SLOW = 30    # 减速距离 cm
LINE_THRESHOLD = 0.5           # 循迹传感器阈值 (0=黑,1=白)
RFID_TARGET_ROOM = "302"       # 默认目标病房 (RFID遗留, NearLink模式下用NEARLINK_TARGET_ROOM)

# ═══════════════════════════════════════════
#  NearLink 星闪室内定位配置
#  芯片: Hi3863V100 (锚点+床载标签), Hi2821E (手环标签)
#  方案B: 巡线+NearLink混合定位
# ═══════════════════════════════════════════
NEARLINK_ENABLED = True

# MQTT Topics (锚点通过WiFi上报测距数据)
TOPIC_NL_RANGING = "bed/nearlink/ranging"    # 锚点→树莓派: 测距数据
TOPIC_NL_POSITION = "bed/nearlink/position"  # 树莓派发布: 解算后的坐标
TOPIC_NL_STATUS = "bed/nearlink/status"      # NearLink系统状态

# 锚点坐标 (3病房Demo走廊布局)
# 原点: 走廊起点地面中心, X轴沿走廊方向, Y轴垂直走廊
# 单位: 米
NEARLINK_ANCHORS = {
    "anchor_01": {"x": 0.0,  "y": 0.0, "z": 2.5, "desc": "走廊起点/301门口"},
    "anchor_02": {"x": 4.0,  "y": 0.0, "z": 2.5, "desc": "302门口"},
    "anchor_03": {"x": 8.0,  "y": 0.0, "z": 2.5, "desc": "303门口/走廊末端"},
}

# 病房入口坐标 (到达判定点)
NEARLINK_ROOM_WAYPOINTS = {
    "301": {"x": 0.5,  "y": -1.0, "desc": "301号病房入口"},
    "302": {"x": 4.5,  "y": -1.0, "desc": "302号病房入口"},
    "303": {"x": 8.5,  "y": -1.0, "desc": "303号病房入口"},
}

NEARLINK_TARGET_ROOM = "302"     # 默认NearLink目标病房

# 定位参数
NL_ARRIVE_THRESHOLD = 0.8       # 到达判定半径 (米), ±0.5m定位精度 + 余量
NL_SLOWDOWN_THRESHOLD = 2.0     # 减速区半径 (米)
NL_POSITION_UPDATE_HZ = 5       # 位置更新频率 (Hz)
NL_KALMAN_PROCESS_NOISE = 0.05  # 卡尔曼滤波过程噪声
NL_KALMAN_MEASURE_NOISE = 0.3   # 卡尔曼滤波测量噪声 (与SLE测距精度匹配)
NL_MIN_ANCHORS = 3              # 最少需要的锚点数 (三边定位)

# ═══════════════════════════════════════════
#  推杆参数
# ═══════════════════════════════════════════
ACTUATOR_RAISE_TIME = 5.0    # 升到最高需要的秒数
ACTUATOR_LOWER_TIME = 5.0    # 降到最低需要的秒数

# ═══════════════════════════════════════════
#  气囊减压系统 (创新点: 闭环自动减压)
#  硬件: 5V小气泵(继电器控制) + 2个电磁阀(分区)
#  ⚠️ 继电器模块请选低电平触发(常见光耦板):
#     GPIO3 有板载I2C上拉, 开机为高电平 → 低触发=气泵不动 ✓
#  ⚠️ GPIO14/15 是 UART0, 必须关闭串口console否则阀门乱跳
# ═══════════════════════════════════════════
AIR_RELAY_ACTIVE_LOW = True  # 低电平触发继电器 (True=输出LOW导通)
AIR_PUMP_PIN = 3             # 气泵继电器 GPIO
AIR_VALVE_LEFT = 14          # 左区电磁阀 GPIO
AIR_VALVE_RIGHT = 15         # 右区电磁阀 GPIO
AIR_MAX_INFLATE_TIME = 10.0  # 单次最大充气时间(秒)
AIR_CYCLE_INTERVAL = 300     # 减压循环最小间隔(秒)
AIR_INFLATE_DURATION = 5.0   # 默认充气时长(秒)
AIR_DEFLATE_DURATION = 3.0   # 默认放气时长(秒)

# ═══════════════════════════════════════════
#  语音配置
# ═══════════════════════════════════════════
VOICE_AUTO_MODE = True         # 自动检测静音停止录音
VOICE_WAKEWORD_ENABLED = True  # 是否启用唤醒词
VOICE_WAKEWORD = "你好小床"    # 唤醒词 (需要snowboy模型)

# ═══════════════════════════════════════════
#  LCD 屏幕
# ═══════════════════════════════════════════
LCD_ENABLED = True
LCD_WIDTH = 480
LCD_HEIGHT = 320

# ═══════════════════════════════════════════
#  摄像头
# ═══════════════════════════════════════════
CAMERA_ENABLED = True
CAMERA_RESOLUTION = (640, 480)
CAMERA_STREAM_PORT = 8080
