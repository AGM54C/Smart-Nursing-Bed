/**
 * 智能护理病床 - NearLink星闪床载标签固件
 *
 * 芯片: Hi3863V100 (WiFi6 + SLE双模)
 * 功能: SLE测距从节点 (被锚点测距) + WiFi状态上报
 *
 * 安装位置: 病床底部
 * 供电: 病床主供电 (5V USB-C)
 *
 * ⚠️ 此文件为参考框架, 需要配合海思SLE SDK的头文件编译
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>

/* ═══════════════════════════════════════════
 *  配置参数
 * ═══════════════════════════════════════════ */

/* 标签身份 */
#define TAG_ID              "bed_tag_01"
#define TAG_DESC            "智能护理病床#1 床载标签"

/* WiFi配置 (与锚点相同网络) */
#define WIFI_SSID           "SmartBed_AP"
#define WIFI_PASSWORD       "your_password"

/* MQTT配置 */
#define MQTT_BROKER_IP      "192.168.1.100"
#define MQTT_BROKER_PORT    1883
#define MQTT_CLIENT_ID      "nearlink-" TAG_ID
#define MQTT_TOPIC_STATUS   "bed/nearlink/status"

/* SLE标签参数 */
#define SLE_ADV_INTERVAL_MS   100   /* 广播间隔 (响应测距请求) */
#define SLE_TX_POWER          0     /* 发射功率 dBm */

/* ═══════════════════════════════════════════
 *  全局状态
 * ═══════════════════════════════════════════ */

typedef struct {
    int   sle_initialized;
    int   wifi_connected;
    int   mqtt_connected;
    int   ranging_responded;  /* 累计响应测距次数 */
    int   battery_level;      /* 电池电量 (床载标签有线供电则为100) */
} TagState;

static TagState g_state = {0};

/* ═══════════════════════════════════════════
 *  SLE 标签功能 (被动响应测距)
 * ═══════════════════════════════════════════ */

/**
 * SLE测距响应回调
 *
 * 锚点发起测距请求时, SDK自动响应
 * 标签端只需记录状态
 */
static void sle_ranging_response_callback(/* sle_ranging_event_t *event */)
{
    g_state.ranging_responded++;

    /*
     * 实际SDK事件:
     *   event->initiator_addr : 发起方(锚点)地址
     *   event->channel       : 测距信道
     *   event->status        : 响应状态
     */

    if (g_state.ranging_responded % 50 == 0) {
        printf("[Tag:%s] Ranging responses: %d\n",
               TAG_ID, g_state.ranging_responded);
    }
}

static int sle_tag_init(void)
{
    printf("[Tag:%s] Initializing SLE tag mode...\n", TAG_ID);

    /*
     * 实际SDK调用:
     *
     * // 1. SLE初始化
     * sle_init();
     *
     * // 2. 配置为测距响应方 (标签)
     * sle_ranging_param_t params = {
     *     .role = SLE_RANGING_ROLE_RESPONDER,  // 标签=响应方
     *     .tx_power = SLE_TX_POWER,
     * };
     *
     * // 3. 配置SLE广播 (让锚点能发现和测距)
     * sle_adv_param_t adv = {
     *     .adv_interval = SLE_ADV_INTERVAL_MS,
     *     .adv_type = SLE_ADV_TYPE_CONNECTABLE,
     * };
     *
     * // 4. 设置广播数据 (包含标签ID)
     * sle_adv_data_t adv_data = {0};
     * adv_data.data = (uint8_t *)TAG_ID;
     * adv_data.data_len = strlen(TAG_ID);
     * sle_set_adv_data(&adv_data);
     *
     * // 5. 注册测距回调
     * sle_ranging_register_callback(sle_ranging_response_callback);
     *
     * // 6. 启动广播和测距响应
     * sle_start_adv(&adv);
     * sle_start_ranging(&params);
     */

    g_state.sle_initialized = 1;
    printf("[Tag:%s] SLE tag mode initialized, advertising...\n", TAG_ID);
    return 0;
}

/* ═══════════════════════════════════════════
 *  WiFi + MQTT (与锚点类似)
 * ═══════════════════════════════════════════ */

static int wifi_connect(void)
{
    printf("[Tag:%s] Connecting to WiFi: %s\n", TAG_ID, WIFI_SSID);
    /* 同锚点WiFi连接代码 */
    g_state.wifi_connected = 1;
    return 0;
}

static int mqtt_connect(void)
{
    printf("[Tag:%s] Connecting MQTT to %s:%d\n",
           TAG_ID, MQTT_BROKER_IP, MQTT_BROKER_PORT);
    /* 同锚点MQTT连接代码 */
    g_state.mqtt_connected = 1;
    return 0;
}

/**
 * 定期上报标签状态
 */
static void mqtt_publish_status(void)
{
    if (!g_state.mqtt_connected) return;

    char payload[256];
    snprintf(payload, sizeof(payload),
        "{"
        "\"tag_id\":\"%s\","
        "\"sle_active\":%d,"
        "\"ranging_count\":%d,"
        "\"battery\":%d,"
        "\"wifi_rssi\":%d"
        "}",
        TAG_ID,
        g_state.sle_initialized,
        g_state.ranging_responded,
        g_state.battery_level,
        -45  /* 实际使用: wifi_get_rssi() */
    );

    printf("[Tag:%s] Status→ %s\n", TAG_ID, payload);
}

/* ═══════════════════════════════════════════
 *  主任务
 * ═══════════════════════════════════════════ */

static void tag_main_task(void)
{
    printf("\n");
    printf("╔══════════════════════════════════════╗\n");
    printf("║  NearLink Tag: %-21s ║\n", TAG_ID);
    printf("║  %s          ║\n", TAG_DESC);
    printf("╚══════════════════════════════════════╝\n\n");

    g_state.battery_level = 100;  /* 有线供电 */

    /* 1. SLE标签初始化 (优先, 让锚点尽快能测距) */
    if (sle_tag_init() != 0) {
        printf("[Tag] SLE init failed!\n");
        return;
    }

    /* 2. WiFi连接 */
    wifi_connect();

    /* 3. MQTT连接 */
    if (g_state.wifi_connected) {
        mqtt_connect();
    }

    /* 4. 工作循环 (标签主要被动等待测距请求) */
    printf("[Tag:%s] Running, waiting for ranging requests...\n", TAG_ID);

    int status_counter = 0;
    while (1) {
        /* 标签主要工作是被动响应, 这里只做定期状态上报 */
        status_counter++;

        if (status_counter % 50 == 0) {  /* 每10秒上报一次状态 */
            mqtt_publish_status();
        }

        /* 模拟被动响应 */
        sle_ranging_response_callback();

        usleep(200 * 1000);  /* 200ms */
    }
}

int main(void)
{
    tag_main_task();
    return 0;
}
