/**
 * AlertsPage - 告警中心 (临床监护风格)
 */
import { apiGet, apiPut, RequestBody } from '../common/ApiService';
import { API, POLL_INTERVAL_ALERTS, Colors } from '../common/Constants';
import { AlertData } from '../common/Types';

@Component
export struct AlertsPage {
  @State alerts: AlertData[] = [];
  @State isLoading: boolean = true;
  @State filter: string = 'all';

  private pollingTimer: number = -1;

  aboutToAppear(): void {
    this.fetchAlerts();
    this.pollingTimer = setInterval(() => {
      this.fetchAlerts();
    }, POLL_INTERVAL_ALERTS);
  }

  aboutToDisappear(): void {
    if (this.pollingTimer !== -1) clearInterval(this.pollingTimer);
  }

  private async fetchAlerts(): Promise<void> {
    try {
      const raw = await apiGet(API.ALERTS);
      this.alerts = JSON.parse(raw) as AlertData[];
      this.isLoading = false;
    } catch (e) {
      console.error('[Alerts] Fetch failed:' + (e as Error).message);
    }
  }

  private async updateAlertStatus(id: number, newStatus: string): Promise<void> {
    try {
      const bodyObj = new RequestBody();
      bodyObj.status = newStatus;
      const body = JSON.stringify(bodyObj);
      await apiPut(API.ALERT_UPDATE(id), body);
      const newList: AlertData[] = [];
      for (let i = 0; i < this.alerts.length; i++) {
        if (this.alerts[i].id === id) {
          const updated = new AlertData();
          updated.id = this.alerts[i].id;
          updated.patient_id = this.alerts[i].patient_id;
          updated.alert_type = this.alerts[i].alert_type;
          updated.metric = this.alerts[i].metric;
          updated.value = this.alerts[i].value;
          updated.threshold = this.alerts[i].threshold;
          updated.message = this.alerts[i].message;
          updated.status = newStatus;
          updated.created_at = this.alerts[i].created_at;
          newList.push(updated);
        } else {
          newList.push(this.alerts[i]);
        }
      }
      this.alerts = newList;
    } catch (e) {
      console.error('[Alerts] Update failed:' + (e as Error).message);
    }
  }

  private getFilteredAlerts(): AlertData[] {
    if (this.filter === 'all') return this.alerts;
    return this.alerts.filter((a: AlertData) => a.status === this.filter);
  }

  private getAlertColor(alert: AlertData): string {
    if (alert.message && (alert.message.includes('危急') || alert.message.includes('critical'))) return '#FF3B5C';
    if (alert.alert_type === 'fall') return '#FF3B5C';
    if (alert.status === 'active') return '#FF9F0A';
    return '#48484A';
  }

  private getLevelLabel(alert: AlertData): string {
    if (alert.alert_type === 'vital_sign') return 'VITAL';
    if (alert.alert_type === 'pressure') return 'PRESS';
    if (alert.alert_type === 'fall') return 'FALL';
    return 'ALERT';
  }

  private formatTime(dateStr: string): string {
    try {
      const d = new Date(dateStr);
      const m = d.getMonth() + 1;
      const day = d.getDate();
      const h = d.getHours();
      const min = d.getMinutes().toString().padStart(2, '0');
      return `${m}/${day} ${h}:${min}`;
    } catch (e) {
      return dateStr;
    }
  }

  private getActiveCount(): number {
    return this.alerts.filter((a: AlertData) => a.status === 'active').length;
  }

