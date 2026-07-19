/**
 * 智能护理病床 - 鸿蒙APP 数据类型定义
 * 与 Express 后端 API 返回的 JSON 结构对齐
 */

// ─── 认证 ───
export interface LoginResponse {
  token: string;
  user: UserInfo;
}

export interface UserInfo {
  id: number;
  username: string;
  role: string;       // admin | doctor | patient | family
  real_name: string;
  phone: string;
}

// ─── 患者 ───
export interface Patient {
  id: number;
  name: string;
  age: number;
  gender: string;
  room_number: string;
  bed_number: string;
  disease_type: string;
  disease_detail: string;
  assigned_agent: string;
  admission_date: string;
}

// ─── 生命体征 ───
export interface VitalsData {
  id: number;
  patient_id: number;
  heart_rate: number;
  blood_pressure_sys: number;
  blood_pressure_dia: number;
  blood_oxygen: number;
  blood_glucose: number;
  temperature: number;
  sleep_posture: string;
  fabric_sensor_raw: string;
  recorded_at: string;
}

// ─── 告警 ───
export interface AlertData {
  id: number;
  patient_id: number;
  alert_type: string;        // vital_sign | pressure | fall | custom
  metric: string;
  value: number;
  threshold: number;
  message: string;
  status: string;           // active | acknowledged | resolved
  created_at: string;
}

// ─── Agent Swarm ───
export interface SwarmStatus {
  version: string;
  architecture: string;
  framework_ref: string;
  agents: AgentStatus[];
  capabilities: Record<string, string>;
  safety: Record<string, string>;
  timestamp: string;
}

export interface AgentStatus {
  name: string;
  display_name: string;
  icon: string;
  status: string;
  priority: number;
  color: string;
}

export interface AgentDetail {
  name: string;
  display_name: string;
  icon: string;
  priority: number;
  color: string;
  query_interval: number;
  when_to_use: string;
  triggers: string[];
  allowed_actions: string[];
  has_db_config: boolean;
}

// ─── AI 聊天 ───
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: number;
}

export interface StreamEvent {
  type: 'meta' | 'delta' | 'error' | 'done';
  content?: string;
  agent?: string;
  icon?: string;
  message?: string;
}

// ─── 报告 ───
export interface Report {
  id: number;
  patient_id: number;
  report_date: string;
  summary: string;
  ai_diagnosis: string;
  rehab_suggestions: string;
  generated_by: string;
}

// ─── 体征卡片配置 ───
export interface VitalCardConfig {
  label: string;
  icon: string;
  unit: string;
  getValue: (v: VitalsData) => string;
  getLevel: (v: VitalsData) => 'normal' | 'warning' | 'critical';
}
