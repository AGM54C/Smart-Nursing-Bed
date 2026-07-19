/**
 * AgentCard - AI Agent 状态卡片组件
 *
 * 展示单个专科Agent的运行状态、优先级、负责领域
 */
import { Colors } from '../common/Constants';

@Component
export struct AgentCard {
  @Prop agentName: string = '';
  @Prop displayName: string = '';
  @Prop icon: string = '🤖';
  @Prop priority: number = 0;
  @Prop status: string = 'active';
  @Prop color: string = 'green';
  @Prop whenToUse: string = '';
  @Prop queryInterval: number = 30;

  private getStatusColor(): string {
    return this.status === 'active' ? Colors.SUCCESS : Colors.TEXT_MUTED;
  }

  private getAgentColor(): string {
    switch (this.color) {
      case 'red': return Colors.AGENT_EMERGENCY;
      case 'green': return Colors.AGENT_VITALS;
      case 'blue': return Colors.AGENT_PRESSURE;
      case 'yellow': return Colors.AGENT_COMPANION;
      default: return Colors.TEAL_500;
    }
  }

  build() {
    Column() {
      // 头部: 图标 + 状态灯
      Row() {
        Text(this.icon)
          .fontSize(28)

        // 状态指示灯
        Circle()
          .width(8)
          .height(8)
          .fill(this.getStatusColor())
          .margin({ left: 8 })
      }
      .width('100%')
      .justifyContent(FlexAlign.SpaceBetween)

      // Agent名称
      Text(this.displayName)
        .fontSize(14)
        .fontWeight(600)
        .fontColor(Colors.TEXT_PRIMARY)
        .margin({ top: 10 })

      // 优先级
      Text(`优先级: ${this.priority}`)
        .fontSize(11)
        .fontColor(this.getAgentColor())
        .margin({ top: 4 })

      // 查询间隔
      Text(`${this.queryInterval}s 轮询`)
        .fontSize(10)
        .fontColor(Colors.TEXT_MUTED)
        .margin({ top: 2 })

      // 职责描述
      if (this.whenToUse) {
        Text(this.whenToUse)
          .fontSize(10)
          .fontColor(Colors.TEXT_SECONDARY)
          .margin({ top: 8 })
          .maxLines(2)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
      }
    }
    .width('100%')
    .padding(14)
    .backgroundColor(Colors.BG_CARD)
    .borderRadius(14)
    .borderWidth(1)
    .borderColor(this.getAgentColor() + '30')  // 30% opacity border
    .alignItems(HorizontalAlign.Start)
  }
}
