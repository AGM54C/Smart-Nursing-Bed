/**
 * AgentSwarmPage - Multi-Agent Swarm 状态可视化
 *
 * 鸿蒙独占页面 (Web端没有！)
 * 展示4个专科Agent运行状态 + L0-L3安全层 + Coordinator架构
 */
import { apiGet } from '../common/ApiService';
import { API, POLL_INTERVAL_SWARM, Colors } from '../common/Constants';
import { SwarmStatus, AgentDetail } from '../common/Types';
import { AgentCard } from '../components/AgentCard';

@Component
export struct AgentSwarmPage {
  @State swarmStatus: SwarmStatus | null = null;
  @State agentDetails: AgentDetail[] = [];
  @State isLoading: boolean = true;

  private pollingTimer: number = -1;

  aboutToAppear(): void {
    this.fetchAll();
    this.pollingTimer = setInterval(() => {
      this.fetchAll();
    }, POLL_INTERVAL_SWARM);
  }

  aboutToDisappear(): void {
    if (this.pollingTimer !== -1) {
      clearInterval(this.pollingTimer);
    }
  }

  private async fetchAll(): Promise<void> {
    try {
      const [status, agents] = await Promise.all([
        apiGet<SwarmStatus>(API.SWARM_STATUS),
        apiGet<{ total: number; agents: AgentDetail[] }>(API.SWARM_AGENTS),
      ]);
      this.swarmStatus = status;
      this.agentDetails = agents.agents;
      this.isLoading = false;
    } catch (e) {
      console.error('[AgentSwarm] Fetch failed:', (e as Error).message);
    }
  }

