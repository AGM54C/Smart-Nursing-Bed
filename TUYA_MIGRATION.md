# 🍄 涂鸦赛道迁移指南 (华为 IoTDA → 涂鸦 AI 云)

> 2026 全国大学生物联网设计竞赛 · 涂鸦智能赛道。
> 代码迁移已完成(见文末改动清单),本文档是**你需要手动完成的平台配置与部署步骤**。

---

## 架构变化一览

```
迁移前: ESP32-S3 ──LAN MQTT──> 树莓派 ──HTTP──> 阿里云ECS(已过期) ──× 华为IoTDA(占位,从未接通)
迁移后: ESP32-S3 ──LAN MQTT──> 树莓派 ──HTTP──> 新ECS(成都 2核2G)
                                  └──TuyaLink TLS MQTT──> 涂鸦AI云 (属性上报+命令下发+App面板)
```

ESP32 固件**无需任何改动**(它只连局域网 Mosquitto)。树莓派新增涂鸦直连,作为 TuyaLink 网关设备。

---

## 第一步:新 ECS 部署云平台 (Ubuntu 22.04)

```bash
# SSH 登录新服务器后:
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs git
sudo npm i -g pm2

# 上传项目 (本机 PowerShell, 替换 <ECS_IP>):
#   scp -r D:\IOT\smart-nursing-bed root@<ECS_IP>:/opt/

cd /opt/smart-nursing-bed
npm install
# 编辑 .env: 确认 PORT=3000, 各 API key 有效
pm2 start server.js --name nursing-bed
pm2 save && pm2 startup   # 开机自启
```

**阿里云安全组必须放行**(控制台 → ECS → 安全组 → 入方向):

| 端口 | 用途 |
|---|---|
| 22 | SSH |
| 3000 | Express API + Web(或配 Nginx 后只开 80/443) |
| 80/443 | Nginx 反向代理(可选,`config/nginx.conf` 已备好) |

**部署后回填三处地址**:
1. `hardware/config.py:11` → `CLOUD_SERVER = "http://<ECS_IP>:3000"`
2. 树莓派上同步该文件
3. 浏览器访问 `http://<ECS_IP>:3000` 验证登录页

> ⚠️ 顺手把 `.env` 里的 JWT_SECRET 换掉,DashScope/SiliconFlow/讯飞 key 曾明文入库,建议全部轮换。

---

## 第二步:涂鸦平台创建产品 (拿三元组)

