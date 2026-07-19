/**
 * DashboardPage - 实时监护面板 (临床监护风格)
 *
 * 模仿 Philips IntelliVue / 迈瑞 BeneVision 床旁监护仪
 * - 深色背景 + 大号数值 + 状态指示条
 * - 顶部患者信息条
 * - 6宫格体征展示
 */
import { apiGet } from '../common/ApiService';
import { API, POLL_INTERVAL_VITALS, Colors, VitalRanges, PostureNames } from '../common/Constants';
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
    this.fetchVitals();
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
      const raw = await apiGet(API.PATIENTS);
      const patients: Patient[] = JSON.parse(raw) as Patient[];
      if (patients && patients.length > 0) {
        this.patient = patients[0];
        this.patientId = this.patient.id;
      }
    } catch (e) {
      console.error('[Dashboard] Load patient failed:' + (e as Error).message);
    }
  }

  private async fetchVitals(): Promise<void> {
    try {
      const raw = await apiGet(API.VITALS_LATEST(this.patientId));
      this.vitals = JSON.parse(raw) as VitalsData;
      this.isLoading = false;
      this.errorMsg = '';
      const d = new Date();
      this.lastUpdate = `${d.getHours()}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
    } catch (e) {
      this.errorMsg = (e as Error).message;
    }
  }

  private hrLevel(): string {
    if (!this.vitals) return 'normal';
    const hr = this.vitals.heart_rate;
    if (hr > VitalRanges.heart_rate.critHigh || hr < VitalRanges.heart_rate.critLow) return 'critical';
    if (hr > VitalRanges.heart_rate.high || hr < VitalRanges.heart_rate.low) return 'warning';
    return 'normal';
  }

  private spo2Level(): string {
    if (!this.vitals) return 'normal';
    const v = this.vitals.blood_oxygen;
    if (v < VitalRanges.blood_oxygen.critLow) return 'critical';
    if (v < VitalRanges.blood_oxygen.low) return 'warning';
    return 'normal';
  }

  private tempLevel(): string {
    if (!this.vitals) return 'normal';
    const v = this.vitals.temperature;
    if (v > VitalRanges.temperature.critHigh) return 'critical';
    if (v > VitalRanges.temperature.high) return 'warning';
    return 'normal';
  }

  private bpLevel(): string {
    if (!this.vitals) return 'normal';
    const sys = this.vitals.blood_pressure_sys;
    if (sys > VitalRanges.blood_pressure_sys.critHigh || sys < VitalRanges.blood_pressure_sys.critLow) return 'critical';
    if (sys > VitalRanges.blood_pressure_sys.high || sys < VitalRanges.blood_pressure_sys.low) return 'warning';
    return 'normal';
  }

  private glucoseLevel(): string {
    if (!this.vitals) return 'normal';
    const v = this.vitals.blood_glucose;
    if (v > VitalRanges.blood_glucose.critHigh || v < VitalRanges.blood_glucose.critLow) return 'critical';
    if (v > VitalRanges.blood_glucose.high || v < VitalRanges.blood_glucose.low) return 'warning';
    return 'normal';
  }

  build() {
    Column() {
      // ═══ 顶部患者信息条 (模仿监护仪顶栏) ═══
      Row() {
        // 在线状态灯
        Circle()
          .width(8)
          .height(8)
          .fill(this.errorMsg.length > 0 ? '#FF3B5C' : '#34C759')
          .margin({ right: 8 })

        if (this.patient) {
          Text(`${this.patient.name}`)
            .fontSize(15)
            .fontWeight(600)
            .fontColor('#E5E5EA')
          Text(`${this.patient.room_number}房${this.patient.bed_number}床`)
            .fontSize(12)
            .fontColor('#8E8E93')
            .margin({ left: 10 })
          Text(`${this.patient.age}岁`)
            .fontSize(12)
            .fontColor('#8E8E93')
            .margin({ left: 6 })
        }

        Blank()

        // 更新时间
        Text(this.lastUpdate.length > 0 ? this.lastUpdate : '--:--:--')
          .fontSize(12)
          .fontColor('#636366')
          .fontFamily('HarmonyOS Sans')
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 12, bottom: 10 })
      .backgroundColor('#0C0C0E')
      .alignItems(VerticalAlign.Center)

      // ═══ 体征监护区 ═══
      Scroll() {
        Column() {
          // 区域标题
          Row() {
            Column()
              .width(3)
              .height(14)
              .backgroundColor('#34C759')
              .borderRadius(2)
            Text('实时体征监测')
              .fontSize(14)
              .fontWeight(600)
              .fontColor('#E5E5EA')
              .margin({ left: 8 })
            Blank()
            Text('5s 自动刷新')
              .fontSize(10)
              .fontColor('#48484A')
          }
          .width('100%')
          .padding({ top: 14, bottom: 10 })
          .alignItems(VerticalAlign.Center)

          // ═══ 6宫格体征卡片 ═══
          GridRow({ columns: 2, gutter: 8 }) {
            GridCol() {
              VitalCard({
                label: 'HR 心率',
                icon: '',
                value: this.vitals ? `${this.vitals.heart_rate}` : '—',
                unit: 'bpm',
                level: this.hrLevel(),
                trend: '连续监测中'
              })
            }
            GridCol() {
              VitalCard({
                label: 'NIBP 血压',
                icon: '',
                value: this.vitals ? `${this.vitals.blood_pressure_sys}/${this.vitals.blood_pressure_dia}` : '—/—',
                unit: 'mmHg',
                level: this.bpLevel(),
                trend: '连续监测中'
              })
            }
            GridCol() {
              VitalCard({
                label: 'SpO₂ 血氧',
                icon: '',
                value: this.vitals ? `${this.vitals.blood_oxygen}` : '—',
                unit: '%',
                level: this.spo2Level(),
                trend: '连续监测中'
              })
            }
            GridCol() {
              VitalCard({
                label: 'GLU 血糖',
                icon: '',
                value: this.vitals ? `${this.vitals.blood_glucose}` : '—',
                unit: 'mmol/L',
                level: this.glucoseLevel(),
                trend: '连续监测中'
              })
            }
            GridCol() {
              VitalCard({
                label: 'TEMP 体温',
                icon: '',
                value: this.vitals ? `${this.vitals.temperature}` : '—',
                unit: '°C',
                level: this.tempLevel(),
                trend: '连续监测中'
              })
            }
            GridCol() {
              VitalCard({
                label: 'POSTURE 体位',
                icon: '',
                value: this.vitals ? PostureNames.get(this.vitals.sleep_posture) : '—',
                unit: '当前',
                level: 'normal',
                trend: '实时检测'
              })
            }
          }

          // ═══ 患者详情卡片 ═══
          if (this.patient) {
            Column() {
              Row() {
                Column()
                  .width(3)
                  .height(14)
                  .backgroundColor('#007AFF')
                  .borderRadius(2)
                Text('患者信息')
                  .fontSize(13)
                  .fontWeight(600)
                  .fontColor('#E5E5EA')
                  .margin({ left: 8 })
              }
              .width('100%')
              .margin({ bottom: 10 })

              this.InfoRow('诊断', `${this.patient.disease_type}`)
              this.InfoRow('详情', `${this.patient.disease_detail}`)
              this.InfoRow('入院', `${this.patient.admission_date}`)
              this.InfoRow('责任Agent', `${this.patient.assigned_agent}`)
            }
            .width('100%')
            .padding(14)
            .backgroundColor('#0D0D11')
            .borderRadius(12)
            .borderWidth(0.5)
            .borderColor('#1C1C1E')
            .margin({ top: 12 })
          }

          // ═══ 错误提示 ═══
          if (this.errorMsg.length > 0) {
            Row() {
              Column()
                .width(3)
                .height(14)
                .backgroundColor('#FF3B5C')
                .borderRadius(2)
              Text(`连接异常: ${this.errorMsg}`)
                .fontSize(12)
                .fontColor('#FF6B6B')
                .margin({ left: 8 })
            }
            .width('100%')
            .padding(12)
            .backgroundColor('#1A0A10')
            .borderRadius(10)
            .margin({ top: 12 })
            .alignItems(VerticalAlign.Center)
          }

          // 底部间距
          Blank().height(20)
        }
        .padding({ left: 12, right: 12 })
      }
      .layoutWeight(1)
      .scrollBar(BarState.Off)
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#000000')
  }

  @Builder
  InfoRow(label: string, value: string) {
    Row() {
      Text(label)
        .fontSize(12)
        .fontColor('#636366')
        .width(70)
      Text(value)
        .fontSize(12)
        .fontColor('#AEAEB2')
    }
    .width('100%')
    .margin({ bottom: 4 })
  }
}
