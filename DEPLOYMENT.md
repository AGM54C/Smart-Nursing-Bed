# 📖 智能护理病床 - 完整部署指南

从拆箱到演示的全流程指南。按顺序执行即可。

---

## 目录

0. [第零阶段：电源系统搭建](#第零阶段电源系统搭建)
1. [第一阶段：云端部署](#第一阶段云端部署)
2. [第二阶段：ESP32-S3 传感器节点](#第二阶段esp32-s3-传感器节点)
3. [第三阶段：树莓派主控](#第三阶段树莓派主控)
4. [第四阶段：机械组装](#第四阶段机械组装)
5. [第五阶段：联调测试](#第五阶段联调测试)
6. [第六阶段：Demo 演示](#第六阶段demo-演示)
7. [常见问题](#常见问题)

---

## 第零阶段：电源系统搭建

> ⚡ **先把电源搞定，后续所有硬件调试都需要稳定供电。** 完整电源原理详见 [hardware/README.md](hardware/README.md) 的「电源系统详解」章节。

### 0.1 准备物料

你需要以下电源相关物料（完整硬件清单见 [hardware/README.md](hardware/README.md)）：

| 物料 | 规格 | 数量 | 淘宝搜索关键词 |
|------|------|------|----------------|
| 锂电池组 | 12V 3S ≥5000mAh, **DC 5.5×2.1mm公头** | 1 | "12V锂电池 DC头 5000mAh" |
| 充电器 | 12.6V 2A, DC5.5×2.1mm插头 | 1 | "12.6V锂电池充电器 DC头" |
| DC母座转接板 | 5.5×2.1mm 母座→螺丝端子 | 1 | "DC母座 螺丝端子" |
| LM2596降压模块 | 可调型 (输入7-35V) | 3 | "LM2596降压模块" |
| 船型开关 | KCD1 两脚 | 1 | "船型开关" |
| USB-C供电线 | 带裸线头 | 1 | "USB-C 供电线 裸线" |
| 万用表 | 任意 | 1 | 用于调压 |

> 💡 **DC头电池选购要点**：搜索 "12V锂电池 DC5.5 2.1 5000mAh"，买带保护板的成品电池组（黑色塑料壳，一端DC圆口）。很多店铺有电池+充电器套餐，DC口通用，充电器插入电池DC口即可充电。**不要买航模XT60/T插口的电池**！

### 0.2 LM2596 调压 (⚠️ 最关键步骤)

```bash
# 在接任何设备之前，必须先把三个 LM2596 的输出调到 5V！
# 出厂默认输出可能是 12V，直接接树莓派/ESP32 会烧毁！

步骤:
1. 将电池DC头插入DC母座转接板
2. 转接板正极 → LM2596 IN+
   转接板负极 → LM2596 IN-
3. 打开万用表，调到直流电压 (V DC) 档
4. 红表笔接 LM2596 OUT+，黑表笔接 OUT-
5. 用小一字螺丝刀旋转蓝色电位器:
   逆时针 = 降压 / 顺时针 = 升压
6. 精确调到 5.10V ± 0.05V
7. 用马克笔标记: #1=树莓派 / #2=ESP32 / #3=气囊
8. 三个LM2596都重复以上步骤
```

### 0.3 接线总装

```
电池DC头 → DC母座转接板 → 船型开关 → 12V正极总线
                                           ├→ L298N #1 (12V, 前轮: 左前 ChA + 右前 ChB)
                                           ├→ L298N #2 (12V, 后轮: 左后 ChA + 右后 ChB)
                                           ├→ L298N #3 (12V, 推杆: ChA接推杆, ChB空置)
                                           ├→ LM2596 #1 IN+ → OUT+(5V) → USB-C线 → 树莓派
                                           ├→ LM2596 #2 IN+ → OUT+(5V) → 面包板 → ESP32 VIN
                                           └→ LM2596 #3 IN+ → OUT+(5V) → 气囊系统独立供电

气囊减压系统供电 (LM2596 #3 独立供电, 继电器开关控制):
  LM2596 #3 OUT+(5V) → 3路继电器模块 VCC
  GND总线 (端子排)   → 继电器模块 GND
  树莓派 GPIO3       → 继电器 IN1 (气泵)
  树莓派 GPIO14      → 继电器 IN2 (左电磁阀)
  树莓派 GPIO15      → 继电器 IN3 (右电磁阀)
  继电器 COM (3路)   → LM2596 #3 OUT+(5V)
  继电器 NO1/NO2/NO3 → 气泵/左电磁阀/右电磁阀 正极
  气泵/电磁阀 负极   → GND总线 (端子排)

DC母座转接板 负极 → GND总线 (所有GND互连)
```

> ⚠️ **共地 (Common Ground)**
>
> 你使用的 2进12出 配电端子排已经将所有 GND 连通（端子排内部金属条互连），
> 所以 LM2596 #1/#2/#3、树莓派、ESP32、L298N、继电器模块的 GND 天然共地。
> 只需确保所有负极线都接入端子排的 GND 列即可，无需额外跑线。

**树莓派供电方法（二选一）：**

```
方案A (推荐): USB-C供电线
  LM2596 #1 OUT+ → USB-C线红线
  LM2596 #1 OUT- → USB-C线黑线
  USB-C头 → 树莓派供电口

方案B (进阶): GPIO直供
  LM2596 #1 OUT+ → GPIO Pin 2/4 (5V)
  LM2596 #1 OUT- → GPIO Pin 6 (GND)
  ⚠️ 绕过保险丝，必须确保5V精确
```

**ESP32-S3供电：**

```
  LM2596 #2 OUT+ → 面包板正极轨 → ESP32 VIN引脚
  LM2596 #2 OUT- → 面包板负极轨 → ESP32 GND引脚
  传感器3.3V ← ESP32 3V3引脚 (不要直接接5V!)
```

### 0.4 气囊减压系统物料 (单独采买清单)

| 物料 | 规格 | 数量 | 淘宝搜索关键词 | 参考价 |
|------|------|------|----------------|--------|
| LM2596降压模块 | 可调型 (输入7-35V) | 1 | "LM2596降压模块" | ¥3 |
| 3路继电器模块 | 5V 光耦隔离 低电平触发 | 1 | "3路继电器模块 5V" | ¥5 |
| 微型气泵 | DC 3-6V, 带进出气嘴 | 1 | "微型真空气泵 充气 5V" | ¥8-15 |
| 电磁阀 | DC 5V 二位二通 常闭 | 2 | "微型电磁阀 5V 常闭" | ¥5/个 |
| PU气管 | 外径4mm | 1米 | "PU气管 4mm" | ¥1/米 |
| T型三通接头 | 4mm 快插 | 1 | "气管三通 4mm" | ¥1 |
| 气囊 | 硅胶/TPU 可充气 | 2 | "充气气囊 硅胶垫" | ¥5/个 |

> 💡 **合计约 ¥35 以内**。继电器模块内置续流二极管和光耦隔离，杜邦线直接插，不需要焊接。

### 0.5 通电前检查清单

```
□ LM2596 #1 输出已调到 5.10V (万用表确认) → 树莓派
□ LM2596 #2 输出已调到 5.10V (万用表确认) → ESP32
□ LM2596 #3 输出已调到 5.10V (万用表确认) → 气囊系统
□ 船型开关处于关闭状态
□ 所有GND已互连 (端子排2进12出, 天然共地)
□ USB-C供电线正负极无反接
□ 传感器接的是3.3V不是5V
□ 12V线没有短路 (万用表测正负极阻值应>1kΩ)
□ 继电器模块 VCC/GND 接 LM2596 #3 (不是树莓派)
□ 气囊系统由 LM2596 #3 独立供电 (不是从树莓派取电)
```

### 0.6 首次通电测试

```bash
1. 打开船型开关
2. 检查:
   ✅ 树莓派红色LED亮起 (5V供电正常)
   ✅ ESP32板载LED亮 (供电正常)
   ✅ L298N板载LED亮 (12V正常)
   ✅ 没有任何元件发烫 (等10秒确认)
3. 如果任何异常，立即关闭船型开关!
```

### 0.7 充电方法

```
1. 关闭船型开关
2. 把12.6V充电器的DC头直接插入电池的DC口
   (电池充电口和放电口是同一个DC 5.5×2.1mm口)
3. 红灯 = 充电中 / 绿灯 = 充满
4. 约2-3小时充满，充满后拔掉充电器
```

> 📝 **续航参考**：5000mAh电池行驶约1.7h，静止监测约4h，Demo演示2-3h足够。

✅ **电源系统完成**。后续所有硬件调试都用电池+船型开关上电。

---

## 第一阶段：云端部署

> 先把云端跑起来，后续硬件有数据可以直接看效果。

### 1.1 准备服务器

- 阿里云/腾讯云 ECS，最低 1核2G，Ubuntu 20.04+
- 开放端口：**3000** (API) 和 **80/443** (Nginx，可选)
- 阿里云操作路径：ECS 控制台 → 实例 → 安全组 → 配置规则 → **入方向手动添加** TCP 3000，授权对象 0.0.0.0/0（不放行则外网无法访问，浏览器请用 `http://IP:3000` 而非 https）

### 1.2 安装 Node.js

```bash
ssh root@<你的服务器IP>

# 安装 Node.js 20 (国内 npmmirror 镜像, 免翻墙, 实测可用)
wget https://registry.npmmirror.com/-/binary/node/v20.19.0/node-v20.19.0-linux-x64.tar.xz
tar -xf node-v20.19.0-linux-x64.tar.xz -C /usr/local --strip-components=1
npm config set registry https://registry.npmmirror.com

# 验证
node -v   # v20.19.0
npm -v    # 10.x.x
```

### 1.3 上传代码

```bash
# 方法1: SCP (从你的电脑)
scp -r smart-nursing-bed/ root@<服务器IP>:/opt/

# 方法2: Git
ssh root@<服务器IP>
cd /opt && git clone <你的仓库地址> smart-nursing-bed
```

### 1.4 安装依赖 & 配置

```bash
cd /opt/smart-nursing-bed
npm install --omit=dev

# 编辑环境变量
nano .env
```

`.env` 文件内容：
```env
PORT=3000
JWT_SECRET=用openssl-rand--hex-32生成的随机串
DEVICE_API_KEY=<你的DEVICE_API_KEY>

# ── 统一 LLM 网关 (services/llm.js) ──
# 降级链: 涂鸦智能体 → Moonshot kimi-k3 → SiliconFlow (上级失败自动降级, 演示不中断)
LLM_PROVIDER=tuya
# 第二级 主力 kimi-k3 (K2.5 已下架; platform.kimi.com 申请, K3 需充值; 不填则跳过本级):
MOONSHOT_API_KEY=
MOONSHOT_MODEL=kimi-k3
MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
# 第三级 保底 SiliconFlow (KIMI_* 为历史变量名):
KIMI_API_KEY=sk-xxxxxxxxxxxxxxxx
KIMI_MODEL=deepseek-ai/DeepSeek-V3
KIMI_BASE_URL=https://api.siliconflow.cn/v1
VOICE_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
# 第一级 涂鸦智能体 (云项目授权密钥, 完整说明见 TUYA_MIGRATION.md 第五步):
# TUYA_ACCESS_ID=
# TUYA_ACCESS_SECRET=
# TUYA_AGENT_ID=
# TUYA_AGENT_ID_QUADRIPLEGIA= / _DIABETES= / _POST_STROKE= / _COPD= / _GENERAL=

SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxxxx
```

> ⚠️ `MOONSHOT_API_KEY` 从 [platform.kimi.com](https://platform.kimi.com/console/api-keys) 获取，kimi-k3 需充值解锁（新用户代金券不适用）  
> ⚠️ `KIMI_API_KEY`/`SILICONFLOW_API_KEY` 从 [siliconflow.cn](https://siliconflow.cn) 获取  
> 💡 配置后可用 `node scripts/test_llm_gateway.js` 一键自测 LLM 是否可用

### 1.5 启动服务

```bash
# 安装 PM2
npm install -g pm2

# 启动
pm2 start config/ecosystem.config.js
pm2 save
pm2 startup    # 开机自启

# 查看状态
pm2 status
pm2 logs
```

### 1.6 配置 Nginx (可选但推荐)

```bash
sudo apt install nginx
sudo cp config/nginx.conf /etc/nginx/sites-available/smartnursingbed
sudo ln -s /etc/nginx/sites-available/smartnursingbed /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 1.7 验证云端

```bash
# 浏览器访问
http://<服务器IP>:3000

# 用 admin / admin123 登录

# 测试设备数据上报
curl -X POST http://<服务器IP>:3000/api/vitals \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <你的DEVICE_API_KEY>" \
  -d '{"patient_id":1,"heart_rate":72,"blood_oxygen":96,"temperature":36.5,"sleep_posture":"supine"}'
# 应返回 {"message":"Vitals recorded","id":...}
```

✅ **云端完成**。留着这个终端，后面要用。

---

## 第二阶段：ESP32-S3 传感器节点

> 在你的PC上操作(Windows/Mac均可)，不是在树莓派上。

### 2.1 安装开发环境

```bash
# 方法1: 命令行 (推荐)
pip install platformio

# 方法2: VSCode扩展
# 安装 PlatformIO IDE 扩展
```

### 2.2 修改配置

编辑 `hardware/esp32/src/config.h`：

```cpp
// 改成你的WiFi
#define WIFI_SSID      "你的WiFi名"
#define WIFI_PASSWORD  "你的WiFi密码"

// 改成树莓派的IP (后面第三阶段确定后再填)
#define MQTT_BROKER    "192.168.x.x"
```

### 2.3 接线传感器

按 [hardware/README.md](hardware/README.md) 的接线图，用**面包板+杜邦线**连接：

```
步骤1: I2C总线 (面包板上3个传感器并联)
  ESP32-S3 GPIO2 (SDA) → 面包板某行 → MAX30102/MLX90614/MPU6050 SDA
  ESP32-S3 GPIO1 (SCL) → 面包板某行 → MAX30102/MLX90614/MPU6050 SCL
  ESP32-S3 3.3V        → 面包板某行 → 三个传感器 VCC
  ESP32-S3 GND         → 面包板某行 → 三个传感器 GND

步骤2: MUX + Velostat压力矩阵
  GPIO39/40/41 → MUX1 S0/S1/S2
  GPIO42/21/47 → MUX2 S0/S1/S2
  GPIO4        → 列MUX COM (通过10kΩ下拉)
  GPIO48       → 行MUX SIG

步骤3: 脉搏传感器
  GPIO5        → HK-2000B+ 信号输出

步骤4: 电池监测 (可后续再接)
  GPIO6        → 100kΩ/33kΩ分压器中点
```

### 2.4 烧录固件

```bash
# USB-C 连接 ESP32-S3 到电脑
cd hardware/esp32

# 编译+烧录
pio run -t upload
# 如果失败: 按住 BOOT 键 → 按一下 RST 键 → 松开 BOOT → 重试

# 打开串口监视器
pio device monitor
```

你应该看到：
```
╔══════════════════════════════════════════╗
║  🛏️ 智能护理病床 - ESP32传感器节点        ║
╚══════════════════════════════════════════╝
[I2C] Bus initialized
─── Initializing sensors ───
─── Sensor Status ───
  MAX30102 (HR/SpO2): ✅
  MLX90614 (Temp):    ✅
  MPU6050 (Posture):  ✅
  Pressure Mat:       ✅
  Pulse (BP):         ✅ (HK-2000B+ Estimated)
```

> 如果某个传感器显示 ❌，检查接线是否松动。

✅ **ESP32-S3 完成**。先不用管MQTT连接失败，等树莓派就绪后自动连接。

---

## 第三阶段：树莓派主控

### 3.1 系统准备

```bash
# 1. 用 Raspberry Pi Imager 烧录系统到TF卡
#    选择: Raspberry Pi OS (64-bit) with Desktop
#    设置: 用户名=pi, 密码=你的密码, WiFi, SSH启用
#    https://www.raspberrypi.com/software/

# 2. 插入TF卡，接网线或WiFi，上电开机

# 3. SSH 连接
ssh pi@<树莓派IP>
```

### 3.2 启用外设

```bash
sudo raspi-config
# → Interface Options → SPI → Enable     (RFID需要)
# → Interface Options → Camera → Enable  (CSI摄像头)
# → Finish → 重启
```

### 3.3 安装 Mosquitto MQTT Broker

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y mosquitto mosquitto-clients

# 启动并设为开机自启
sudo systemctl enable mosquitto
sudo systemctl start mosquitto

# 验证
mosquitto_sub -t "test" &
mosquitto_pub -t "test" -m "hello"
# 应看到 "hello" 输出
kill %1   # 停止后台订阅
```

### 3.4 安装 Python 依赖

```bash
sudo apt install -y python3-pip python3-pyaudio python3-rpi.gpio mpg123

# 上传代码到树莓派
# 从你的电脑:
scp -r smart-nursing-bed/ pi@<树莓派IP>:/home/pi/

# 在树莓派上:
cd /home/pi/smart-nursing-bed/hardware
pip3 install -r requirements.txt
```

> 📝 **PyTorch安装注意**：RPi4B上安装PyTorch可能较慢(10-20分钟)，耐心等待。如果安装失败，系统会自动降级为规则模式，不影响其他功能。

### 3.5 修改配置

```bash
nano /home/pi/smart-nursing-bed/hardware/config.py
```

修改以下行：
```python
CLOUD_SERVER = "http://<你的云端服务器IP>:3000"
DEVICE_API_KEY = "<你的DEVICE_API_KEY>"    # 与云端.env一致
PATIENT_ID = 1

# 涂鸦云 TuyaLink 配置 (可选, 在 platform.tuya.com 拿到三元组后启用)
TUYA_ENABLED = True  # 改为 False 则禁用涂鸦云
TUYA_PRODUCT_ID = "YOUR_PRODUCT_ID"
TUYA_DEVICE_ID = "YOUR_DEVICE_ID"
TUYA_DEVICE_SECRET = "YOUR_DEVICE_SECRET"
```

> ℹ️ **涂鸦云配置步骤**: 登录 [platform.tuya.com](https://platform.tuya.com) → 创建产品（智能化方式选**「生态设备接入」**即 TuyaLink）→ 功能定义（物模型 DP 表见 [TUYA_MIGRATION.md](TUYA_MIGRATION.md)）→ 添加设备获取三元组 → 填入 config.py。不启用涂鸦云不影响其他功能。

### 3.6 更新 ESP32 的 MQTT Broker 地址

现在你知道了树莓派的IP，回到PC上修改 `config.h`：
```cpp
#define MQTT_BROKER    "192.168.x.x"  // 树莓派的IP
```
重新烧录：`pio run -t upload`

### 3.7 训练AI模型 (推荐)

```bash
cd /home/pi/smart-nursing-bed/hardware

# 训练 MobileNetV3-style 模型 (推荐, ~45K参数)
python3 pressure_analyzer.py train
# 约60秒完成, 生成 posture_mobilenet.pth + posture_mobilenet.onnx

# 训练受压风险预测模型 (🆕 创新点: 预测性护理)
python3 predictive_model.py train
# 约30秒完成, 生成 predictive_risk.pth (~8K参数)

# 模型性能对比
python3 pressure_analyzer.py benchmark
python3 predictive_model.py benchmark
```

> 📝 系统自动选择最佳模型: ONNX Runtime > MobileNet > CNN > 规则回退

### 3.8 准备 RFID 病房卡

```bash
python3 rfid_reader.py write
# 按提示将白卡放到RC522上
# 输入房间号: 301  → 写入
# 输入房间号: 302  → 写入
# 输入房间号: 303  → 写入
```

### 3.9 启动系统

```bash
cd /home/pi/smart-nursing-bed/hardware
python3 main.py
```

你应该看到：
```
╔══════════════════════════════════════════════╗
║  🛏️  智能护理病床 · 树莓派主控 v3.0          ║
║  [LLM Agent + 预测性护理 + 气囊减压]         ║
║  Tuya: Enabled                                 ║
╚══════════════════════════════════════════════╝

─── [1/7] Starting MQTT Bridge + TuyaLink ───
[MQTT Bridge] Connected to Mosquitto
[TuyaLink] ✅ Connected to Tuya Cloud (m1.tuyacn.com:8883)
─── [2/7] Initializing Hardware ───
  ✅ Navigator ready
  ✅ Actuator ready
  ✅ Air Cushion ready
─── [3/7] Starting AI Decision Engine v2.0 ───
  ✅ Decision Engine v2.0 ready (LLM + Predictive + AirCushion)
─── [4/7] Starting Web Remote Control ───
[Web] Remote control at http://0.0.0.0:5000
─── [5/7] Starting Camera Stream ───
[Camera] Stream at http://0.0.0.0:8080/stream
─── [6/7] Voice Client ───
  ✅ Voice client started
─── [7/7] LCD Display ───
[LCD] Display started (1fps)

═══════════════════════════════════════════════
  ✅ System Ready!
  🌐 Web Remote:  http://<RPi-IP>:5000
  📹 Camera:      http://<RPi-IP>:8080/stream
  📡 MQTT Broker:  localhost:1883
  ☁️  Cloud API:   http://<你的服务器>:3000
  🔗 Tuya:        ✅ Connected
  🧠 AI Engine:   DecisionEngine v2.0 + LLM Agent
  🔮 Prediction:  1D-CNN Risk Forecasting
  🫧 AirCushion:  Active
  🔗 Blockchain:  HealthChain active
═══════════════════════════════════════════════
```

### 3.10 设为开机自启 (可选)

```bash
sudo nano /etc/systemd/system/smart-bed.service
```

写入：
```ini
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
```

```bash
sudo systemctl enable smart-bed
sudo systemctl start smart-bed
```

✅ **树莓派完成**。

---

## 第四阶段：机械组装

### 4.1 底盘组装

```
1. 组装4WD小车底盘 (按套件说明书)
   - 安装4个TT马达 → 轮子
   - 底板固定

2. 安装L298N驱动板 (×3)
   - L298N #1: 螺丝固定在底盘上层（前轮驱动）
   - L298N #2: 固定在#1旁边（后轮驱动）
   - L298N #3: 靠近推杆位置固定（推杆独立驱动）

3. 连接电机线 (树莓派 GPIO BCM 编号)

   | 电机     | L298N | 方向引脚           | EN引脚    | 输出端子  |
   |----------|-------|--------------------|-----------|-----------|
   | 左前轮   | #1 ChA | IN1=GPIO17, IN2=GPIO27 | ENA=GPIO12 | OUT1/OUT2 |
   | 右前轮   | #1 ChB | IN3=GPIO22, IN4=GPIO23 | ENB=GPIO16 | OUT3/OUT4 |
   | 左后轮   | #2 ChA | IN1=GPIO5,  IN2=GPIO6  | ENA=GPIO11 | OUT1/OUT2 |
   | 右后轮   | #2 ChB | IN3=GPIO9,  IN4=GPIO10 | ENB=GPIO2  | OUT3/OUT4 |
   | 电动推杆 | #3 ChA | IN1=GPIO13, IN2=GPIO19 | ENA=GPIO26 | OUT1/OUT2 |

   ⚠️ 所有L298N的 VSS(5V逻辑) 接树莓派 5V（Pin 2/4）
   ⚠️ 所有L298N的 GND 必须与树莓派 GND 共地
   ⚠️ L298N #3 的 OUT3/OUT4 (Channel B) 悬空不接
```

### 4.2 传感器安装

```
4. ESP32-S3 + 面包板
   - 用双面胶/铜柱固定在底盘上层
   - 各传感器通过杜邦线连接 (已在第二阶段接好)

5. 超声波 HC-SR04 (×3)
   - 前方: 用热熔胶固定在底盘前端
   - 左侧/右侧: 固定在底盘两侧

6. 循迹模块 (5路TCRT5000)
   - 安装在底盘底部前端, 距地面 1-2cm

7. RFID RC522
   - 安装在底盘侧面, 天线朝外
```

### 4.3 上层安装

```
8. 树莓派4B
   - 铜柱固定在底盘最上层
   - 接CSI摄像头排线
   - 接SPI LCD屏幕
   - 接USB麦克风
   - 接PAM8403功放 → 喇叭

9. 电动推杆
   - 固定在底盘边缘
   - 推杆上方放置一个小平台 (用于放玩具小人)

10. Velostat压力矩阵
    - 放在推杆平台上
    - MUX通过杜邦线连接到ESP32

11. 电源 (详见 [第零阶段：电源系统搭建](#第零阶段电源系统搭建))
      - 12V DC头锟电池固定在底盘下层 (配重)
      - DC母座转接板用螺丝固定在底盘边缘
      - 船型开关安装在侧面, 方便手指操作
      - LM2596 #1 (标记好) 固定在底盘上, 5V→USB-C→树莓派
      - LM2596 #2 固定在面包板旁, 5V→面包板→ESP32+传感器
      - 所有12V/GND线汇聚到接线端子排, 用扎带整理走线

12. 🆕 气囊减压系统
      - LM2596 #3 固定在底盘上 (专供气囊, 已调5V)
      - 3路继电器模块固定在 LM2596 #3 旁 (杜邦线直插)
      - LM2596 #3 OUT+ → 继电器 VCC + COM (3路)
      - LM2596 #3 OUT- → 继电器 GND → GND总线 (端子排)
      - 树莓派 GPIO3/14/15 → 继电器 IN1/IN2/IN3 (仅信号线)
      - 继电器 NO1/NO2/NO3 → 气泵/左电磁阀/右电磁阀正极
      - 气泵/电磁阀负极 → GND总线 (端子排)
      - PU气管连接: 气泵 → T型三通 → 左电磁阀 → 左气囊
                              → 右电磁阀 → 右气囊
      - 气囊铺在推杆平台/床垫下方, 分左右两区
```

---

## 第五阶段：联调测试

### 5.1 分模块测试

```bash
# 在树莓派上执行

# 1. MQTT链路测试
mosquitto_sub -h localhost -t "bed/#" -v
# 另开终端, 看ESP32是否在发数据。应看到 bed/vitals, bed/pressure_mat 等

# 2. 云端连通测试
curl -X POST http://<云端IP>:3000/api/vitals \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <你的DEVICE_API_KEY>" \
  -d '{"patient_id":1,"heart_rate":72,"blood_oxygen":96}'

# 3. 电机测试
python3 -c "
from motor_control import MotorController
m = MotorController()
m.forward(50)  # 前进,速度50%
import time; time.sleep(2)
m.stop()
m.cleanup()
"

# 4. RFID测试
python3 rfid_reader.py
# 把写好的RFID卡靠近RC522, 应显示房间号

# 5. 超声波测试
python3 -c "
from obstacle_avoidance import ObstacleAvoidance
oa = ObstacleAvoidance()
oa.start()
import time; time.sleep(3)
d = oa.get_distances()
print(f'前方:{d[\"front\"]}cm 左:{d[\"left\"]}cm 右:{d[\"right\"]}cm')
oa.stop()
oa.cleanup()
"

# 6. 推杆测试
python3 -c "
from bed_actuator import BedActuator
a = BedActuator()
a.raise_bed()
import time; time.sleep(3)
a.stop()
a.lower_bed()
time.sleep(3)
a.stop()
a.cleanup()
"

# 7. 摄像头测试
python3 camera_stream.py
# 浏览器打开 http://<树莓派IP>:8080/stream

# 7. 🆕 气囊减压测试
python3 air_cushion.py cycle
# 应看到气泵启动/停止, 气囊交替充放气 (约22s)

# 8. Web遥控测试
# 手机浏览器打开 http://<树莓派IP>:5000
# 测试方向键、导航、升降
```

### 5.2 全链路验证

```bash
# 启动完整系统
python3 main.py

# 在云端Dashboard (http://<云端IP>:3000, 用admin登录) 检查:
# ✅ 心率数据实时更新
# ✅ 压力热力图有颜色变化
# ✅ 睡姿显示 (MobileNet AI推理)
# ✅ 数字孪生3D页面 (/digital-twin.html) 正常显示
# ✅ AI自主决策引擎日志正常
```

---

## 第六阶段：Demo 演示

### 6.1 场景搭建

```
桌面/地面:
  1. 用黑色电工胶带贴出"走廊"路线 (宽度约3cm)
  2. 路线岔口处放置纸盒模拟"病房"
  3. 每个纸盒门口贴一张RFID卡 (301/302/303)
```

### 6.2 5分钟演示流程

```
1. 开机 (翻开船型开关)
   → LCD屏显示"系统启动中..."
   → 串口打印传感器自检 ✅
   → "System Ready!"

2. 传感器演示
   → 把玩具小人放在Velostat垫上
   → 云端Dashboard出现压力热力图
   → 手指放上MAX30102 → 心率/血氧实时跳动

3. 语音陪聊演示
   → 对麦克风说"小护小护" → 进入陪聊模式
   → 说"你好" → AI从喇叭回复
   → 说"结束聊天" → 退出陪聊模式

3.5 语音控制演示 (NLC)
   → 对麦克风说"病床控制" → 进入语音控制模式
   → 说"把靠背升起来" → AI回复"好的，靠背正在升起" + 推杆自动升起
   → 说"停" → 推杆停止
   → 说"往前走" → 小车前进
   → 说"停下来" → 小车停止
   → 说"退出控制" → 退出语音控制模式

4. 导航演示
   → 手机打开 http://<RPi-IP>:5000
   → 点击"RFID寻房" → 输入"302"
   → 小车启动 → 沿黑线行驶
   → 遇障碍物自动停 → 移除障碍 → 继续
   → 到达302 → RFID匹配 → 右转进入 → 停车

5. 推杆演示
   → 手机点"↑ 靠背升" → 推杆升起
   → 点"↓ 靠背降" → 推杆放平

6. 断电手推演示
   → 关闭船型开关
   → 手推小车自由滑行 (TT马达不锁定)

7. AI分析演示
   → 云端Dashboard点击"🧠 AI深度分析"
   → Kimi AI返回压力分布评估+护理建议
```

---

## 常见问题

### Q: ESP32连不上MQTT
```bash
# 检查树莓派Mosquitto是否运行
sudo systemctl status mosquitto

# 检查防火墙
sudo ufw allow 1883

# 检查ESP32 config.h 中 MQTT_BROKER 是否是树莓派IP
# ESP32和树莓派必须在同一个WiFi网络下
```

### Q: 传感器显示 ❌
```
1. 检查杜邦线是否插紧
2. I2C设备扫描: 在ESP32串口看地址是否匹配
3. 确认传感器VCC接的是3.3V (不是5V!)
```

### Q: 云端收不到数据
```bash
# 1. 检查MQTT Bridge是否运行
mosquitto_sub -h localhost -t "bed/#" -v
# 应看到ESP32发送的数据

# 2. 检查config.py中CLOUD_SERVER地址是否正确
# 3. 检查DEVICE_API_KEY是否与云端.env一致
# 4. 检查云端服务是否运行: pm2 status
```

### Q: PyTorch安装失败
```bash
# RPi4B上PyTorch安装可能较慢或失败
# 解决方案1: 使用pip wheel
pip3 install torch --index-url https://download.pytorch.org/whl/cpu

# 解决方案2: 不安装
# 系统自动降级为规则模式判断睡姿，不影响其他功能
```

### Q: LCD不显示
```bash
# 3.5寸SPI LCD需要在/boot/config.txt中添加overlay
# 具体配置取决于LCD型号，参考LCD附带的说明书
# 通常需要:
sudo nano /boot/config.txt
# 添加: dtoverlay=waveshare35a  (或对应型号)
# 重启
```

### Q: 摄像头不工作
```bash
# CSI摄像头
libcamera-hello    # 测试能否显示画面

# USB摄像头
ls /dev/video*     # 检查设备
python3 -c "import cv2; print(cv2.VideoCapture(0).isOpened())"
```

### Q: 树莓派启动后出现闪电符号 ⚡ 或彩虹屏
```
原因: LM2596输出电压不够或线材太细导致压降
解决:
1. 万用表测 LM2596 #1 的 OUT+ 和 OUT-，确认 ≥5.05V
2. 如果电压够但仍报警：更换更粗的USB-C线(至少22AWG)
3. 尝试GPIO Pin 2/4供电方案 (绕过USB-C线损)
4. 减少树莓派负载: 临时拔掉LCD/摄像头/USB麦克风测试
```

### Q: ESP32反复重启 (Brownout detector was triggered)
```
原因: 5V供电瞬间电流不足(WiFi发射时峰值电流大)
解决:
1. 在ESP32的VIN和GND之间焊一个 100μF/16V 电解电容
2. 检查面包板接触是否良好 (建议焊接而非杜邦线)
3. 确认LM2596 #2没有同时给太多设备供电
4. 将ESP32和传感器用独立的LM2596供电
```

### Q: 电池充不进电 / 充电灯不亮
```
1. 确认充电器是 12.6V (不是12V) 的DC头充电器
2. 检查电池DC口是否有异物，清洁接触面
3. 用万用表测电池电压:
   <3V → 电池过放，保护板锁定，需要专用修复充电器
   9-12V → 正常范围，重新插拔充电器
   >12.6V → 已满电
4. 拿另一个DC设备测试充电器是否有输出
```

### Q: 行驶时树莓派断电重启
```
原因: 电机启动瞬间电流冲击导致电池电压瞬降
解决:
1. 在LM2596 #1 输入端并联 470μF/25V 电解电容 (缓冲电压波动)
2. 检查电池是否电量不足 (电压<10.5V时应充电)
3. 12V总线加装接线端子排，减少接触电阻
4. 如果经常出现：考虑树莓派独立供电(充电宝)
```

### Q: NLC 语音控制没有反应
```
1. 确认已进入控制模式：先说"病床控制"，终端应显示"进入【语音控制】模式"
2. 检查云端 API 是否正常：
   curl -X POST http://<云端IP>:3000/api/voice/device/command \
     -H "X-Device-Key: <你的DEVICE_API_KEY>" \
     -F "audio=@test.wav" -F "patient_id=1"
3. 检查本地 Flask 是否运行：curl http://localhost:5000/api/status
4. 确认 KIMI_API_KEY 和 SILICONFLOW_API_KEY 配置正确
```
