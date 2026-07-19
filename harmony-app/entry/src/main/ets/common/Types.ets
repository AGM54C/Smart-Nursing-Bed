/**
 * 智能护理病床 - 鸿蒙APP 数据类型定义 (ArkTS Strict Mode)
 * 用 class 代替 interface，避免 object literal / union type 问题
 */

// ─── 患者 ───
export class Patient {
  id: number = 0;
  name: string = '';
  age: number = 0;
  gender: string = '';
  room_number: string = '';
  bed_number: string = '';
  disease_type: string = '';
  disease_detail: string = '';
  assigned_agent: string = '';
  admission_date: string = '';
}

// ─── 生命体征 ───
export class VitalsData {
  id: number = 0;
  patient_id: number = 0;
  heart_rate: number = 0;
  blood_pressure_sys: number = 0;
  blood_pressure_dia: number = 0;
  blood_oxygen: number = 0;
  blood_glucose: number = 0;
  temperature: number = 0;
  sleep_posture: string = '';
  fabric_sensor_raw: string = '';
  recorded_at: string = '';
}

// ─── 告警 ───
export class AlertData {
  id: number = 0;
  patient_id: number = 0;
  alert_type: string = '';
  metric: string = '';
  value: number = 0;
  threshold: number = 0;
  message: string = '';
  status: string = '';
  created_at: string = '';
}

// ─── Agent Swarm ───
export class SwarmCapabilities {
  coordinator: string = '';
  mailbox: string = '';
  memory: string = '';
  permission: string = '';
}

export class SwarmSafety {
  L0: string = '';
  L1: string = '';
  L2: string = '';
  L3: string = '';
}

export class SwarmStatus {
  version: string = '';
  architecture: string = '';
  framework_ref: string = '';
  agents: AgentStatus[] = [];
  capabilities: SwarmCapabilities = new SwarmCapabilities();
  safety: SwarmSafety = new SwarmSafety();
  timestamp: string = '';
}

export class AgentStatus {
  name: string = '';
  display_name: string = '';
  icon: string = '';
  status: string = '';
  priority: number = 0;
  color: string = '';
}

export class AgentDetail {
  name: string = '';
  display_name: string = '';
  icon: string = '';
  priority: number = 0;
  color: string = '';
  query_interval: number = 0;
  when_to_use: string = '';
  triggers: string[] = [];
  allowed_actions: string[] = [];
  has_db_config: boolean = false;
}

export class AgentListResponse {
  total: number = 0;
  agents: AgentDetail[] = [];
}

// ─── AI 聊天 ───
export class ChatMessage {
  role: string = '';
  content: string = '';
  timestamp: number = 0;
}

// ─── 报告 ───
export class Report {
  id: number = 0;
  patient_id: number = 0;
  report_date: string = '';
  summary: string = '';
  ai_diagnosis: string = '';
  rehab_suggestions: string = '';
  generated_by: string = '';
}
