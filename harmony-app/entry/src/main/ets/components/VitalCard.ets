/**
 * VitalCard - 体征数据卡片组件
 *
 * 显示单个体征指标 (心率/血压/血氧/血糖/体温/睡姿)
 * 根据数值自动变色: 绿色=正常, 橙色=警告, 红色=危急
 */
import { Colors } from '../common/Constants';

@Component
export struct VitalCard {
  @Prop label: string = '';
  @Prop icon: string = '';
  @Prop value: string = '—';
  @Prop unit: string = '';
  @Prop level: string = 'normal';   // normal | warning | critical
  @Prop trend: string = '稳定';

  private getColor(): string {
    switch (this.level) {
      case 'critical': return Colors.DANGER;
      case 'warning': return Colors.WARNING;
      default: return Colors.TEAL_500;
    }
  }

  private getBgColor(): string {
    switch (this.level) {
      case 'critical': return '#2A1525';
      case 'warning': return '#2A2215';
      default: return Colors.BG_CARD;
    }
  }

  private getTrendIcon(): string {
    if (this.trend.includes('↑') || this.trend.includes('升')) return '↑';
    if (this.trend.includes('↓') || this.trend.includes('降')) return '↓';
    return '—';
  }

  build() {
    Column() {
      // 标签行
      Row() {
        Text(this.icon)
          .fontSize(14)
        Text(' ' + this.label)
          .fontSize(13)
          .fontColor(Colors.TEXT_SECONDARY)
          .fontWeight(500)
      }
      .width('100%')
      .justifyContent(FlexAlign.Start)

      // 数值 (大字)
      Text(this.value)
        .fontSize(32)
        .fontWeight(700)
        .fontColor(this.getColor())
        .margin({ top: 8, bottom: 4 })

      // 单位
      Text(this.unit)
        .fontSize(12)
        .fontColor(Colors.TEXT_MUTED)

      // 趋势
      Text(`${this.getTrendIcon()} ${this.trend}`)
        .fontSize(11)
        .fontColor(Colors.TEXT_MUTED)
        .margin({ top: 6 })
    }
    .width('100%')
    .padding(16)
    .backgroundColor(this.getBgColor())
    .borderRadius(16)
    .alignItems(HorizontalAlign.Start)
  }
}