  build() {
    Column() {
      // ═══ 顶栏 ═══
      Row() {
        Column()
          .width(3)
          .height(16)
          .backgroundColor(this.getActiveCount() > 0 ? '#FF3B5C' : '#34C759')
          .borderRadius(2)
        Text('告警管理')
          .fontSize(16)
          .fontWeight(600)
          .fontColor('#E5E5EA')
          .margin({ left: 8 })

        Blank()

        if (this.getActiveCount() > 0) {
          Row() {
            Circle()
              .width(6)
              .height(6)
              .fill('#FF3B5C')
              .margin({ right: 4 })
            Text(`${this.getActiveCount()} 条活跃`)
              .fontSize(12)
              .fontColor('#FF3B5C')
          }
        }
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 14, bottom: 12 })
      .backgroundColor('#0C0C0E')
      .alignItems(VerticalAlign.Center)

      // ═══ 筛选 ═══
      Row({ space: 6 }) {
        ForEach(['all', 'active', 'acknowledged', 'resolved'], (f: string) => {
          Text(f === 'all' ? '全部' : f === 'active' ? '活跃' : f === 'acknowledged' ? '已确认' : '已处理')
            .fontSize(12)
            .fontWeight(this.filter === f ? 600 : 400)
            .fontColor(this.filter === f ? '#007AFF' : '#636366')
            .padding({ left: 12, right: 12, top: 6, bottom: 6 })
            .backgroundColor(this.filter === f ? '#0A1A2E' : 'transparent')
            .borderRadius(6)
            .borderWidth(this.filter === f ? 0.5 : 0)
            .borderColor('#007AFF40')
            .onClick(() => { this.filter = f; })
        })
      }
      .width('100%')
      .padding({ left: 16, right: 16, bottom: 10 })

      // ═══ 列表 ═══
      if (this.getFilteredAlerts().length === 0) {
        Column() {
          Text('—')
            .fontSize(36)
            .fontColor('#2C2C2E')
            .margin({ top: 80 })
          Text('暂无告警记录')
            .fontSize(13)
            .fontColor('#48484A')
            .margin({ top: 12 })
        }
        .width('100%')
        .alignItems(HorizontalAlign.Center)
      } else {
        List({ space: 6 }) {
          ForEach(this.getFilteredAlerts(), (alert: AlertData) => {
            ListItem() {
              Column() {
                Row() {
                  // 类型标签
                  Text(this.getLevelLabel(alert))
                    .fontSize(10)
                    .fontWeight(700)
                    .fontColor(this.getAlertColor(alert))
                    .padding({ left: 6, right: 6, top: 2, bottom: 2 })
                    .backgroundColor(this.getAlertColor(alert) + '18')
                    .borderRadius(3)
                    .letterSpacing(0.5)

                  Text(alert.message)
                    .fontSize(13)
                    .fontColor('#E5E5EA')
                    .margin({ left: 8 })
                    .layoutWeight(1)
                    .maxLines(2)
                }
                .width('100%')

                Row() {
                  Text(`${alert.metric}: ${alert.value}`)
                    .fontSize(11)
                    .fontColor(this.getAlertColor(alert))
                  Text(this.formatTime(alert.created_at))
                    .fontSize(11)
                    .fontColor('#48484A')
                }
                .width('100%')
                .justifyContent(FlexAlign.SpaceBetween)
                .margin({ top: 8 })

                if (alert.status === 'active') {
                  Row({ space: 8 }) {
                    Button('确认')
                      .type(ButtonType.Normal)
                      .fontSize(12)
                      .height(30)
                      .backgroundColor('#007AFF')
                      .borderRadius(6)
                      .onClick(() => this.updateAlertStatus(alert.id, 'acknowledged'))
                    Button('已处理')
                      .type(ButtonType.Normal)
                      .fontSize(12)
                      .height(30)
                      .backgroundColor('#1C1C1E')
                      .fontColor('#8E8E93')
                      .borderRadius(6)
                      .onClick(() => this.updateAlertStatus(alert.id, 'resolved'))
                  }
                  .width('100%')
                  .justifyContent(FlexAlign.End)
                  .margin({ top: 8 })
                } else {
                  Text(alert.status === 'acknowledged' ? '已确认' : '已处理')
                    .fontSize(11)
                    .fontColor('#34C759')
                    .margin({ top: 8 })
                }
              }
              .padding(14)
              .backgroundColor('#0D0D11')
              .borderRadius(10)
              .borderWidth(0.5)
              .borderColor(this.getAlertColor(alert) + '20')
            }
          })
        }
        .padding({ left: 12, right: 12 })
        .layoutWeight(1)
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#000000')
  }
}
