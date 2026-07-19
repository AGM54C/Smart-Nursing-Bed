/**
 * 智能护理病床 - NearLink星闪锚点固件
 *
 * 芯片: Hi3863V100 (WiFi6 + SLE双模)
 * 功能: SLE测距主节点 + WiFi上报测距数据到树莓派
 *
 * 开发环境: OpenHarmony轻量系统 / DevEco Device Tool
 * SDK: HiHope WS63 NearLink SDK (fbb_ws63)
 *
 * 部署: 固定安装在走廊天花板/墙壁, USB-C 5V供电
 *
 * ⚠️ 此文件为参考框架, 需要配合海思SLE SDK的头文件编译
 *    实际开发请参考: https://gitee.com/HiSpark/fbb_ws63
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>

/* OpenHarmony 轻量系统头文件 */
// #include "ohos_init.h"
// #include "cmsis_os2.h"

/* SLE协议栈头文件 (海思SDK) */
// #include "sle_common.h"
// #include "sle_connection_manager.h"
// #include "sle_ranging.h"
// #include "sle_device_discovery.h"

/* WiFi头文件 */
// #include "wifi_device.h"
// #include "lwip/sockets.h"

/* MQTT轻量客户端 */
// #include "MQTTClient.h"  // Eclipse Paho Embedded-C

/* ═══════════════════════════════════════════
 *  配置参数
 * ═══════════════════════════════════════════ */

/* 锚点身份 (烧录时修改) */
#define ANCHOR_ID           "anchor_01"
#define ANCHOR_X            0.0f
#define ANCHOR_Y            0.0f
#define ANCHOR_Z            2.5f
#define ANCHOR_DESC         "走廊起点/301门口"

/* WiFi配置 */
#define WIFI_SSID           "SmartBed_AP"
#define WIFI_PASSWORD       "your_password"

/* MQTT配置 */
#define MQTT_BROKER_IP      "192.168.1.100"   /* 树莓派IP */
#define MQTT_BROKER_PORT    1883
#define MQTT_CLIENT_ID      "nearlink-" ANCHOR_ID
#define MQTT_TOPIC_RANGING  "bed/nearlink/ranging"
#define MQTT_TOPIC_STATUS   "bed/nearlink/status"

/* SLE测距参数 */
#define SLE_RANGING_INTERVAL_MS   200   /* 测距周期 (5Hz) */
#define SLE_CHANNEL               37    /* SLE信道 */
#define TAG_FILTER_ID             "bed_tag_01"  /* 只测距此标签 */

/* ═══════════════════════════════════════════
 *  全局状态
 * ═══════════════════════════════════════════ */

typedef struct {
    float distance;         /* 最新测距值 (米) */
    int   rssi;             /* 信号强度 dBm */
    int   ranging_count;    /* 累计测距次数 */
    int   wifi_connected;   /* WiFi连接状态 */
    int   mqtt_connected;   /* MQTT连接状态 */
    int   sle_initialized;  /* SLE初始化状态 */
    char  tag_id[32];       /* 最新测到的标签ID */
} AnchorState;

static AnchorState g_state = {0};

/* ═══════════════════════════════════════════
 *  SLE 测距功能
 * ═══════════════════════════════════════════ */

/**
 * SLE测距结果回调
 *
 * 当SLE完成一次测距后, SDK会调用此回调
 * 数据包含: 距离(米), RSSI, 标签ID等
 */
static void sle_ranging_callback(/* sle_ranging_result_t *result */)
{
    /*
     * 实际SDK回调参数示例:
     *   result->distance_m   : float, 测距值(米)
     *   result->rssi        : int8_t, 信号强度
     *   result->peer_addr   : 对端地址
     *   result->status      : 0=成功
     * 
     * g_state.distance = result->distance_m;
     * g_state.rssi = result->rssi;
     * g_state.ranging_count++;
     * snprintf(g_state.tag_id, sizeof(g_state.tag_id), "%s", TAG_FILTER_ID);
     */

    /* 模拟: 使用占位值 */
    g_state.distance = 3.5f;
    g_state.rssi = -55;
    g_state.ranging_count++;
    strncpy(g_state.tag_id, TAG_FILTER_ID, sizeof(g_state.tag_id));

    printf("[Anchor:%s] Ranging #%d: dist=%.2fm, RSSI=%ddBm, tag=%s\n",
           ANCHOR_ID, g_state.ranging_count,
           g_state.distance, g_state.rssi, g_state.tag_id);
}

/**
 * 初始化SLE测距
 */
static int sle_ranging_init(void)
{
    printf("[Anchor:%s] Initializing SLE ranging...\n", ANCHOR_ID);

    /*
     * 实际SDK调用:
     *
     * // 1. 初始化SLE协议栈
     * sle_init();
     *
     * // 2. 配置测距参数
     * sle_ranging_param_t params = {
     *     .role = SLE_RANGING_ROLE_INITIATOR,  // 锚点=发起方
     *     .channel = SLE_CHANNEL,
     *     .interval_ms = SLE_RANGING_INTERVAL_MS,
     *     .method = SLE_RANGING_METHOD_TOF_PHASE,  // ToF+相位差复合
     * };
     *
     * // 3. 注册回调
     * sle_ranging_register_callback(sle_ranging_callback);
     *
     * // 4. 启动测距
     * int ret = sle_start_ranging(&params);
     * if (ret != 0) {
     *     printf("SLE ranging start failed: %d\n", ret);
     *     return -1;
     * }
     */

    g_state.sle_initialized = 1;
    printf("[Anchor:%s] SLE ranging initialized (channel=%d, interval=%dms)\n",
           ANCHOR_ID, SLE_CHANNEL, SLE_RANGING_INTERVAL_MS);
    return 0;
}