  build() {
    Scroll() {
      Column() {
        // ═══ 标题 ═══
        Column() {
          Text('🧠 Multi-Agent Nursing Swarm')
            .fontSize(20)
            .fontWeight(700)
            .fontColor(Colors.TEXT_PRIMARY)
          Text('v4.0 · OpenHarness Architecture')
            .fontSize(12)
            .fontColor(Colors.TEAL_500)
            .margin({ top: 4 })
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)
        .padding({ bottom: 16 })

        // ═══ 4个Agent卡片 (2×2网格) ═══
        Text('专科 Agent 集群')
          .fontSize(14)
          .fontWeight(600)
          .fontColor(Colors.TEXT_SECONDARY)
          .width('100%')
          .margin({ bottom: 10 })

        GridRow({ columns: 2, gutter: 10 }) {
          ForEach(this.agentDetails, (agent: AgentDetail) => {
            GridCol() {
              AgentCard({
                agentName: agent.name,
                displayName: agent.display_name,
                icon: agent.icon,
                priority: agent.priority,
                status: 'active',
                color: agent.color,
                whenToUse: agent.when_to_use,
                queryInterval: agent.query_interval,
              })
            }
          })
        }

        // ═══ 安全架构 L0-L3 ═══
        Text('安全架构')
          .fontSize(14)
          .fontWeight(600)
          .fontColor(Colors.TEXT_SECONDARY)
          .width('100%')
          .margin({ top: 20, bottom: 10 })

        if (this.swarmStatus) {
          Column() {
            this.SafetyRow('L0', this.swarmStatus.safety.L0, Colors.TEXT_MUTED, 1.0)
            this.SafetyRow('L1', this.swarmStatus.safety.L1, Colors.TEAL_500, 0.9)
            this.SafetyRow('L2', this.swarmStatus.safety.L2, Colors.INFO, 0.7)
            this.SafetyRow('L3', this.swarmStatus.safety.L3, Colors.WARNING, 0.5)
          }
          .width('100%')
          .padding(14)
          .backgroundColor(Colors.BG_CARD)
          .borderRadius(14)
        }

        // ═══ 核心能力 ═══
        Text('核心能力')
          .fontSize(14)
          .fontWeight(600)
          .fontColor(Colors.TEXT_SECONDARY)
          .width('100%')
          .margin({ top: 20, bottom: 10 })

        if (this.swarmStatus) {
          Column({ space: 8 }) {
            this.CapabilityItem('🎯', 'Coordinator', this.swarmStatus.capabilities.coordinator)
            this.CapabilityItem('📬', 'Mailbox', this.swarmStatus.capabilities.mailbox)
            this.CapabilityItem('🧠', 'Memory', this.swarmStatus.capabilities.memory)
            this.CapabilityItem('🔐', 'Permission', this.swarmStatus.capabilities.permission)
          }
          .width('100%')
          .padding(14)
          .backgroundColor(Colors.BG_CARD)
          .borderRadius(14)
        }

        // ═══ Agent详情列表 ═══
        Text('Agent 工具权限')
          .fontSize(14)
          .fontWeight(600)
          .fontColor(Colors.TEXT_SECONDARY)
          .width('100%')
          .margin({ top: 20, bottom: 10 })

        ForEach(this.agentDetails, (agent: AgentDetail) => {
          Column() {
            Row() {
              Text(`${agent.icon} ${agent.display_name}`)
                .fontSize(14)
                .fontWeight(600)
                .fontColor(Colors.TEXT_PRIMARY)
              Text(`P${agent.priority}`)
                .fontSize(11)
                .fontColor(Colors.TEAL_500)
                .padding({ left: 8, right: 8, top: 2, bottom: 2 })
                .backgroundColor(Colors.TEAL_500 + '20')
                .borderRadius(10)
            }
            .width('100%')
            .justifyContent(FlexAlign.SpaceBetween)

            // 触发条件
            Text(`触发: ${agent.triggers.join(', ')}`)
              .fontSize(11)
              .fontColor(Colors.TEXT_MUTED)
              .margin({ top: 6 })
              .width('100%')

            // 允许动作
            Flex({ wrap: FlexWrap.Wrap }) {
              ForEach(agent.allowed_actions, (action: string) => {
                Text(action)
                  .fontSize(10)
                  .fontColor(Colors.TEXT_SECONDARY)
                  .padding({ left: 6, right: 6, top: 2, bottom: 2 })
                  .backgroundColor(Colors.BG_SURFACE)
                  .borderRadius(6)
                  .margin({ right: 4, top: 4 })
              })
            }
            .width('100%')
            .margin({ top: 6 })
          }
          .width('100%')
          .padding(12)
          .backgroundColor(Colors.BG_CARD)
          .borderRadius(12)
          .margin({ bottom: 8 })
        })

        Blank().height(20)
      }
      .padding(16)
    }
    .width('100%')
    .height('100%')
    .backgroundColor(Colors.BG_DARK)
    .scrollBar(BarState.Off)
  }

  @Builder
  SafetyRow(level: string, desc: string, color: string, widthRatio: number) {
    Row() {
      Text(level)
        .fontSize(12)
        .fontWeight(700)
        .fontColor(color)
        .width(30)

      Column()
        .height(6)
        .backgroundColor(color + '40')
        .borderRadius(3)
        .layoutWeight(1)
        .margin({ left: 8, right: 8 })

      Text(desc)
        .fontSize(10)
        .fontColor(Colors.TEXT_MUTED)
        .constraintSize({ maxWidth: '55%' })
        .maxLines(1)
        .textOverflow({ overflow: TextOverflow.Ellipsis })
    }
    .width('100%')
    .height(28)
    .alignItems(VerticalAlign.Center)
  }

  @Builder
  CapabilityItem(icon: string, name: string, desc: string) {
    Row() {
      Text(icon)
        .fontSize(16)
      Column() {
        Text(name)
          .fontSize(13)
          .fontWeight(600)
          .fontColor(Colors.TEXT_PRIMARY)
        Text(desc)
          .fontSize(11)
          .fontColor(Colors.TEXT_MUTED)
          .margin({ top: 2 })
      }
      .alignItems(HorizontalAlign.Start)
      .margin({ left: 10 })
      .layoutWeight(1)
    }
    .width('100%')
  }
}
