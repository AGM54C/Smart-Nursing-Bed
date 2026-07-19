/**
 * 智能护理病床 - 鸿蒙APP 全局常量
 */

// ═══════════════════════════════════════════
//  服务器配置 — 部署后改为你的阿里云域名
// ═══════════════════════════════════════════
export const SERVER_BASE_URL: string = 'http://47.109.73.194:3000';
// 域名生效后改为: 'http://smartnursingbed.com'

// 树莓派局域网直连 (NLC控制用)
export const PI_BASE_URL: string = 'http://10.20.42.167:5000';

// ═══════════════════════════════════════════
//  API 端点
// ═══════════════════════════════════════════
export const API = {
  // 认证
  LOGIN: '/api/auth/login',

  // 患者
  PATIENTS: '/api/patients',

  // 体征
  VITALS_LATEST: (id: number) => `/api/vitals/${id}/latest`,
  VITALS_HISTORY: (id: number, days: number) => `/api/vitals/${id}?days=${days}`,
  VITALS_STATS: (id: number) => `/api/vitals/${id}/stats`,

  // 告警
  ALERTS: '/api/alerts',
  ALERT_UPDATE: (id: number) => `/api/alerts/${id}`,

  // AI Agent
  AGENTS_CONSULT: '/api/agents/consult',
  AGENTS_STREAM_CHAT: '/api/agents/stream-chat',
  SWARM_STATUS: '/api/agents/swarm/status',
  SWARM_AGENTS: '/api/agents/swarm/agents',

  // 报告
  REPORTS: (id: number) => `/api/reports/${id}`,

  // 语音
  VOICE_CHAT: '/api/voice/chat',

  // 树莓派直连
  PI_NLC: '/api/nlc',
  PI_REMOTE: '/api/remote',
};

// ═══════════════════════════════════════════
//  轮询间隔
// ═══════════════════════════════════════════
export const POLL_INTERVAL_VITALS: number = 5000;    // 体征 5秒
export const POLL_INTERVAL_ALERTS: number = 10000;   // 告警 10秒
export const POLL_INTERVAL_SWARM: number = 15000;    // Agent 15秒

// ═══════════════════════════════════════════
//  颜色主题 (与 Web 端 style.css 对齐)
// ═══════════════════════════════════════════
export const Colors = {
  // 主色
  TEAL_500: '#43D9AD',
  TEAL_600: '#36B896',
  CORAL_400: '#FF6B8A',
  CORAL_500: '#E8546A',

  // 背景
  BG_DARK: '#0A0F1E',
  BG_CARD: '#131A2E',
  BG_SURFACE: '#1A2340',

  // 文字
  TEXT_PRIMARY: '#F0F2F5',
  TEXT_SECONDARY: '#8B95A8',
  TEXT_MUTED: '#5A6478',

  // 状态
  SUCCESS: '#43D9AD',
  WARNING: '#FFB547',
  DANGER: '#FF6B8A',
  INFO: '#5B9CF6',

  // Agent 颜色
  AGENT_EMERGENCY: '#FF4D6A',
  AGENT_VITALS: '#43D9AD',
  AGENT_PRESSURE: '#5B9CF6',
  AGENT_COMPANION: '#FFB547',
};

// ═══════════════════════════════════════════
//  体征正常范围 (用于颜色判断)
// ═══════════════════════════════════════════
export const VITAL_RANGES = {
  heart_rate: { low: 50, high: 120, critLow: 40, critHigh: 140 },
  blood_oxygen: { low: 93, critLow: 88 },
  temperature: { high: 37.5, critHigh: 38.5 },
  blood_glucose: { low: 3.9, high: 11.1, critLow: 2.8, critHigh: 16.7 },
  blood_pressure_sys: { high: 140, critHigh: 170, low: 90, critLow: 70 },
};

// ═══════════════════════════════════════════
//  睡姿中文映射
// ═══════════════════════════════════════════
export const POSTURE_NAMES: Record<string, string> = {
  'supine': '仰卧',
  'left_side': '左侧卧',
  'right_side': '右侧卧',
  'prone': '俯卧',
  'sitting': '坐起',
  'empty': '离床',
};
