/**
 * AlertsPage - 告警中心
 *
 * 展示所有活跃告警，支持状态流转
 */
import { apiGet, apiPut } from '../common/ApiService';
import { API, POLL_INTERVAL_ALERTS, Colors } from '../common/Constants';
import { AlertData } from '../common/Types';

@Component
export struct AlertsPage {
  @State alerts: AlertData[] = [];
  @State isLoading: boolean = true;
  @State filter: string = 'all';   // all | active | acknowledged | resolved

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
      const data = await apiGet<AlertData[]>(API.ALERTS);
      this.alerts = data;
      this.isLoading = false;
    } catch (e) {
      console.error('[Alerts] Fetch failed:', (e as Error).message);
    }
  }

  private async updateAlertStatus(id: number, newStatus: string): Promise<void> {
    try {
      await apiPut<object>(API.ALERT_UPDATE(id), { status: newStatus });
      // 更新本地状态
      const idx = this.alerts.findIndex(a => a.id === id);
      if (idx >= 0) {
        const updated = { ...this.alerts[idx], status: newStatus } as AlertData;
        const newList = [...this.alerts];
        newList[idx] = updated;
        this.alerts = newList;
      }
    } catch (e) {
      console.error('[Alerts] Update failed:', (e as Error).message);
    }
  }

  private getFilteredAlerts(): AlertData[] {
    if (this.filter === 'all') return this.alerts;
    return this.alerts.filter(a => a.status === this.filter);
  }

  private getAlertColor(alert: AlertData): string {
    if (alert.message && (alert.message.includes('危急') || alert.message.includes('critical'))) return Colors.DANGER;
    if (alert.alert_type === 'fall') return Colors.DANGER;
    if (alert.status === 'active') return Colors.WARNING;
    return Colors.TEXT_MUTED;
  }

  private getAlertIcon(alert: AlertData): string {
    switch (alert.alert_type) {
      case 'vital_sign': return '🫀';
      case 'pressure': return '🛡️';
      case 'fall': return '🚨';
      default: return '⚠️';
    }
  }

  private formatTime(dateStr: string): string {
    try {
      const d = new Date(dateStr);
      return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
    } catch (e) {
      return dateStr;
    }
  }

  private getActiveCount(): number {
    return this.alerts.filter(a => a.status === 'active').length;
  }

  build() {
    Column() {
      // ═══ 标题 + 活跃数 ═══
      Row() {
        Text('🚨 告警中心')
          .fontSize(20)
          .fontWeight(700)
          .fontColor(Colors.TEXT_PRIMARY)

        if (this.getActiveCount() > 0) {
          Text(`${this.getActiveCount()}`)
            .fontSize(13)
            .fontWeight(700)
            .fontColor('#FFF')
            .padding({ left: 10, right: 10, top: 3, bottom: 3 })
            .backgroundColor(Colors.DANGER)
            .borderRadius(12)
        }
      }
      .width('100%')
      .justifyContent(FlexAlign.SpaceBetween)
      .padding({ left: 16, right: 16, top: 16, bottom: 12 })

      // ═══ 筛选栏 ═══
      Row({ space: 8 }) {
        ForEach(['all', 'active', 'acknowledged', 'resolved'], (f: string) => {
          Text(f === 'all' ? '全部' : f === 'active' ? '活跃' : f === 'acknowledged' ? '已确认' : '已解决')
            .fontSize(12)
            .fontWeight(this.filter === f ? 600 : 400)
            .fontColor(this.filter === f ? Colors.TEAL_500 : Colors.TEXT_MUTED)
            .padding({ left: 12, right: 12, top: 6, bottom: 6 })
            .backgroundColor(this.filter === f ? Colors.TEAL_500 + '20' : 'transparent')
            .borderRadius(16)
            .onClick(() => { this.filter = f; })
        })
      }
      .width('100%')
      .padding({ left: 16, right: 16, bottom: 12 })

      // ═══ 告警列表 ═══
      if (this.getFilteredAlerts().length === 0) {
        Column() {
          Text('✓')
            .fontSize(48)
            .fontColor(Colors.SUCCESS)
            .margin({ top: 60 })
          Text('暂无告警')
            .fontSize(14)
            .fontColor(Colors.TEXT_MUTED)
            .margin({ top: 12 })
        }
        .width('100%')
        .alignItems(HorizontalAlign.Center)
      } else {
        List({ space: 8 }) {
          ForEach(this.getFilteredAlerts(), (alert: AlertData) => {
            ListItem() {
              Column() {
                // 告警头部
                Row() {
                  Text(this.getAlertIcon(alert))
                    .fontSize(18)
                  Text(alert.message)
                    .fontSize(13)
                    .fontWeight(500)
                    .fontColor(Colors.TEXT_PRIMARY)
                    .margin({ left: 8 })
                    .layoutWeight(1)
                    .maxLines(2)
                }
                .width('100%')

                // 详情行
                Row() {
                  Text(`${alert.metric}: ${alert.value}`)
                    .fontSize(11)
                    .fontColor(this.getAlertColor(alert))
                  Text(this.formatTime(alert.created_at))
                    .fontSize(11)
                    .fontColor(Colors.TEXT_MUTED)
                }
                .width('100%')
                .justifyContent(FlexAlign.SpaceBetween)
                .margin({ top: 8 })

                // 操作按钮
                if (alert.status === 'active') {
                  Row({ space: 8 }) {
                    Button('确认处理')
                      .type(ButtonType.Normal)
                      .fontSize(12)
                      .height(30)
                      .backgroundColor(Colors.TEAL_600)
                      .borderRadius(8)
                      .onClick(() => this.updateAlertStatus(alert.id, 'acknowledged'))

                    Button('已解决')
                      .type(ButtonType.Normal)
                      .fontSize(12)
                      .height(30)
                      .backgroundColor(Colors.BG_SURFACE)
                      .fontColor(Colors.TEXT_SECONDARY)
                      .borderRadius(8)
                      .onClick(() => this.updateAlertStatus(alert.id, 'resolved'))
                  }
                  .width('100%')
                  .justifyContent(FlexAlign.End)
                  .margin({ top: 8 })
                } else {
                  Text(alert.status === 'acknowledged' ? '✓ 已确认' : '✓ 已解决')
                    .fontSize(11)
                    .fontColor(Colors.SUCCESS)
                    .margin({ top: 8 })
                }
              }
              .padding(14)
              .backgroundColor(Colors.BG_CARD)
              .borderRadius(12)
              .borderWidth(1)
              .borderColor(this.getAlertColor(alert) + '30')
            }
          })
        }
        .padding({ left: 16, right: 16 })
        .layoutWeight(1)
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor(Colors.BG_DARK)
  }
}
