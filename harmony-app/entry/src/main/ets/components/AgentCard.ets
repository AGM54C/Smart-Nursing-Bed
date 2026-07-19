/**
 * AgentCard - 智能体状态卡片 (临床风格)
 */
import { Colors } from '../common/Constants';

@Component
export struct AgentCard {
  @Prop agentName: string = '';
  @Prop displayName: string = '';
  @Prop icon: string = '';
  @Prop priority: number = 0;
  @Prop status: string = 'active';
  @Prop color: string = 'green';
  @Prop whenToUse: string = '';
  @Prop queryInterval: number = 30;

  private getAccentColor(): string {
    if (this.color === 'red') return '#FF3B5C';
    if (this.color === 'green') return '#34C759';
    if (this.color === 'blue') return '#007AFF';
    if (this.color === 'yellow') return '#FF9F0A';
    return '#34C759';
  }

  build() {
    Column() {
      // 顶部: 状态条 + 状态灯
      Row() {
        Column()
          .width(3)
          .height(12)
          .backgroundColor(this.getAccentColor())
          .borderRadius(2)
        Text(this.displayName)
          .fontSize(13)
          .fontWeight(600)
          .fontColor('#E5E5EA')
          .margin({ left: 6 })

        Blank()

        Circle()
          .width(6)
          .height(6)
          .fill(this.status === 'active' ? '#34C759' : '#48484A')
      }
      .width('100%')
      .alignItems(VerticalAlign.Center)

      // 优先级 + 间隔
      Text(`P${this.priority} · ${this.queryInterval}s`)
        .fontSize(10)
        .fontColor(this.getAccentColor())
        .margin({ top: 8 })

      // 描述
      if (this.whenToUse.length > 0) {
        Text(this.whenToUse)
          .fontSize(10)
          .fontColor('#636366')
          .margin({ top: 6 })
          .maxLines(2)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
      }
    }
    .width('100%')
    .padding(12)
    .backgroundColor('#0D0D11')
    .borderRadius(10)
    .borderWidth(0.5)
    .borderColor(this.getAccentColor() + '25')
    .alignItems(HorizontalAlign.Start)
  }
}
