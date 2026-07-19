/**
 * VitalCard - 体征数据卡片 (医疗监护风格)
 *
 * 模仿飞利浦IntelliVue/迈瑞监护仪的数值展示:
 *   大号数值 + 小号标签 + 状态指示条
 */
import { Colors } from '../common/Constants';

@Component
export struct VitalCard {
  @Prop label: string = '';
  @Prop icon: string = '';
  @Prop value: string = '—';
  @Prop unit: string = '';
  @Prop level: string = 'normal';
  @Prop trend: string = '稳定';

  private getAccentColor(): string {
    if (this.level === 'critical') return '#FF3B5C';
    if (this.level === 'warning') return '#FF9F0A';
    return '#34C759';
  }

  private getBgColor(): string {
    if (this.level === 'critical') return '#1A0A10';
    if (this.level === 'warning') return '#1A1408';
    return '#0D1A14';
  }

  build() {
    Column() {
      // 顶部: 标签 + 状态条
      Row() {
        // 状态指示竖条
        Column()
          .width(3)
          .height(14)
          .backgroundColor(this.getAccentColor())
          .borderRadius(2)

        Text(this.label)
          .fontSize(11)
          .fontWeight(500)
          .fontColor('#8E8E93')
          .margin({ left: 6 })
          .letterSpacing(0.5)

        Blank()

        Text(this.unit)
          .fontSize(10)
          .fontColor('#636366')
      }
      .width('100%')
      .alignItems(VerticalAlign.Center)

      // 核心数值 (大号)
      Text(this.value)
        .fontSize(36)
        .fontWeight(700)
        .fontColor(this.getAccentColor())
        .margin({ top: 6, bottom: 2 })
        .fontFamily('HarmonyOS Sans')

      // 趋势
      Text(this.trend)
        .fontSize(10)
        .fontColor('#636366')
    }
    .width('100%')
    .padding({ left: 14, right: 14, top: 12, bottom: 10 })
    .backgroundColor(this.getBgColor())
    .borderRadius(12)
    .borderWidth(0.5)
    .borderColor(this.getAccentColor() + '25')
    .alignItems(HorizontalAlign.Start)
  }
}
