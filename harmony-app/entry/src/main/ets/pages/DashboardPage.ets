/**
 * DashboardPage - 实时监护面板
 *
 * 核心功能:
 *   - 6个体征指标实时展示 (5秒轮询)
 *   - 患者信息卡片
 *   - 受压风险展示
 *   - 体征颜色自动变化
 */
import { apiGet } from '../common/ApiService';
import { API, POLL_INTERVAL_VITALS, Colors, VITAL_RANGES, POSTURE_NAMES } from '../common/Constants';
import { VitalsData, Patient } from '../common/Types';
import { VitalCard } from '../components/VitalCard';

@Component
export struct DashboardPage {
  @State patientId: number = 1;
  @State patient: Patient | null = null;
  @State vitals: VitalsData | null = null;
  @State isLoading: boolean = true;
  @State errorMsg: string = '';
  @State lastUpdate: string = '';

  private pollingTimer: number = -1;

  aboutToAppear(): void {
    this.loadPatient();
    this.startPolling();
  }

  aboutToDisappear(): void {
    this.stopPolling();
  }

  private startPolling(): void {
    // 立即拉取一次
    this.fetchVitals();
    // 定时轮询
    this.pollingTimer = setInterval(() => {
      this.fetchVitals();
    }, POLL_INTERVAL_VITALS);
  }

  private stopPolling(): void {
    if (this.pollingTimer !== -1) {
      clearInterval(this.pollingTimer);
      this.pollingTimer = -1;
    }
  }

  private async loadPatient(): Promise<void> {
    try {
      const patients = await apiGet<Patient[]>(API.PATIENTS);
      if (patients && patients.length > 0) {
        this.patient = patients[0]; // 默认第一个患者
        this.patientId = this.patient.id;
      }
    } catch (e) {
      console.error('[Dashboard] Load patient failed:', (e as Error).message);
    }
  }

  private async fetchVitals(): Promise<void> {
    try {
      const data = await apiGet<VitalsData>(API.VITALS_LATEST(this.patientId));
      this.vitals = data;
      this.isLoading = false;
      this.errorMsg = '';
      this.lastUpdate = new Date().toLocaleTimeString();
    } catch (e) {
      this.errorMsg = (e as Error).message;
      console.error('[Dashboard] Fetch vitals failed:', this.errorMsg);
    }
  }

  // ─── 体征级别判断 ───

  private hrLevel(): string {
    if (!this.vitals) return 'normal';
    const hr = this.vitals.heart_rate;
    if (hr > VITAL_RANGES.heart_rate.critHigh || hr < VITAL_RANGES.heart_rate.critLow) return 'critical';
    if (hr > VITAL_RANGES.heart_rate.high || hr < VITAL_RANGES.heart_rate.low) return 'warning';
    return 'normal';
  }

  private spo2Level(): string {
    if (!this.vitals) return 'normal';
    const v = this.vitals.blood_oxygen;
    if (v < VITAL_RANGES.blood_oxygen.critLow) return 'critical';
    if (v < VITAL_RANGES.blood_oxygen.low) return 'warning';
    return 'normal';
  }

  private tempLevel(): string {
    if (!this.vitals) return 'normal';
    const v = this.vitals.temperature;
    if (v > VITAL_RANGES.temperature.critHigh) return 'critical';
    if (v > VITAL_RANGES.temperature.high) return 'warning';
    return 'normal';
  }

  private bpLevel(): string {
    if (!this.vitals) return 'normal';
    const sys = this.vitals.blood_pressure_sys;
    if (sys > VITAL_RANGES.blood_pressure_sys.critHigh || sys < VITAL_RANGES.blood_pressure_sys.critLow) return 'critical';
    if (sys > VITAL_RANGES.blood_pressure_sys.high || sys < VITAL_RANGES.blood_pressure_sys.low) return 'warning';
    return 'normal';
  }

  private glucoseLevel(): string {
    if (!this.vitals) return 'normal';
    const v = this.vitals.blood_glucose;
    if (v > VITAL_RANGES.blood_glucose.critHigh || v < VITAL_RANGES.blood_glucose.critLow) return 'critical';
    if (v > VITAL_RANGES.blood_glucose.high || v < VITAL_RANGES.blood_glucose.low) return 'warning';
    return 'normal';
  }