/* ═══════════════════════════════════════════
 *  WiFi 连接
 * ═══════════════════════════════════════════ */

static int wifi_connect(void)
{
    printf("[Anchor:%s] Connecting to WiFi: %s\n", ANCHOR_ID, WIFI_SSID);

    /*
     * 实际SDK调用 (OpenHarmony WiFi STA):
     *
     * WifiDeviceConfig config = {0};
     * strcpy(config.ssid, WIFI_SSID);
     * strcpy(config.preSharedKey, WIFI_PASSWORD);
     * config.securityType = WIFI_SEC_TYPE_PSK;
     *
     * int netId = -1;
     * AddDeviceConfig(&config, &netId);
     * ConnectTo(netId);
     *
     * // 等待DHCP
     * struct netif *iface = netifapi_netif_find("wlan0");
     * dhcp_start(iface);
     */

    g_state.wifi_connected = 1;
    printf("[Anchor:%s] WiFi connected\n", ANCHOR_ID);
    return 0;
}

/* ═══════════════════════════════════════════
 *  MQTT 上报
 * ═══════════════════════════════════════════ */

/**
 * 通过MQTT上报测距数据到树莓派
 *
 * JSON格式:
 * {
 *   "anchor_id": "anchor_01",
 *   "tag_id": "bed_tag_01",
 *   "distance": 3.42,
 *   "rssi": -65,
 *   "channel": 37,
 *   "ts": 1712345678.123
 * }
 */
static void mqtt_publish_ranging(void)
{
    if (!g_state.mqtt_connected) {
        return;
    }

    char payload[256];
    snprintf(payload, sizeof(payload),
        "{"
        "\"anchor_id\":\"%s\","
        "\"tag_id\":\"%s\","
        "\"distance\":%.3f,"
        "\"rssi\":%d,"
        "\"channel\":%d,"
        "\"ts\":%.3f"
        "}",
        ANCHOR_ID,
        g_state.tag_id,
        g_state.distance,
        g_state.rssi,
        SLE_CHANNEL,
        /* 实际使用: hi_get_real_time() / 1000.0 */
        0.0
    );

    /*
     * 实际SDK调用 (Paho Embedded-C):
     *
     * MQTTMessage message = {0};
     * message.qos = QOS0;
     * message.payload = payload;
     * message.payloadlen = strlen(payload);
     *
     * MQTTPublish(&mqtt_client, MQTT_TOPIC_RANGING, &message);
     */

    printf("[Anchor:%s] MQTT→ %s\n", ANCHOR_ID, payload);
}

static int mqtt_connect(void)
{
    printf("[Anchor:%s] Connecting MQTT to %s:%d\n",
           ANCHOR_ID, MQTT_BROKER_IP, MQTT_BROKER_PORT);

    /*
     * 实际SDK调用:
     *
     * Network n;
     * NetworkInit(&n);
     * NetworkConnect(&n, MQTT_BROKER_IP, MQTT_BROKER_PORT);
     *
     * MQTTClient client;
     * MQTTClientInit(&client, &n, 1000, ...);
     *
     * MQTTPacket_connectData data = MQTTPacket_connectData_initializer;
     * data.clientID.cstring = MQTT_CLIENT_ID;
     * data.keepAliveInterval = 60;
     * MQTTConnect(&client, &data);
     */

    g_state.mqtt_connected = 1;
    printf("[Anchor:%s] MQTT connected\n", ANCHOR_ID);
    return 0;
}

/* ═══════════════════════════════════════════
 *  主任务
 * ═══════════════════════════════════════════ */

/**
 * 锚点主任务
 *
 * 执行流程:
 *   1. WiFi连接
 *   2. MQTT连接
 *   3. SLE测距初始化
 *   4. 循环: 测距 → MQTT上报
 */
static void anchor_main_task(void)
{
    printf("\n");
    printf("╔══════════════════════════════════════╗\n");
    printf("║  NearLink Anchor: %-18s ║\n", ANCHOR_ID);
    printf("║  Position: (%.1f, %.1f, %.1f)       ║\n",
           ANCHOR_X, ANCHOR_Y, ANCHOR_Z);
    printf("║  %s           ║\n", ANCHOR_DESC);
    printf("╚══════════════════════════════════════╝\n\n");

    /* 1. WiFi连接 */
    if (wifi_connect() != 0) {
        printf("[Anchor] WiFi failed, retrying in 5s...\n");
        sleep(5);
        return;
    }

    /* 2. MQTT连接 */
    if (mqtt_connect() != 0) {
        printf("[Anchor] MQTT failed, retrying in 5s...\n");
        sleep(5);
        return;
    }

    /* 3. SLE测距初始化 */
    if (sle_ranging_init() != 0) {
        printf("[Anchor] SLE init failed!\n");
        return;
    }

    /* 4. 工作循环 */
    printf("[Anchor:%s] Entering main loop (interval=%dms)\n",
           ANCHOR_ID, SLE_RANGING_INTERVAL_MS);

    while (1) {
        /* SLE测距 (回调方式, 这里只需等待和上报) */
        /* 注: 实际SDK中测距是异步的, 回调中更新g_state */
        sle_ranging_callback(/* 模拟调用 */);

        /* 上报MQTT */
        mqtt_publish_ranging();

        /* 等待下一个测距周期 */
        usleep(SLE_RANGING_INTERVAL_MS * 1000);
    }
}

/* ═══════════════════════════════════════════
 *  入口 (OpenHarmony SYS_RUN / 普通main)
 * ═══════════════════════════════════════════ */

/*
 * OpenHarmony入口:
 * SYS_RUN(anchor_main_task);
 *
 * 或普通C入口:
 */
int main(void)
{
    anchor_main_task();
    return 0;
}
