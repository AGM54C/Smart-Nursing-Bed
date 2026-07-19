/**
 * AgentSwarmPage - 智能体集群 (临床风格)
 */
import { apiGet } from '../common/ApiService';
import { API, POLL_INTERVAL_SWARM, Colors } from '../common/Constants';
import { SwarmStatus, AgentDetail, AgentListResponse } from '../common/Types';
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
      const statusRaw = await apiGet(API.SWARM_STATUS);
      const agentsRaw = await apiGet(API.SWARM_AGENTS);
      const status: SwarmStatus = JSON.parse(statusRaw) as SwarmStatus;
      const agentsResp: AgentListResponse = JSON.parse(agentsRaw) as AgentListResponse;
      this.swarmStatus = status;
      this.agentDetails = agentsResp.agents;
      this.isLoading = false;
    } catch (e) {
      console.error('[AgentSwarm] Fetch failed:' + (e as Error).message);
    }
  }

  build() {
    Scroll() {
      Column() {
        // ═══ 标题 ═══
        Column() {
          Row() {
            Column()
              .width(3)
              .height(16)
              .backgroundColor('#007AFF')
              .borderRadius(2)
            Text('智能体集群')
              .fontSize(16)
              .fontWeight(600)
              .fontColor('#E5E5EA')
              .margin({ left: 8 })
          }
          .alignItems(VerticalAlign.Center)

          Text('Multi-Agent Swarm v4.0')
            .fontSize(11)
            .fontColor('#48484A')
            .margin({ top: 4, left: 11 })
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)
        .padding({ bottom: 14 })

        // ═══ Agent 卡片 ═══
        this.SubTitle('专科智能体')
        GridRow({ columns: 2, gutter: 8 }) {
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

        // ═══ 安全架构 ═══
        this.SubTitle('安全分级架构')
        if (this.swarmStatus) {
          Column({ space: 1 }) {
            this.SafetyRow('L0', this.swarmStatus.safety.L0, '#48484A')
            this.SafetyRow('L1', this.swarmStatus.safety.L1, '#34C759')
            this.SafetyRow('L2', this.swarmStatus.safety.L2, '#007AFF')
            this.SafetyRow('L3', this.swarmStatus.safety.L3, '#FF9F0A')
          }
          .width('100%')
          .padding(12)
          .backgroundColor('#0D0D11')
          .borderRadius(10)
          .borderWidth(0.5)
          .borderColor('#1C1C1E')
        }

        // ═══ 系统能力 ═══
        this.SubTitle('系统能力')
        if (this.swarmStatus) {
          Column({ space: 6 }) {
            this.CapRow('协调器', this.swarmStatus.capabilities.coordinator)
            this.CapRow('邮箱', this.swarmStatus.capabilities.mailbox)
            this.CapRow('记忆', this.swarmStatus.capabilities.memory)
            this.CapRow('权限', this.swarmStatus.capabilities.permission)
          }
          .width('100%')
          .padding(12)
          .backgroundColor('#0D0D11')
          .borderRadius(10)
          .borderWidth(0.5)
          .borderColor('#1C1C1E')
        }

        // ═══ 工具权限 ═══
        this.SubTitle('工具权限')
        ForEach(this.agentDetails, (agent: AgentDetail) => {
          Column() {
            Row() {
              Text(agent.display_name)
                .fontSize(13)
                .fontWeight(600)
                .fontColor('#E5E5EA')
              Text(`P${agent.priority}`)
                .fontSize(10)
                .fontColor('#007AFF')
                .padding({ left: 6, right: 6, top: 2, bottom: 2 })
                .backgroundColor('#0A1A2E')
                .borderRadius(4)
            }
            .width('100%')
            .justifyContent(FlexAlign.SpaceBetween)

            Text(`触发: ${agent.triggers.join(', ')}`)
              .fontSize(11)
              .fontColor('#636366')
              .margin({ top: 6 })
              .width('100%')

            Flex({ wrap: FlexWrap.Wrap }) {
              ForEach(agent.allowed_actions, (action: string) => {
                Text(action)
                  .fontSize(10)
                  .fontColor('#8E8E93')
                  .padding({ left: 6, right: 6, top: 2, bottom: 2 })
                  .backgroundColor('#1C1C1E')
                  .borderRadius(4)
                  .margin({ right: 4, top: 4 })
              })
            }
            .width('100%')
            .margin({ top: 6 })
          }
          .width('100%')
          .padding(12)
          .backgroundColor('#0D0D11')
          .borderRadius(10)
          .margin({ bottom: 6 })
          .borderWidth(0.5)
          .borderColor('#1C1C1E')
        })

        Blank().height(20)
      }
      .padding(14)
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#000000')
    .scrollBar(BarState.Off)
  }

  @Builder
  SubTitle(title: string) {
    Row() {
      Column()
        .width(2)
        .height(12)
        .backgroundColor('#636366')
        .borderRadius(1)
      Text(title)
        .fontSize(13)
        .fontWeight(600)
        .fontColor('#8E8E93')
        .margin({ left: 6 })
    }
    .width('100%')
    .margin({ top: 18, bottom: 8 })
    .alignItems(VerticalAlign.Center)
  }

  @Builder
  SafetyRow(level: string, desc: string, color: string) {
    Row() {
      Text(level)
        .fontSize(11)
        .fontWeight(700)
        .fontColor(color)
        .width(28)
        .letterSpacing(0.5)
      Column()
        .height(4)
        .backgroundColor(color + '35')
        .borderRadius(2)
        .layoutWeight(1)
        .margin({ left: 6, right: 6 })
      Text(desc)
        .fontSize(10)
        .fontColor('#636366')
        .constraintSize({ maxWidth: '55%' })
        .maxLines(1)
        .textOverflow({ overflow: TextOverflow.Ellipsis })
    }
    .width('100%')
    .height(26)
    .alignItems(VerticalAlign.Center)
  }

  @Builder
  CapRow(name: string, desc: string) {
    Row() {
      Text(name)
        .fontSize(12)
        .fontColor('#8E8E93')
        .width(50)
      Text(desc)
        .fontSize(12)
        .fontColor('#AEAEB2')
        .layoutWeight(1)
    }
    .width('100%')
  }
}