  build() {
    Scroll() {
      Column() {
        // ═══ 患者信息卡片 ═══
        if (this.patient) {
          Row() {
            // 头像
            Column() {
              Text(this.patient.name.charAt(0))
                .fontSize(22)
                .fontWeight(700)
                .fontColor('#FFF')
            }
            .width(50)
            .height(50)
            .backgroundColor(Colors.TEAL_600)
            .borderRadius(25)
            .justifyContent(FlexAlign.Center)

            // 信息
            Column() {
              Text(this.patient.name)
                .fontSize(18)
                .fontWeight(700)
                .fontColor(Colors.TEXT_PRIMARY)
              Text(`${this.patient.age}岁 · ${this.patient.room_number}房${this.patient.bed_number}号床`)
                .fontSize(12)
                .fontColor(Colors.TEXT_SECONDARY)
                .margin({ top: 2 })
              Text(`${this.patient.disease_type} · ${this.patient.disease_detail}`)
                .fontSize(11)
                .fontColor(Colors.TEXT_MUTED)
                .margin({ top: 2 })
            }
            .alignItems(HorizontalAlign.Start)
            .margin({ left: 14 })
            .layoutWeight(1)

            // 更新时间
            Column() {
              Circle()
                .width(8)
                .height(8)
                .fill(this.errorMsg ? Colors.DANGER : Colors.SUCCESS)
              Text(this.lastUpdate || '--:--')
                .fontSize(10)
                .fontColor(Colors.TEXT_MUTED)
                .margin({ top: 4 })
            }
            .alignItems(HorizontalAlign.Center)
          }
          .width('100%')
          .padding(16)
          .backgroundColor(Colors.BG_CARD)
          .borderRadius(16)
        }

        // ═══ 实时体征标题 ═══
        Row() {
          Circle()
            .width(8)
            .height(8)
            .fill(Colors.SUCCESS)
          Text(' 实时生命体征')
            .fontSize(16)
            .fontWeight(600)
            .fontColor(Colors.TEXT_PRIMARY)
        }
        .width('100%')
        .margin({ top: 20, bottom: 12 })

        // ═══ 6个体征卡片 (2列网格) ═══
        GridRow({ columns: 2, gutter: 10 }) {
          // 心率
          GridCol() {
            VitalCard({
              label: '心率',
              icon: '♡',
              value: this.vitals ? `${this.vitals.heart_rate}` : '—',
              unit: 'bpm',
              level: this.hrLevel(),
              trend: '稳定'
            })
          }
          // 血压
          GridCol() {
            VitalCard({
              label: '血压',
              icon: '⊘',
              value: this.vitals ? `${this.vitals.blood_pressure_sys}/${this.vitals.blood_pressure_dia}` : '—/—',
              unit: 'mmHg',
              level: this.bpLevel(),
              trend: '稳定'
            })
          }
          // 血氧
          GridCol() {
            VitalCard({
              label: '血氧',
              icon: '◎',
              value: this.vitals ? `${this.vitals.blood_oxygen}` : '—',
              unit: '%SpO₂',
              level: this.spo2Level(),
              trend: '正常'
            })
          }
          // 血糖
          GridCol() {
            VitalCard({
              label: '血糖',
              icon: '◇',
              value: this.vitals ? `${this.vitals.blood_glucose}` : '—',
              unit: 'mmol/L',
              level: this.glucoseLevel(),
              trend: '正常'
            })
          }
          // 体温
          GridCol() {
            VitalCard({
              label: '体温',
              icon: '◌',
              value: this.vitals ? `${this.vitals.temperature}` : '—',
              unit: '°C',
              level: this.tempLevel(),
              trend: '正常'
            })
          }
          // 睡姿
          GridCol() {
            VitalCard({
              label: '睡姿',
              icon: '⊡',
              value: this.vitals ? (POSTURE_NAMES[this.vitals.sleep_posture] || this.vitals.sleep_posture) : '—',
              unit: '当前体位',
              level: 'normal',
              trend: '正常'
            })
          }
        }

        // ═══ 错误提示 ═══
        if (this.errorMsg) {
          Row() {
            Text(`⚠ 数据获取失败: ${this.errorMsg}`)
              .fontSize(12)
              .fontColor(Colors.WARNING)
          }
          .width('100%')
          .padding(12)
          .backgroundColor('#2A2215')
          .borderRadius(10)
          .margin({ top: 12 })
        }

        // ═══ 底部信息 ═══
        Text('💝 24小时智能守护，让爱不缺席')
          .fontSize(12)
          .fontColor(Colors.TEXT_MUTED)
          .margin({ top: 24, bottom: 20 })
          .textAlign(TextAlign.Center)
          .width('100%')
      }
      .padding(16)
    }
    .width('100%')
    .height('100%')
    .backgroundColor(Colors.BG_DARK)
    .scrollBar(BarState.Off)
  }
}
