/**
 * 智能护理病床 - 鸿蒙APP 全局常量 (ArkTS Strict Mode)
 */

// ═══════════════════════════════════════════
//  服务器配置
// ═══════════════════════════════════════════
export const SERVER_BASE_URL: string = 'http://47.109.61.163:3000';  // 云端 ECS (与 hardware/config.py 的 CLOUD_SERVER 一致)
export const PI_BASE_URL: string = 'http://10.20.42.167:5000';

// ═══════════════════════════════════════════
//  API 端点 (用静态方法代替对象字面量)
// ═══════════════════════════════════════════
export class API {
  static readonly LOGIN: string = '/api/auth/login';
  static readonly PATIENTS: string = '/api/patients';
  static readonly ALERTS: string = '/api/alerts';
  static readonly AGENTS_CONSULT: string = '/api/agents/consult';
  static readonly AGENTS_STREAM_CHAT: string = '/api/agents/stream-chat';
  static readonly SWARM_STATUS: string = '/api/agents/swarm/status';
  static readonly SWARM_AGENTS: string = '/api/agents/swarm/agents';
  static readonly VOICE_CHAT: string = '/api/voice/chat';
  static readonly PI_NLC: string = '/api/nlc';
  static readonly PI_REMOTE: string = '/api/remote';

  static VITALS_LATEST(id: number): string { return `/api/vitals/${id}/latest`; }
  static VITALS_HISTORY(id: number, days: number): string { return `/api/vitals/${id}?days=${days}`; }
  static VITALS_STATS(id: number): string { return `/api/vitals/${id}/stats`; }
  static ALERT_UPDATE(id: number): string { return `/api/alerts/${id}`; }
  static REPORTS(id: number): string { return `/api/reports/${id}`; }
}

// ═══════════════════════════════════════════
//  轮询间隔
// ═══════════════════════════════════════════
export const POLL_INTERVAL_VITALS: number = 5000;
export const POLL_INTERVAL_ALERTS: number = 10000;
export const POLL_INTERVAL_SWARM: number = 15000;

// ═══════════════════════════════════════════
//  颜色主题
// ═══════════════════════════════════════════
export class Colors {
  static readonly TEAL_500: string = '#43D9AD';
  static readonly TEAL_600: string = '#36B896';
  static readonly CORAL_400: string = '#FF6B8A';
  static readonly CORAL_500: string = '#E8546A';
  static readonly BG_DARK: string = '#0A0F1E';
  static readonly BG_CARD: string = '#131A2E';
  static readonly BG_SURFACE: string = '#1A2340';
  static readonly TEXT_PRIMARY: string = '#F0F2F5';
  static readonly TEXT_SECONDARY: string = '#8B95A8';
  static readonly TEXT_MUTED: string = '#5A6478';
  static readonly SUCCESS: string = '#43D9AD';
  static readonly WARNING: string = '#FFB547';
  static readonly DANGER: string = '#FF6B8A';
  static readonly INFO: string = '#5B9CF6';
  static readonly AGENT_EMERGENCY: string = '#FF4D6A';
  static readonly AGENT_VITALS: string = '#43D9AD';
  static readonly AGENT_PRESSURE: string = '#5B9CF6';
  static readonly AGENT_COMPANION: string = '#FFB547';
}

// ═══════════════════════════════════════════
//  体征正常范围
// ═══════════════════════════════════════════
export class VitalRange {
  low: number = 0;
  high: number = 999;
  critLow: number = 0;
  critHigh: number = 999;
  constructor(low: number, high: number, critLow: number, critHigh: number) {
    this.low = low;
    this.high = high;
    this.critLow = critLow;
    this.critHigh = critHigh;
  }
}

export class VitalRanges {
  static readonly heart_rate: VitalRange = new VitalRange(50, 120, 40, 140);
  static readonly blood_oxygen: VitalRange = new VitalRange(93, 100, 88, 100);
  static readonly temperature: VitalRange = new VitalRange(35, 37.5, 34, 38.5);
  static readonly blood_glucose: VitalRange = new VitalRange(3.9, 11.1, 2.8, 16.7);
  static readonly blood_pressure_sys: VitalRange = new VitalRange(90, 140, 70, 170);
}

// ═══════════════════════════════════════════
//  睡姿映射
// ═══════════════════════════════════════════
export class PostureNames {
  static get(key: string): string {
    if (key === 'supine') return '仰卧';
    if (key === 'left_side') return '左侧卧';
    if (key === 'right_side') return '右侧卧';
    if (key === 'prone') return '俯卧';
    if (key === 'sitting') return '坐起';
    if (key === 'empty') return '离床';
    return key;
  }
}
