# 🛏️ 智能护理病床 (Smart Nursing Bed)

> 基于物联网 IoT + AI 大模型的慢性病患者智能看护系统 —— 端(ESP32-S3)·边(树莓派 4B)·云(Express + 涂鸦AI云)三层架构
>
> **本 README 是完整的搭建手册:从硬件采购、供电、接线、烧录,到树莓派、云服务器、涂鸦平台接入、联调验证,按顺序做即可复现整个系统。**

[![Node.js](https://img.shields.io/badge/Node.js-20-green)](https://nodejs.org/)
[![Express](https://img.shields.io/badge/Express-4.18-blue)](https://expressjs.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57)](https://sqlite.org/)
[![LLM](https://img.shields.io/badge/LLM-Qwen3.5%20Plus-purple)](https://bailian.console.aliyun.com/)
[![PyTorch](https://img.shields.io/badge/Edge%20AI-MobileNetV3-EE4C2C)](https://pytorch.org/)
[![ONNX](https://img.shields.io/badge/ONNX-Runtime-005CED)](https://onnxruntime.ai/)
[![Tuya](https://img.shields.io/badge/Tuya-TuyaLink-orange)](https://platform.tuya.com/)
[![Three.js](https://img.shields.io/badge/Digital%20Twin-Three.js-black)](https://threejs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 📑 目录

- [项目速览](#-项目速览)
- [系统架构](#-系统架构)
- [搭建总路线图](#-搭建总路线图)
- [第 1 步:硬件采购](#-第-1-步硬件采购)
- [第 2 步:电源系统搭建](#-第-2-步电源系统搭建)
- [第 3 步:ESP32-S3 传感器节点(接线 + 烧录)](#-第-3-步esp32-s3-传感器节点接线--烧录)
- [第 4 步:机械组装(底盘 / 电机 / 推杆 / 气囊)](#-第-4-步机械组装底盘--电机--推杆--气囊)
- [第 5 步:树莓派边缘网关](#-第-5-步树莓派边缘网关)
- [第 6 步:云服务器部署](#-第-6-步云服务器部署)
- [第 7 步:接入涂鸦 AI 云(TuyaLink)](#-第-7-步接入涂鸦-ai-云tuyalink)
- [第 8 步:联调与验证(含无硬件虚拟联调)](#-第-8-步联调与验证含无硬件虚拟联调)
- [第 9 步:Demo 演示流程](#-第-9-步demo-演示流程)
- [演示账号](#-演示账号)
- [常见故障速查](#-常见故障速查)
- [项目结构](#-项目结构)
- [技术栈与 AI 能力](#-技术栈与-ai-能力)
- [API 接口文档](#-api-接口文档)
- [相关文档](#-相关文档)

---

## 📋 项目速览

传统护理依赖人工定时巡检,存在**监测盲区大、响应滞后、护理人员负担重**的问题。本项目用一张智能病床解决:

| 特色 | 说明 |
|------|------|
| 🧠 **AI 大模型加持** | LLM(通义 Qwen3.5-Plus,OpenAI 兼容接口可换任意模型)生成健康报告、护理咨询、受压深度分析 |
| 📡 **涂鸦AI云 TuyaLink** | 本地 MQTT + 涂鸦云双链路:设备三元组 TLS 认证、物模型属性上报、平台远程下发指令 |
| 🔬 **双模型边缘 AI** | PostureCNN(15K) + PostureMobileNet(45K, MobileNetV3-inspired) + ONNX Runtime,<1ms 推理 |
| 🤖 **AI 自主决策闭环** | 感知→决策→执行,8 条规则:低血氧自动抬靠背、持续受压自动气囊减压、跌倒告警等 |
| 🔮 **预测性护理** | 1D-CNN 受压风险预测,提前 30 分钟预警压疮风险 |
| 🎤 **语音 AI 陪护 + NLC** | ASR→LLM→TTS 陪聊;自然语言控制:"把靠背升起来""去302房"→ 11 种硬件动作 |
| 🌐 **数字孪生 3D** | Three.js 实时病床模型 + 压力热力图 + 体位动画(`/digital-twin.html`) |
| 🔗 **多模态融合告警** | MediaPipe Pose 视觉 + 压力矩阵 + 体征,Dempster-Shafer 证据融合 |
| 🗺️ **自主寻房导航** | 5 路循迹 + RFID/星闪定位 + 3 路超声波避障 |
| 🛡️ **联邦学习 + 区块链** | FedAvg + 差分隐私(ε=2.0);SHA-256 链式哈希健康记录存证 |
| 📊 **5 种专科 AI Agent** | 高位截瘫/糖尿病/中风/COPD/通用,独立提示词与个性化告警阈值 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          系统架构总览 v2.1                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐   MQTT    ┌──────────────────┐    HTTP     ┌─────────────────┐
│   │  ESP32-S3    │ ────────→ │    树莓派 4B      │ ─────────→ │  云端服务器 ECS   │
│   │  传感器节点   │  (局域网)  │   边缘AI网关      │  REST API  │  Express + SQLite│
│   │              │           │                  │            │                 │
│   │ · MAX30102   │ Mosquitto │ · MQTT→HTTP桥接  │            │ · LLM AI 分析   │
│   │   心率/血氧   │  :1883    │ · MobileNet推理  │            │ · JWT+RBAC 认证 │
│   │ · MLX90614   │           │ · ONNX Runtime   │            │ · 数字孪生 3D   │
│   │   红外测温    │           │ · AI自主决策引擎  │            │ · ASR/TTS/SER  │
│   │ · MPU6050    │           │ · 多模态融合告警  │            │ · AI报告/预警   │
│   │   六轴姿态    │           │ · 1D-CNN风险预测 │            │ · 语音聊天/NLC  │
│   │ · Velostat   │           │ · 气囊自动减压    │            └─────────────────┘
│   │   8×8压力矩阵 │           │ · 4WD导航/推杆   │
│   │ · HK-2000B+  │           │ · 语音AI/LCD     │
│   │   脉搏血压    │           └────────┬─────────┘
│   └──────────────┘                    │ TuyaLink (TLS MQTT :8883)
│                                       ▼
│                              ┌──────────────────┐
│                              │   涂鸦AI云平台    │ ◄── App面板/平台下发指令
│                              │ 物模型上报/下发   │
│                              └──────────────────┘
│                                                                         │
│   ◄── 端层 (感知) ──►    ◄── 边层 (AI推理+决策+执行) ──►   ◄── 云层 (应用+存储) ──►
└─────────────────────────────────────────────────────────────────────────┘
```

**数据流**:传感器采集 → ESP32 每 2~5s MQTT 发布 → 树莓派 Mosquitto → MQTT Bridge 解析 → ①本地 AI(睡姿/受压/翻身/预测)→ 决策引擎自动执行 ②HTTP POST 云端入库 + 阈值告警 ③TuyaLink 上报涂鸦云;涂鸦平台/云端可反向下发指令控制推杆、导航、气囊。

---

## 🗺️ 搭建总路线图

> 从硬到软共 9 步。**没有硬件也能先跑通第 6/7/8 步**(云端 + 涂鸦 + 虚拟联调),硬件到货后再补 1~5 步。

| 步骤 | 内容 | 在哪操作 | 预计耗时 |
|------|------|----------|----------|
| 1 | 硬件采购 | 淘宝 | 下单 1h,到货 3~7 天 |
| 2 | 电源系统(电池/降压/总线) | 工作台 | 1~2h |
| 3 | ESP32 接线 + 压力矩阵制作 + 烧录 | 工作台 + PC | 3~4h |
| 4 | 机械组装(底盘/电机/推杆/气囊) | 工作台 | 3~5h |
| 5 | 树莓派系统 + 边缘软件 | 树莓派 | 2~3h |
| 6 | 云服务器部署 | 阿里云 ECS | 1h |
| 7 | 涂鸦平台建产品 + 设备接入 | platform.tuya.com | 1h |
| 8 | 联调与验证 | 全部 | 1~2h |
| 9 | Demo 演示 | 现场 | — |

---

## 🛒 第 1 步:硬件采购

完整 BOM(每件物料的型号、参考价、淘宝搜索关键词)见 **[hardware/README.md](hardware/README.md)**,共约 **¥950**(主体)+ **¥35**(气囊减压系统)。核心清单:

| 类别 | 物料 |
|------|------|
| 主控 | 树莓派 4B(4G/8G)、ESP32-S3-N16R8 开发板(USB-C,16MB Flash + 8MB PSRAM) |
| 体征传感 | MAX30102(心率/血氧)、MLX90614 GY-906(红外测温)、MPU6050 GY-521(六轴)、HK-2000B+(脉搏波/血压估算) |
| 压力矩阵 | Velostat 导电膜 30×30cm、5mm 导电铜箔胶带、CD74HC4051 多路复用器 ×2、10kΩ 电阻 |
| 运动底盘 | 4WD TT 马达小车套件、L298N 双 H 桥 ×3、5 路 TCRT5000 循迹、HC-SR04 超声波 ×3、RC522 RFID 套装 |
| 执行机构 | 12V 电动推杆(行程 150mm)、5V 微型气泵、5V 常闭电磁阀 ×2、3 路继电器模块、PU 气管 + 三通、气囊 ×2 |
| 交互 | CSI 摄像头 V2、3.5 寸 SPI LCD、USB 免驱麦克风、PAM8403 功放 + 3W 喇叭 |
| 电源 | 12V 3S 5000mAh 锂电池(**DC 5.5×2.1mm 头**)、12.6V 充电器、LM2596 降压 ×3、船型开关、DC 母座转接板、USB-C 供电线(裸线头) |
| 辅材 | 面包板 ×2、杜邦线、100kΩ+33kΩ 分压电阻、M3 铜柱、扎带/热缩管、黑色电工胶带(循迹路线)、关节可动人偶(模拟患者) |

> 💡 电池务必买 **DC 头成品电池组**(带保护板),充放电同口即插即充;不要买 XT60/T 插航模电池。

---

## ⚡ 第 2 步:电源系统搭建

> 完整原理、功率预算(行驶 ~35W / 静止 ~15W,5000mAh 续航 1.7~4h)、故障排查见 [hardware/README.md「电源系统详解」](hardware/README.md);逐步操作版见 [DEPLOYMENT.md 第零阶段](DEPLOYMENT.md)。

**供电拓扑**:

```
12V锂电池(DC头) → DC母座转接板 → 船型开关 → 12V正极总线
                                     ├→ L298N #1 (前轮电机)
                                     ├→ L298N #2 (后轮电机)
                                     ├→ L298N #3 (电动推杆)
                                     ├→ LM2596 #1 → 5.1V → USB-C线 → 树莓派4B
                                     ├→ LM2596 #2 → 5.1V → 面包板 → ESP32-S3 VIN + 传感器
                                     └→ LM2596 #3 → 5.1V → 3路继电器 → 气泵/电磁阀
所有负极 → 2进12出配电端子排(天然共地)
```

**⚠️ 最关键一步——先调压再接设备**:LM2596 出厂可能输出 12V,直接接树莓派/ESP32 会烧毁!

1. LM2596 IN+/IN- 接 12V 电池
2. 万用表(直流电压档)量 OUT+/OUT-
3. 小一字螺丝刀旋蓝色电位器:逆时针降压,精确调到 **5.10V ± 0.05V**
4. 三个 LM2596 逐一调好并用马克笔标记:`#1=树莓派 #2=ESP32 #3=气囊`

**通电前检查清单**:

```
□ 三个 LM2596 都已万用表确认 5.10V
□ 船型开关处于关闭
□ 所有 GND 汇入端子排(共地)
□ USB-C 供电线红=+、黑=- 无反接
□ 传感器接 3.3V(不是 5V!)
□ 万用表测 12V 正负极阻值 >1kΩ(无短路)
```

首次通电:打开船型开关 → 树莓派红 LED 亮、ESP32 板载 LED 亮、L298N 指示灯亮、10 秒内无元件发烫。任何异常立即断电。

---

## 🔌 第 3 步:ESP32-S3 传感器节点(接线 + 烧录)

### 3.1 传感器接线(引脚以 [hardware/esp32/src/config.h](hardware/esp32/src/config.h) 为准)

**I2C 总线(三个传感器面包板并联,地址互不冲突)**:

| ESP32-S3 引脚 | 连接 | 说明 |
|---------------|------|------|
| GPIO2 (SDA) | MAX30102 / MLX90614 / MPU6050 的 SDA | I2C 地址 0x57 / 0x5A / 0x68 |
| GPIO1 (SCL) | 三者的 SCL | |
| 3V3 | 三者的 VCC | ⚠️ 全部 3.3V 器件,严禁 5V |
| GND | 三者的 GND | |

**压力矩阵 + 模拟量(全部走 ADC1,WiFi 开启时 ADC2 不可用)**:

| ESP32-S3 引脚 | 连接 |
|---------------|------|
| GPIO39/40/41 | MUX1(行选择 CD74HC4051)S0/S1/S2 |
| GPIO42/21/47 | MUX2(列选择)S0/S1/S2 |
| GPIO48 | MUX1 SIG(行驱动) |
| GPIO4 (ADC1) | MUX2 COM 输出(经 10kΩ 下拉接地) |
| GPIO5 (ADC1) | HK-2000B+ 脉搏信号 |
| GPIO6 (ADC1) | 电池分压中点(12V→100kΩ→**中点**→33kΩ→GND,满电 12.6V 分压后 3.12V) |
| GPIO16/15 | UART1 RX/TX(预留正式连续血压传感器,`BP_SENSOR_ENABLED` 默认关) |

### 3.2 Velostat 压力矩阵制作(8×8)

1. 30×30cm 泡沫垫做基底,平行贴 **8 条铜箔**(间距 ~3cm)作为行电极,引出杜邦线接 MUX1 的 8 个通道
2. 整张 Velostat 覆盖行电极
3. Velostat 上方**正交**再贴 8 条铜箔作为列电极,接 MUX2 的 8 个通道
4. 盖无纺布保护层
5. 原理:行 MUX 逐行加 3.3V(GPIO48 控制),列 MUX 逐列读 ADC(GPIO4),扫出 64 点压力

### 3.3 编译烧录(在你的 PC 上,Windows/Mac/Linux 均可)

```bash
pip install platformio          # 或 VSCode 装 PlatformIO IDE 扩展

# 修改 WiFi 与 MQTT 配置
# 编辑 hardware/esp32/src/config.h:
#   WIFI_SSID / WIFI_PASSWORD  → 你的 WiFi(2.4GHz)
#   MQTT_BROKER                → 树莓派 IP(第 5 步确定后回填重烧)

cd hardware/esp32
pio run                         # 仅编译验证
pio run -t upload               # USB-C 连接 ESP32-S3 后烧录
pio device monitor              # 打开串口(115200)
```

> 📦 所有依赖库(ArduinoJson 7.x、PubSubClient、SparkFun MAX3010x、Adafruit MLX90614、MPU6050)已放在 `hardware/esp32/lib/`,**离线可编译**。实测:`SUCCESS`,RAM 14.8%(48KB/320KB)、Flash 11.5%(755KB/6.5MB)。
>
> 烧录失败时:按住 **BOOT** → 点按 **RST** → 松开 BOOT → 重试(进入下载模式)。

串口自检应看到:

```
║  🛏️ 智能护理病床 - ESP32传感器节点  ║
  MAX30102 (HR/SpO2): ✅
  MLX90614 (Temp):    ✅
  MPU6050 (Posture):  ✅
  Pressure Mat:       ✅
  Pulse (BP):         ✅ (HK-2000B+ Estimated)
```

某项 ❌ = 检查该传感器杜邦线;MQTT 连接失败可先忽略,等树莓派就绪自动重连。上报节奏:体征 5s / 压力矩阵 2s / 脉搏波 1s / 电池 30s。

---

## 🔧 第 4 步:机械组装(底盘 / 电机 / 推杆 / 气囊)

> 详细步骤见 [DEPLOYMENT.md 第四阶段](DEPLOYMENT.md)。树莓派 GPIO 均为 **BCM 编号**,权威定义在 [hardware/config.py](hardware/config.py)。

**电机 / 推杆(3 块 L298N)**:

| 设备 | L298N | 方向引脚 | 使能(PWM) |
|------|-------|----------|------------|
| 左前轮 | #1 ChA | IN1=GPIO17, IN2=GPIO27 | ENA=GPIO12 |
| 右前轮 | #1 ChB | IN3=GPIO22, IN4=GPIO23 | ENB=GPIO16 |
| 左后轮 | #2 ChA | IN1=GPIO5, IN2=GPIO6 | ENA=GPIO11 |
| 右后轮 | #2 ChB | IN3=GPIO9, IN4=GPIO10 | ENB=GPIO2 |
| 电动推杆 | #3 ChA | IN1=GPIO13, IN2=GPIO19 | EN=GPIO26 |

- 所有 L298N:12V 接电池总线,5V 逻辑接树莓派 5V(Pin 2/4),GND 与树莓派共地
- L298N #3 的 ChB 悬空

**传感与交互**:

| 设备 | 树莓派引脚 |
|------|-----------|
| 循迹 TCRT5000 ×5(左→右) | GPIO4, 14, 15, 18, 0 |
| 超声波 前/左/右 Trig,Echo | GPIO24,25 / GPIO7,8 / GPIO20,21 |
| RFID RC522(SPI0) | MOSI=10, MISO=9, SCK=11, CE0=8, RST=GPIO3 |
| 气囊系统(继电器 IN1/2/3) | 气泵=GPIO3, 左阀=GPIO14, 右阀=GPIO15 |
| CSI 排线 / SPI1 / USB / 3.5mm | 摄像头 / 3.5寸 LCD / 麦克风 / PAM8403→喇叭 |

> ⚠️ **引脚复用提示**:气囊继电器(GPIO3/14/15)与 RFID_RST(GPIO3)、循迹(GPIO14/15)存在复用;RC522 的 SPI0 引脚(9/10/11)与后轮 L298N 复用。这是演示型设计——**同一时刻只启用其一**(如"导航演示"关闭气囊、"减压演示"停车进行),或在 `config.py` 中把冲突项改到空闲 GPIO。

**气路连接**:气泵出气口 → T 型三通 → 左电磁阀 → 左气囊;三通另一路 → 右电磁阀 → 右气囊。气囊分左右两区铺在床垫下。

**组装顺序**:底盘 + 4 电机 → 3×L298N 固定接线 → 循迹(底部,离地 1~2cm)→ 超声波(前/左/右)→ RFID(侧面朝外)→ 上层铜柱固定树莓派(接摄像头/LCD/麦克风/功放)→ 推杆固定 + 顶部小平台(放人偶)→ Velostat 垫铺平台 → 电池(下层配重)+ 电源走线扎带整理 → 气囊系统。

---

## 🍓 第 5 步:树莓派边缘网关

### 5.1 系统与基础环境

```bash
# 1. Raspberry Pi Imager 烧录 Raspberry Pi OS (64-bit) 到 TF 卡
#    高级设置里直接配好: 用户名 pi、WiFi、启用 SSH
# 2. 上电,SSH 登录
ssh pi@<树莓派IP>

# 3. 启用外设
sudo raspi-config
#   Interface Options → SPI → Enable      (RFID)
#   Interface Options → I2C → Enable
#   Interface Options → Camera → Enable   (CSI 摄像头)

# 4. 安装 Mosquitto MQTT Broker
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto

# 5. 记下树莓派 IP → 回填 ESP32 config.h 的 MQTT_BROKER 并重烧固件
hostname -I
```

### 5.2 部署代码与依赖

```bash
# 从 PC 上传整个项目
scp -r smart-nursing-bed/ pi@<树莓派IP>:/home/pi/

# 树莓派上安装依赖
sudo apt install -y python3-pip python3-pyaudio python3-rpi.gpio mpg123
cd /home/pi/smart-nursing-bed/hardware
pip3 install -r requirements.txt
# PyTorch 在 RPi 上安装较慢(10~20min);失败不阻塞——AI 自动降级规则模式
```

### 5.3 修改配置 `hardware/config.py`

```python
CLOUD_SERVER   = "http://47.109.61.163:3000"   # ← 换成你的云服务器 IP(第 6 步)
DEVICE_API_KEY = "<你的DEVICE_API_KEY>"              # 与云端 .env 一致
PATIENT_ID     = 1

# 涂鸦云(第 7 步拿到三元组后填,先保持 False 不影响本地全功能)
TUYA_ENABLED       = False
TUYA_PRODUCT_ID    = "YOUR_PRODUCT_ID"
TUYA_DEVICE_ID     = "YOUR_DEVICE_ID"
TUYA_DEVICE_SECRET = "YOUR_DEVICE_SECRET"
```

### 5.4 训练边缘 AI 模型(推荐,模型文件不随仓库分发)

```bash
python3 pressure_analyzer.py train    # ~60s,生成 posture_mobilenet.pth/.onnx(睡姿分类)
python3 predictive_model.py train     # ~30s,生成 predictive_risk.pth(受压风险预测)
python3 pressure_analyzer.py benchmark
# 推理引擎自动择优: ONNX Runtime > MobileNet > CNN > 规则回退
```

### 5.5 写 RFID 病房卡 + 启动

```bash
python3 rfid_reader.py write          # 依提示把白卡贴上 RC522,写入 301/302/303

python3 main.py                       # 启动主控
```

期望输出(节选):

```
║  🛏️  智能护理病床 · 树莓派主控 v3.0  ║
─── [1/7] Starting MQTT Bridge + TuyaLink ───
[MQTT Bridge] Connected to Mosquitto
─── [2/7] Initializing Hardware ───
  ✅ Navigator / Actuator / Air Cushion ready
─── [3/7] Starting AI Decision Engine v2.0 ───
...
  🌐 Web Remote:  http://<RPi-IP>:5000     ← 手机遥控界面
  📹 Camera:      http://<RPi-IP>:8080/stream
  ☁️  Cloud API:   http://47.109.61.163:3000
  Tuya: Disabled (三元组未配置)
```

### 5.6 开机自启(可选)

```bash
sudo tee /etc/systemd/system/smart-bed.service > /dev/null <<'EOF'
[Unit]
Description=Smart Nursing Bed Controller
After=mosquitto.service network.target
[Service]
ExecStart=/usr/bin/python3 /home/pi/smart-nursing-bed/hardware/main.py
WorkingDirectory=/home/pi/smart-nursing-bed/hardware
User=pi
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now smart-bed
```

---

## ☁️ 第 6 步:云服务器部署

> 以下为本项目实际部署并验证过的流程(阿里云成都 ECS,**2 核 2G / 3Mbps 完全够用**,Ubuntu 22.04,示例 IP `47.109.61.163` 请替换为你的)。

### 6.1 购买 & 安全组放行(⚠️ 必做,否则外网访问不了)

阿里云控制台 → ECS → 实例 → 点实例 ID → **安全组** → 配置规则 → **入方向 → 手动添加**:

| 端口 | 协议 | 授权对象 | 用途 |
|------|------|----------|------|
| 3000 | TCP | 0.0.0.0/0 | Web 控制台 + API(必须) |
| 80/443 | TCP | 0.0.0.0/0 | Nginx 反代(可选) |
| 22 | TCP | 建议改成你的出口 IP | SSH(默认已放行) |

> 浏览器访问用 **`http://<IP>:3000`**(不是 https——未配证书;需要 https 再上 Nginx + 免费证书)。

### 6.2 安装 Node.js 20(国内镜像,免翻墙)

```bash
ssh root@<你的服务器IP>

wget https://registry.npmmirror.com/-/binary/node/v20.19.0/node-v20.19.0-linux-x64.tar.xz
tar -xf node-v20.19.0-linux-x64.tar.xz -C /usr/local --strip-components=1
node -v                                              # v20.19.0
npm config set registry https://registry.npmmirror.com
```

### 6.3 上传代码、配置、启动

```bash
# PC 上传(或 git clone)
scp -r smart-nursing-bed/ root@<服务器IP>:/opt/

# 服务器上
cd /opt/smart-nursing-bed
npm install --omit=dev

# 配置环境变量(模板见 .env.example, 完整说明见 TUYA_MIGRATION.md 第五步)
cp .env.example .env && vi .env
# LLM 降级链: 涂鸦智能体 → Moonshot kimi-k3 → SiliconFlow (上级失败自动降级, 演示不中断)
#   MOONSHOT_API_KEY=  主力 kimi-k3 (platform.kimi.com 申请, K3 需充值)
#   KIMI_API_KEY=      保底 SiliconFlow (siliconflow.cn 申请)
#   TUYA_ACCESS_ID/SECRET + TUYA_AGENT_ID_*  涂鸦智能体 (probe 脚本体检)

# PM2 守护 + 开机自启
npm install -g pm2
pm2 start server.js --name nursing-bed     # 或 pm2 start config/ecosystem.config.js
pm2 save && pm2 startup systemd            # 按提示执行输出的那行命令
```

### 6.4 验证

```bash
curl -s http://127.0.0.1:3000/ -o /dev/null -w "%{http_code}\n"   # 200

# 登录 API
curl -s -X POST http://127.0.0.1:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'                  # 返回 JWT

# 模拟设备上报
curl -s -X POST http://127.0.0.1:3000/api/vitals \
  -H "Content-Type: application/json" -H "X-API-Key: <你的DEVICE_API_KEY>" \
  -d '{"patient_id":1,"heart_rate":72,"blood_oxygen":96,"temperature":36.5,"sleep_posture":"supine"}'
```

浏览器打开 `http://<服务器IP>:3000` → admin/admin123 登录 → 能看到仪表盘即成功。数据库为 SQLite(`db/nursing.db`,WAL 模式),首次启动自动按 `db/schema.sql` + `db/seed.sql` 初始化,零运维。

---

## 🟠 第 7 步:接入涂鸦 AI 云(TuyaLink)

> 本项目走 **TuyaLink 网关直连**路线:树莓派用设备三元组直连涂鸦云,**不需要 T5/涂鸦模组硬件,不需要 TuyaOpen 授权码**。协议实现在 [hardware/tuya_link.py](hardware/tuya_link.py)(HMAC-SHA256 签名 + TLS MQTT),完整迁移说明见 [TUYA_MIGRATION.md](TUYA_MIGRATION.md)。

### 7.1 创建产品([platform.tuya.com](https://platform.tuya.com))

1. 注册/登录涂鸦开发者平台 → **产品开发 → 创建产品**
2. 品类选 **网关**(找不到就搜索;品类不严格,物模型全部自定义)
3. **智能化方式选「生态设备接入」**——⚠️ 这就是 TuyaLink 在新版平台上的名字,**不要选"产品开发"**(那会进 TuyaOS/MCU 方案)
4. 填产品名称(如 `智能护理病床`)→ 创建

### 7.2 功能定义(物模型,code 必须与下表完全一致)

**上报属性(12 个)**:

| code | 类型 | 取值/说明 |
|------|------|-----------|
| heart_rate | 数值 | 0~200 次/min |
| blood_oxygen | 数值 | 0~100 % |
| temperature | 数值 | 200~450,**倍数 1**(实际值×10,36.5℃→365) |
| blood_pressure_sys / blood_pressure_dia | 数值 | mmHg |
| sleep_posture | 枚举 | supine, left, right, prone, sitting, empty, unknown |
| pressure_total | 数值 | 压力矩阵总和 |
| bed_occupied | 布尔 | 在床检测 |
| posture_ai | 字符串 | 边缘 AI 分析摘要 |
| ulcer_risk | 枚举 | none, low, medium, high |
| battery_voltage | 数值 | 倍数 1(×10) |
| battery_percent | 数值 | 0~100 |

**可下发属性(2 个)**:`target_bed_angle`(数值 0~60,下发即调推杆)、`target_room`(字符串,下发即导航)

**动作(5 个)**:`set_bed_angle(angle)`、`emergency_stop`、`navigate_room(room)`、`air_decompress(zone: left/right/both)`、`get_status`

### 7.3 获取三元组并联调

1. 产品页 → **设备管理 / 联调设备 → 添加设备** → 得到 `deviceId` + `deviceSecret`(productId 在产品页顶部)
2. 填入树莓派 `hardware/config.py` 的 `TUYA_PRODUCT_ID / TUYA_DEVICE_ID / TUYA_DEVICE_SECRET`,并把 `TUYA_ENABLED = True`
3. 单独验证连接(不用启动整个系统):

```bash
cd hardware && python3 tuya_link.py
# 期望: [TuyaLink] Connected → 平台设备列表中该设备变「在线」,并每 5s 收到模拟体征
```

4. 之后正常 `python3 main.py`,桥接层会自动把体征/压力/电池上报涂鸦云,并接收平台下发的属性设置与动作(压力上报节流 5s/次)。

> 🏆 **竞赛提示**(2026 全国大学生物联网设计竞赛·涂鸦赛道):入群可领免费设备授权码、免费涂鸦大模型额度与 T5AI 板卡——本方案均非必需,但可作加分扩展(如把 5 个专科 Agent 迁到涂鸦智能体平台、App 面板)。

---

## ✅ 第 8 步:联调与验证(含无硬件虚拟联调)

### 8.1 没有硬件?虚拟跑通全链路(本仓库已验证 PASS)

不插任何硬件,在 PC 上模拟 `ESP32 → MQTT → 桥接+AI → 云端 → SQLite` 全链:

```bash
# 终端 1:本地 MQTT broker(替代树莓派 Mosquitto)
npx -y aedes-cli --port 1883

# 终端 2:本地云端(替代 ECS)
PORT=3100 node server.js

# 终端 3:一键端到端测试
cd hardware && python test_e2e.py
```

期望输出:

```
─── 校验结果 ───
  ✅ Bridge缓存体征: HR=76 SpO2=98 姿态=supine
  ✅ 压力AI分析: posture=supine conf=60%
  ✅ 云端SQLite新增 6 行 vitals (HTTP POST 201 全链路通)
═══ ✅ E2E PASS ═══
```

也可手动灌数据观察仪表盘:`python hardware/mock_publisher.py`(`--abnormal` 触发告警,`--pressure` 模拟持续受压)。

### 8.2 分模块硬件测试(树莓派上)

```bash
mosquitto_sub -h localhost -t "bed/#" -v      # 1. 看 ESP32 数据有没有进来
python3 rfid_reader.py                        # 2. 刷卡显示房间号
python3 air_cushion.py cycle                  # 3. 气囊充放气循环(~22s)
python3 camera_stream.py                      # 4. 浏览器 http://<RPi-IP>:8080/stream
# 电机/超声波/推杆的单测代码段见 DEPLOYMENT.md 第五阶段
```

### 8.3 全链路验收清单

```
□ ESP32 串口 5 个传感器全 ✅,MQTT connected
□ mosquitto_sub 能看到 bed/vitals、bed/pressure_mat、bed/battery
□ 云端 Dashboard 心率实时跳动、压力热力图随按压变化
□ 睡姿显示 MobileNet 推理结果;/digital-twin.html 3D 同步
□ 涂鸦平台设备「在线」,设备调试页能看到属性上报
□ 涂鸦平台下发 target_bed_angle=30 → 推杆动作
□ 手机 http://<RPi-IP>:5000 遥控前后左右/升降正常
□ 说"病床控制"→"把靠背升起来" → 推杆升起(NLC)
```

---

## 🎬 第 9 步:Demo 演示流程

场地:黑胶带贴 3cm 宽"走廊"路线,岔口放纸盒当"病房",盒口贴 RFID 卡(301/302/303)。

1. **开机**:船型开关 → LCD"系统启动中" → 串口自检 → System Ready
2. **体征**:人偶放 Velostat 垫 → 热力图出现;手指按 MAX30102 → 心率/血氧实时跳
3. **AI 陪聊**:"小护小护" 唤醒 → 对话 → "结束聊天"
4. **语音控制 NLC**:"病床控制" → "把靠背升起来"(推杆升)→ "往前走" → "停下来" → "退出控制"
5. **自主导航**:手机 5000 端口点"寻房 302" → 循迹行驶 → 遇障停车 → RFID 匹配入房
6. **云端 AI**:Dashboard 点"🧠 AI 深度分析" → LLM 返回压力评估与护理方案;涂鸦 App/平台远程下发抬背
7. **断电安全**:关船型开关 → 手推自由滑行(TT 马达不锁死)

---

## 👤 演示账号

| 角色 | 用户名 | 密码 | 说明 |
|------|--------|------|------|
| 管理员 | admin | admin123 | 全部权限 |
| 医生 | dr_wang | doctor123 | 查看所有患者 |
| 患者 | patient_zhang | patient123 | 张建国(高位截瘫) |
| 患者 | patient_li | patient123 | 李秀芳(糖尿病) |
| 患者 | patient_wang | patient123 | 王明辉(中风后遗症) |
| 家属 | family_zhang | family123 | 张伟(张建国家属) |

> ⚠️ 公网部署后请立即修改默认密码与 `.env` 中的密钥。

---

## 🔍 常见故障速查

| 现象 | 原因 → 处理 |
|------|-------------|
| 浏览器打不开 `https://<IP>/` | 未配 TLS + 端口没开 → 用 **http://<IP>:3000**,并在阿里云安全组放行 3000 |
| 云端收不到数据 | `config.py` 的 CLOUD_SERVER/API_KEY 与云端 `.env` 不一致;`pm2 logs nursing-bed` 排查 |
| ESP32 连不上 MQTT | ESP32 与树莓派不在同一 WiFi;`config.h` 的 MQTT_BROKER 不是树莓派 IP;Mosquitto 未启动 |
| 传感器 ❌ | 杜邦线松动;VCC 误接 5V;I2C 地址扫描比对 0x57/0x5A/0x68 |
| ESP32 反复重启 (Brownout) | WiFi 峰值电流不足 → VIN-GND 并 100μF 电容;检查 LM2596 #2 |
| 树莓派闪电⚡/彩虹屏 | 供电压降 → 确认 LM2596 #1 ≥5.05V,换粗 USB-C 线 |
| 行驶时树莓派重启 | 电机冲击电流 → LM2596 #1 输入并 470μF;电池低于 10.5V 先充电 |
| 涂鸦设备不在线 | 三元组抄错;系统时间偏差过大(签名含时间戳,`sudo apt install ntpdate && sudo ntpdate ntp.aliyun.com`);8883 出方向被防火墙拦 |
| 涂鸦收不到属性 | 物模型 code 与第 7.2 表不一致(区分大小写);temperature/battery_voltage 忘了设"倍数1"(×10) |
| AI 功能全部报错 `Arrearage` | 百炼账户欠费 → 充值,或按 [TUYA_MIGRATION.md 第五步](TUYA_MIGRATION.md) 切涂鸦大模型额度;`node scripts/test_llm_gateway.js` 自测 |
| PyTorch 装不上 | `pip3 install torch --index-url https://download.pytorch.org/whl/cpu`;或不装,自动规则模式 |
| NLC 无反应 | 先说"病床控制"进入模式;检查云端 `/api/voice/device/command` 与两个 API Key |
| 更多 | 电源类见 [hardware/README.md](hardware/README.md#八电源故障排查),其余见 [DEPLOYMENT.md 常见问题](DEPLOYMENT.md#常见问题) |

---

## 📱 HarmonyOS 手机 App（harmony-app/）

医护/家属随身端，ArkTS 严格模式开发，完整 DevEco 工程随仓库分发（`oh_modules` 等由 IDE 自动重建）。

| 页面 | 功能 |
|---|---|
| DashboardPage | 实时体征仪表盘（心率/血氧/体温/血压/睡姿，2s 轮询） |
| AgentSwarmPage | 5 专科智能体总览与协同状态 |
| ChatPage | AI 护理咨询对话（走云端统一 LLM 网关） |
| AlertsPage | 告警列表与确认 |
| ControlPage | 床体控制（靠背角度/气囊减压/病房导航） |

**构建运行**：
1. DevEco Studio（HarmonyOS SDK **6.0.2(22)**，`bundleName: com.smartnursing.bed`）打开 `harmony-app/` → 首次自动同步依赖
2. 服务器地址在 [harmony-app/entry/src/main/ets/common/Constants.ets](harmony-app/entry/src/main/ets/common/Constants.ets)：`SERVER_BASE_URL` 指向云端 ECS，`PI_BASE_URL` 指向局域网树莓派（NLC 语音直控用）
3. File → Project Structure → Signing Configs 勾选自动签名 → 真机运行
4. 登录账号与 Web 端通用（见「👤 演示账号」）

---

## 📁 项目结构

```
smart-nursing-bed/
├── server.js / package.json    # Express 云端入口(端口 3000)
├── .env                        # 环境变量(需自建,见第 6.3 节)
├── db/                         # schema.sql + seed.sql → SQLite(自动初始化)
├── middleware/auth.js          # JWT 验证 + RBAC
├── routes/                     # 11 个 API 模块: auth/patients/vitals/reports/alerts/
│                               #   agents/voice/voiceStream/pressure/pressure_predict/
│                               #   reminders/emotion
├── public/                     # 前端 SPA(11 页): login/index/dashboard/digital-twin/
│                               #   reports/alerts/records/voice-chat/ai-chat/
│                               #   family-concerns/reminders
├── config/                     # ecosystem.config.js(PM2) + nginx.conf
├── DEPLOYMENT.md               # 六阶段部署细则(电源→云→ESP32→树莓派→组装→联调)
├── TUYA_MIGRATION.md           # 涂鸦云迁移方案与物模型 DP 全表
├── docs/                       # 设计文档 + 创意表(涂鸦赛道)
├── scripts/                    # 运维脚本: 智能体提示词导出/LLM网关自测/涂鸦迁移体检/讯飞ASR
├── harmony-app/                # 📱 HarmonyOS App(DevEco 工程, ArkTS, 见上节)
└── hardware/
    ├── README.md               # 完整 BOM + 接线图 + 电源详解
    ├── config.py               # ⭐ 树莓派全局配置(GPIO/MQTT/云端/涂鸦三元组)
    ├── main.py                 # 主入口 v3.0(7 步启动)
    ├── mqtt_bridge.py          # MQTT→HTTP 桥接 + TuyaLink 双链路 v2.1
    ├── tuya_link.py            # ⭐ TuyaLink 协议客户端(三元组签名/上报/下发)
    ├── test_e2e.py             # ⭐ 无硬件端到端虚拟测试
    ├── mock_publisher.py       # 模拟 ESP32 数据源
    ├── pressure_analyzer.py    # CNN/MobileNet 睡姿 + 受压 + 翻身
    ├── predictive_model.py     # 1D-CNN 受压风险预测(30min 预警)
    ├── decision_engine.py      # AI 自主决策引擎 v2.0(LLM Agent + 安全沙箱)
    ├── air_cushion.py          # 气囊自动减压控制
    ├── multimodal_fusion.py    # D-S 证据理论多模态融合
    ├── federated_learning.py   # 联邦学习 PoC(差分隐私)
    ├── blockchain.py           # 健康记录链式存证
    ├── motor_control / navigation / obstacle_avoidance / rfid_reader / bed_actuator
    ├── voice_client / camera_stream / lcd_display / web_remote
    └── esp32/                  # PlatformIO 固件(lib/ 内置全部依赖,离线可编译)
        └── src/                # config.h + main.cpp + 5 种传感器驱动 + MQTT 客户端
```

---

## ⚙️ 技术栈与 AI 能力

| 层 | 技术 |
|----|------|
| 云端 | Node.js 20 + Express 4.18,better-sqlite3(WAL),JWT + bcrypt(4 角色 RBAC),Socket.IO/WS,PM2,可选 Nginx |
| 边缘 | Python 3 + paho-mqtt + Mosquitto;PyTorch/ONNX Runtime 推理;Flask 遥控(5000);MJPEG 推流(8080) |
| 端侧 | ESP32-S3 Arduino(PlatformIO),I2C 三传感器共线,CD74HC4051 双 MUX 8×8 ADC 扫描 |
| 云-云 | TuyaLink(TLS MQTT 8883,HMAC-SHA256 三元组签名);LLM OpenAI 兼容接口;SiliconFlow ASR/TTS |

| AI 功能 | 引擎 | 位置 |
|---------|------|------|
| 睡姿分类(6 类) | PostureCNN 15K / PostureMobileNet 45K / ONNX | 🟢 树莓派 |
| 受压风险预测 | 1D-CNN(8K 参数,30min 预警) | 🟢 树莓派 |
| 翻身检测 / 受压监测 | 帧间差异 + 规则引擎(30/60/120min 三级) | 🟢 树莓派 |
| 自主决策 | 8 条规则 + LLM Agent(安全沙箱) | 🟢 树莓派 |
| 多模态融合 | MediaPipe Pose + D-S 证据理论 | 🟢 树莓派 |
| 健康报告 / 专科咨询 / 压力深度分析 / 情绪分析 | LLM(Qwen3.5-Plus,可替换) | ☁️ 云端 |
| NLC 意图解析 | LLM → 11 种动作 JSON | ☁️ 云端 |
| ASR / TTS | TeleSpeechASR / CosyVoice2 | ☁️ SiliconFlow |

**5 种专科 AI Agent**(`agent_configs` 表,独立提示词 + 个性化阈值):🦽 高位截瘫 · 💉 糖尿病 · 🧠 中风后遗症 · 🫁 慢阻肺 · 🏥 通用护理

---

## 🔌 API 接口文档

认证:用户端 `Authorization: Bearer <JWT>`;设备端 `X-API-Key: <你的DEVICE_API_KEY>`。

| 端点 | 方法 | 认证 | 描述 |
|------|------|------|------|
| /api/auth/login · /register | POST | 无 | 登录(返回 JWT)/ 注册 |
| /api/patients | GET | JWT | 患者列表 |
| /api/vitals | POST | API-Key | 设备体征上报(自动阈值告警) |
| /api/vitals/:id · /latest · /stats | GET | JWT | 体征历史 / 最新 / 统计 |
| /api/reports/:id · /generate | GET/POST | JWT | AI 健康报告 |
| /api/alerts | GET | JWT | 预警列表(状态流转) |
| /api/agents · /consult | GET/POST | JWT | 专科 Agent 咨询 |
| /api/pressure/analyze · /history/:id | POST/GET | JWT | AI 压力深度分析 / 历史 |
| /api/voice/chat | POST | JWT | Web 文本聊天 |
| /api/voice/device/chat · /command · /tts | POST | API-Key | 设备语音全流程 / **NLC 控制** / TTS |
| /api/voice/concerns/:id · /generate/:id | GET/POST | JWT | 家属关注点分析 |

上报示例见 [第 6.4 节](#64-验证);语音/NLC 示例见 [DEPLOYMENT.md](DEPLOYMENT.md)。

---

## 📚 相关文档

| 文档 | 内容 |
|------|------|
| [hardware/README.md](hardware/README.md) | 完整 BOM 报价表、接线图、Velostat 制作、电源系统详解与故障排查 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | 六阶段部署手册(含每个模块的单测代码段、Demo 话术) |
| [TUYA_MIGRATION.md](TUYA_MIGRATION.md) | 涂鸦云迁移全案:TuyaLink 协议、物模型 DP 全表、路线图 |

---

## 📜 许可证与致谢

课程设计/竞赛作品(2026 全国大学生物联网设计竞赛·涂鸦智能赛道),仅供学术研究与教学演示。

感谢:[Tuya 涂鸦智能](https://platform.tuya.com/) · [阿里云百炼](https://bailian.console.aliyun.com/) · [SiliconFlow](https://siliconflow.cn/) · [PyTorch](https://pytorch.org/) · [Express](https://expressjs.com/) · [Mosquitto](https://mosquitto.org/) · [Three.js](https://threejs.org/) · [Chart.js](https://www.chartjs.org/)