1. 注册/登录 [platform.tuya.com](https://platform.tuya.com)(涂鸦开发者平台,旧域名 iot.tuya.com 会跳转到此)。
2. **产品开发 → 创建产品 → 找不到品类?选"网关"或任意接近品类**(物模型全自定义,品类不严格)。
   - 智能化方式:**「生态设备接入」**(⚠️ 这就是 TuyaLink 在新版平台上的名字!**不要选"产品开发"**——那会进 TuyaOS/MCU 模组方案,列表里永远找不到 TuyaLink。已选错的在"已选智能化方式"旁点"重新选择"改过来)
   - 联网方式:WiFi(树莓派)
3. **功能定义 → 自定义功能**,按下表创建物模型(标识符必须逐字一致,代码按这些 code 上报):

### 属性 (上报)

| 标识符 code | 类型 | 取值/范围 | 说明 |
|---|---|---|---|
| `heart_rate` | value | 0–200, 单位 bpm | 心率 |
| `blood_oxygen` | value | 0–100, 单位 % | 血氧 |
| `temperature` | value | 0–500, scale=1, 单位 ℃ | 体温(上报 365 = 36.5℃) |
| `blood_pressure_sys` | value | 0–250, mmHg | 收缩压 |
| `blood_pressure_dia` | value | 0–200, mmHg | 舒张压 |
| `sleep_posture` | enum | supine / left / right / prone / sitting / empty / unknown | 睡姿(MPU6050/CNN) |
| `pressure_total` | value | 0–65535 | 压力矩阵总压值 |
| `bed_occupied` | bool | — | 是否在床 |
| `posture_ai` | enum | 同 sleep_posture | AI 识别睡姿 |
| `ulcer_risk` | enum | none / low / medium / high | 压疮风险等级 |
| `battery_voltage` | value | 0–150, scale=1, V | 电池电压(126 = 12.6V) |
| `battery_percent` | value | 0–100, % | 电量 |

### 属性 (可下发, 云端/App 面板可写)

| 标识符 code | 类型 | 范围 | 动作 |
|---|---|---|---|
| `target_bed_angle` | value | 0–60, ° | 靠背角度 → 推杆 |
| `target_room` | string | — | 目标病房号 → 自主导航 |

### 动作 (action)

| 标识符 code | 输入参数 | 说明 |
|---|---|---|
| `set_bed_angle` | `angle`: value | 设置靠背角度 |
| `emergency_stop` | — | 急停所有电机 |
| `navigate_room` | `room`: string | 导航到病房 |
| `air_decompress` | `zone`: enum(left/right/both) | 气囊减压循环 |
| `get_status` | — | 查询在线状态与体征 |

4. **硬件开发**页选 TuyaLink SDK 接入 → **设备管理 → 新建设备**,得到**设备三元组**:`productId` / `deviceId` / `deviceSecret`。
   - 比赛团队记得先领**免费平台设备接入授权码**(命题 PDF【参赛支持】,加赛事微信群申请)。

---

## 第三步:树莓派配置与联调

```bash
# 1. 同步代码到树莓派后, 编辑 hardware/config.py:
#    TUYA_ENABLED = True
#    TUYA_PRODUCT_ID / TUYA_DEVICE_ID / TUYA_DEVICE_SECRET = 三元组
#    (数据中心默认中国区 m1.tuyacn.com, 不用改)

# 2. 单测涂鸦连接 (每5秒上报一组模拟体征):
cd hardware && python3 tuya_link.py
#    平台侧: 设备管理 → 该设备应显示"在线", 设备调试可看到属性值

# 3. 跑完整桥接:
python3 mqtt_bridge.py     # 或 python3 main.py 全量启动
```

**命令下发验证**:涂鸦平台 → 设备调试 → 调用 `set_bed_angle`(angle=30) → 树莓派日志应出现 `[TuyaLink] Action: set_bed_angle → {'angle': 30}` 且推杆动作。

---

## 第四步:App 端 (替代鸿蒙 App)

产品发布后,在涂鸦平台"面板"选一个公版面板,用**涂鸦App(智能生活/Tuya Smart)扫码配网绑定**即可看到实时体征面板——这就是创意表承诺的"涂鸦 App 小程序"最小实现,零代码。进阶再做自定义小程序(MiniApp)或微信小程序。

---

## 第五步:服务端 AI 迁移 (智能体平台 + 大模型额度)

> ⚠️ **背景(2026-07-16)**:阿里云百炼账户已欠费(`Arrearage`)。
> ✅ **进展(2026-07-19)**:主力/兜底 LLM 已切到 **SiliconFlow**(key 有效,已实测通),线上 AI 功能恢复。涂鸦智能体作为迁移目标,**失败自动降级 SiliconFlow,演示永不中断**。

### 5.0 涂鸦官方文档研读结论 (2026-07-19,依据官方 PDF)

| 事实 | 出处 | 对我们的影响 |
|---|---|---|
| 智能体在「开发者工作台 → AI 智能体开发」创建:选模型(如 Qwen3 Max)→ 写提示词 → 调试(仅中国数据中心)→ 发布 | 《智能体开发平台》《调试与预览》 | 5 个专科智能体可直接建,提示词平台侧托管 |
| 应用端载体含 **App、云云对接、音响、SaaS、中控屏**;投放渠道文档写了设备直连/对话小程序/工作流 | 《智能体开发平台》《投放及费用》 | "云云对接"= 我们服务器调用的通道,路线成立 |
| **智能体开放接口(OpenAPI)存在**:云项目签名鉴权 + 订阅服务;接口不收功能费,消耗 Token 额度;但文档"开放能力持续完善中",**未公开端点路径** | 《智能体开放接口》(全文仅3页) | 真实路径要登录后在「云开发 → API Explorer」查 → 代码已做**候选路径自动探测 + `TUYA_AGENT_CHAT_PATH` 锁定** |
| 每个发布的智能体自动生成**专属对话小程序**,智能生活 App 扫码即用,无需额外授权 | 《投放及费用》 | 演示保底通道:就算 OpenAPI 没放开,评委也能扫码直接和 5 个智能体对话 |

### 5.1 服务端已完成的改造 (代码侧 ✅)

所有 LLM 调用收敛到统一网关 **`services/llm.js`**,业务代码零改动:

```bash
LLM_PROVIDER=tuya     # 当前值:优先涂鸦智能体,失败自动降级 SiliconFlow (LLM_FALLBACK=off 可关)
LLM_PROVIDER=openai   # 纯 SiliconFlow / 任意 OpenAI 兼容端点
```

| 文件 | 角色 |
|---|---|
| `services/llm.js` | 统一入口 `chat(messages, opts)`;**tuya 候选路径探测→降级 SiliconFlow** 全在这里 |
| `services/tuya_openapi.js` | 涂鸦云 OpenAPI 通用客户端(HMAC-SHA256 v2 签名 + token 缓存自动续期) |
| `scripts/probe_tuya_agent_api.js` | **迁移体检**:密钥→token、5 个智能体 ID、对话路径探测、兜底链路,一条命令 |
| `routes/agents.js` `reports.js` `pressure.js` `voice.js` | 全部走网关,携带 `agentKey`(科室智能体路由) |
| `routes/voiceStream.js` | 直连 KIMI_* 端点(现=SiliconFlow):逐句流式→CosyVoice TTS 需要 SSE 增量 |

**科室路由**:患者分配的智能体(`quadriplegia/diabetes/post_stroke/copd/general`)映射到 `.env` 的 `TUYA_AGENT_ID_<大写名>`,没配的回落到 `TUYA_AGENT_ID` 默认智能体,再不行降级 SiliconFlow。

**降级逻辑**:涂鸦阶段独立限时(默认 min(15s, timeoutMs/2),`TUYA_TIMEOUT_MS` 可调),未配置/未订阅/路径全错/超时 → 自动改走 SiliconFlow 并打日志 `[llm] 涂鸦智能体不可用, 已降级...`。**未配 `TUYA_AGENT_ID` 时零网络开销直接降级**,所以现在就可以放心用 `LLM_PROVIDER=tuya`。

### 5.2 你要做的:平台侧三件事 (每步做完跑一次体检)

```bash
node scripts/probe_tuya_agent_api.js      # 迁移体检:告诉你卡在哪、下一步填什么
```

**① 云项目已就绪 ✅**(2026-07-19 实测 token 获取成功):`TUYA_ACCESS_ID/SECRET` 已在 `.env`。
   还需:云开发 → 项目 → **服务 API → 订阅名称含「智能体/AI Agent」的开放服务**(没订阅时对话接口报 code=1106)。

**② 建 5 个专科智能体**:开发者工作台 → **AI 智能体开发** → 创建 Agent:
   1. 模型选 **Qwen3 Max**(或额度内最强档);记忆消息数默认即可
   2. 提示词一键导出,逐个粘贴到「提示词」:
      ```bash
      node scripts/export_agent_prompts.js            # 全部 5 个
      node scripts/export_agent_prompts.js diabetes   # 单个
      ```
   3. 在线调试(数据中心须中国区)→ **发布**
   4. 把每个智能体的 **agent_id** 填入 `.env` 对应变量(导出脚本已标注变量名)
   5. 竞赛赠送的大模型额度按命题说明领取(参赛群/组委会渠道)

**③ 锁定对话接口路径**:再跑一次体检,若候选路径有一条探通,按提示把 `TUYA_AGENT_CHAT_PATH=...` 固化进 `.env`;
   若全部未通 → 云开发 → **API Explorer** → 智能体分组 → 抄真实路径(保留 `{agent_id}` 占位符)填入 `TUYA_AGENT_CHAT_PATH`;
   Explorer 里也没有 = 开放接口未对账号放开(文档明说"持续完善中"),**找赛事群/涂鸦支持开通**;期间演示自动走 SiliconFlow,不受影响。

### 5.3 `.env` 当前状态 (已配好,只差智能体 ID 和 Moonshot key)

```bash
LLM_PROVIDER=tuya                                # 降级链: 涂鸦智能体 → kimi-k3 → SiliconFlow
MOONSHOT_API_KEY=                                # ← 主力 kimi-k3 (K2.5 已下架), 填 key 即启用
MOONSHOT_MODEL=kimi-k3
KIMI_BASE_URL=https://api.siliconflow.cn/v1      # 保底: SiliconFlow (已实测)
KIMI_MODEL=deepseek-ai/DeepSeek-V3
VOICE_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct         # 语音链路快模型 (已实测; 语音自动跳过 K3 级)
TUYA_ACCESS_ID=... / TUYA_ACCESS_SECRET=...      # 已配,token 验证通过
TUYA_AGENT_ID=... + 5 个科室变量                  # ← 建好智能体后回填
# TUYA_AGENT_CHAT_PATH=...                        # ← 体检探通后固化
```

### 5.4 验证矩阵

```bash
node scripts/probe_tuya_agent_api.js              # 平台侧进度体检 (四项检查+结论)
node scripts/test_llm_gateway.js "患者血氧92%?"    # 业务链路端到端 (走真实降级逻辑)
```

| 现象 | 含义 |
|---|---|
| 体检 [3] 某路径 ✅ 通 | 涂鸦链路打通,按提示固化 `TUYA_AGENT_CHAT_PATH`,演示可讲"已迁移涂鸦智能体" |
| 体检 [3] 全部 code=1106 | 云项目没订阅智能体服务 → 5.2① |
| 体检 [3] 全部 code=1108 | 路径形态不对 → API Explorer 抄真实路径 |
| test_llm_gateway 出现"已降级"仍 ✅ | 演示安全:涂鸦没就绪但 SiliconFlow 兜住了 |

ECS 上改完 `.env` 后 `pm2 restart nursing-bed --update-env` 生效。

> 💡 **如果涂鸦额度给的是 OpenAI 兼容端点**(部分批次以 API Key + base_url 形式发放):不用 provider=tuya,直接把 `KIMI_BASE_URL/KIMI_API_KEY/KIMI_MODEL` 换成涂鸦给的值即可,一行代码都不用动。
> 💡 **答辩双保险**:①服务器链路(本节);②每个发布的智能体自带**专属对话小程序**,评委手机装「智能生活」App 扫码即可直接对话 5 个专科智能体——OpenAPI 万一没放开,这条通道照样能证明"智能体真在涂鸦平台上"。

---

## 后续路线 (对照创意表承诺)

| 创意表承诺 | 状态 |
|---|---|
| ① 涂鸦 AI 云设备接入与命令下发 | ✅ **已完成并联调通过** (2026-07-16):产品「树莓派-病床」三元组认证成功(标识与密钥在设备端 local_secrets.py, 不入库),TLS 连接 + 属性上报 OK;桥接双链路 E2E PASS |
| ② 涂鸦智能体开发平台 (5 个专科护理 Agent) | 🟡 **代码侧完成+双链路已验证** (2026-07-19):候选路径探测+自动降级 SiliconFlow;云项目 token 实测通过;剩平台侧建 5 个智能体回填 ID → 见第五步 5.2 |
| ③ 涂鸦大模型调用额度 | 🟡 **代码侧已完成**:`LLM_PROVIDER=tuya` 已启用(自动降级保护);领到额度、建好智能体即真实消耗涂鸦额度 |
| ④ TuyaOpen ESP32-S3 端侧接入 | ⏳ 可选加分项;建议申请命题赠送的 T5AI 开发板做端侧演示 |
| ⑤ DuckyClaw 边缘部署 | ⏳ 可选;命题推荐的端侧 AI 框架,官方资料随赛事讲座发布,树莓派侧评估——当前 RPi 已有本地 CNN+决策引擎,该项属锦上添花 |

---

## 本次代码改动清单

| 文件 | 改动 |
|---|---|
| `hardware/tuya_link.py` | **新增**:TuyaLink MQTT 客户端(三元组 HMAC-SHA256 认证、属性上报、set/action 下行、paho 1.x/2.x 兼容、独立测试入口) |
| `hardware/config.py` | IOTDA_* 配置块 → TUYA_* 三元组配置;CLOUD_SERVER 改为新 ECS 占位符 |
| `hardware/mqtt_bridge.py` | IoTDA 集成段(连接/上报/命令)全部替换为涂鸦实现;新增电池上报与压力上报 5s 限流;命令路由扩展(急停/导航/气囊减压/状态查询) |
| `hardware/main.py` | 启动横幅与日志 IoTDA → Tuya |
| `README.md` | 徽章、架构图、特性表更新为涂鸦 |
| `services/llm.js` | **新增** (2026-07-16, 07-19 增强):统一 LLM 网关;涂鸦候选路径自动探测 + 失败自动降级 SiliconFlow |
| `services/tuya_openapi.js` | **新增**:涂鸦云 OpenAPI 客户端 (v2 HMAC-SHA256 签名 + access_token 缓存续期) |
| `routes/agents.js` `reports.js` `pressure.js` `voice.js` | LLM 直连代码全部收敛到统一网关,新增科室 agentKey 路由 |
| `routes/voiceStream.js` | 保留 KIMI_* 端点直连 (逐句流式 TTS 依赖 SSE 增量,见文件头注释);端点已随 .env 切到 SiliconFlow |
| `scripts/export_agent_prompts.js` | **新增**:导出 5 个专科智能体提示词,建平台智能体时直接粘贴 |
| `scripts/test_llm_gateway.js` | **新增**:网关自测脚本,切换 provider 后一条命令验证 |
| `scripts/probe_tuya_agent_api.js` | **新增** (2026-07-19):涂鸦迁移体检——密钥/智能体ID/对话路径探测/兜底链路四项检查 |
| `.env` | (2026-07-19) LLM 主力切 SiliconFlow (百炼欠费备份在文件尾);`LLM_PROVIDER=tuya` 启用 |
