/**
 * ControlPage - 远程控制面板
 *
 * 通过树莓派Flask API直连控制:
 *   - 病床升降 (电动推杆)
 *   - 自主导航 (寻房)
 *   - 气囊控制 (充气/放气/减压)
 *   - NLC语音指令 (自然语言控制)
 */
import { piRequest } from '../common/ApiService';
import { API, Colors } from '../common/Constants';

@Component
export struct ControlPage {
  @State nlcInput: string = '';
  @State nlcResult: string = '';
  @State isExecuting: boolean = false;
  @State lastAction: string = '';
  @State piConnected: boolean = true;

  private async sendCommand(action: string, params?: object): Promise<void> {
    this.isExecuting = true;
    this.lastAction = action;
    try {
      const body = { action, params: params || {} };
      const result = await piRequest<{ status: string; message: string }>(API.PI_REMOTE, body);
      this.lastAction = `✅ ${action}: ${result.message || '已执行'}`;
      this.piConnected = true;
    } catch (e) {
      this.lastAction = `❌ ${action}: ${(e as Error).message}`;
      this.piConnected = false;
    }
    this.isExecuting = false;
  }

  private async sendNLC(): Promise<void> {
    const text = this.nlcInput.trim();
    if (!text) return;
    this.isExecuting = true;
    this.nlcResult = '解析中...';
    try {
      const result = await piRequest<{
        action: string;
        params: object;
        response: string;
        executed: boolean;
      }>(API.PI_NLC, { text });
      this.nlcResult = `${result.executed ? '✅' : '⚠️'} ${result.response || result.action}`;
      this.nlcInput = '';
    } catch (e) {
      this.nlcResult = `❌ ${(e as Error).message}`;
    }
    this.isExecuting = false;
  }

  build() {
    Scroll() {
      Column() {
        // ═══ 标题 ═══
        Row() {
          Text('🎮 病床远程控制')
            .fontSize(20)
            .fontWeight(700)
            .fontColor(Colors.TEXT_PRIMARY)

          Row() {
            Circle()
              .width(8)
              .height(8)
              .fill(this.piConnected ? Colors.SUCCESS : Colors.DANGER)
            Text(this.piConnected ? '树莓派在线' : '离线')
              .fontSize(11)
              .fontColor(this.piConnected ? Colors.SUCCESS : Colors.DANGER)
              .margin({ left: 4 })
          }
        }
        .width('100%')
        .justifyContent(FlexAlign.SpaceBetween)

        // ═══ 病床升降 ═══
        this.SectionTitle('🛏️ 病床升降')
        Row({ space: 12 }) {
          this.ControlButton('↑ 抬靠背', Colors.TEAL_600, () => this.sendCommand('raise_bed'))
          this.ControlButton('↓ 降靠背', Colors.BG_SURFACE, () => this.sendCommand('lower_bed'))
        }
        .width('100%')

        // ═══ 自主导航 ═══
        this.SectionTitle('🗺️ 自主导航')
        Row({ space: 10 }) {
          this.ControlButton('301房', Colors.INFO + 'CC', () => this.sendCommand('navigate', { room: '301' }))
          this.ControlButton('302房', Colors.INFO + 'CC', () => this.sendCommand('navigate', { room: '302' }))
          this.ControlButton('303房', Colors.INFO + 'CC', () => this.sendCommand('navigate', { room: '303' }))
        }
        .width('100%')

        Row({ space: 12 }) {
          this.ControlButton('⏹ 停止', Colors.DANGER + 'CC', () => this.sendCommand('stop_nav'))
          this.ControlButton('🏠 返回', Colors.WARNING + 'CC', () => this.sendCommand('return_home'))
        }
        .width('100%')
        .margin({ top: 8 })

        // ═══ 气囊控制 ═══
        this.SectionTitle('💨 气囊控制')
        Row({ space: 10 }) {
          this.ControlButton('充气', Colors.TEAL_600, () => this.sendCommand('air_inflate'))
          this.ControlButton('放气', Colors.BG_SURFACE, () => this.sendCommand('air_deflate'))
          this.ControlButton('自动减压', Colors.AGENT_PRESSURE + 'CC', () => this.sendCommand('air_relief_cycle'))
        }
        .width('100%')

        // ═══ NLC 语音指令 ═══
        this.SectionTitle('🎤 自然语言控制 (NLC)')
        Text('输入自然语言指令，Kimi AI 解析后自动执行')
          .fontSize(11)
          .fontColor(Colors.TEXT_MUTED)
          .margin({ bottom: 8 })

        Row({ space: 8 }) {
          TextInput({
            placeholder: '例: 把靠背升起来',
            text: this.nlcInput
          })
            .onChange((v: string) => { this.nlcInput = v; })
            .onSubmit(() => { this.sendNLC(); })
            .layoutWeight(1)
            .height(42)
            .backgroundColor(Colors.BG_SURFACE)
            .fontColor(Colors.TEXT_PRIMARY)
            .placeholderColor(Colors.TEXT_MUTED)
            .borderRadius(21)
            .padding({ left: 16, right: 16 })

          Button('执行')
            .type(ButtonType.Normal)
            .fontSize(14)
            .height(42)
            .width(65)
            .backgroundColor(Colors.TEAL_600)
            .borderRadius(21)
            .onClick(() => { this.sendNLC(); })
            .enabled(!this.isExecuting)
        }
        .width('100%')

        // NLC结果
        if (this.nlcResult) {
          Text(this.nlcResult)
            .fontSize(13)
            .fontColor(Colors.TEXT_PRIMARY)
            .padding(12)
            .backgroundColor(Colors.BG_CARD)
            .borderRadius(10)
            .width('100%')
            .margin({ top: 8 })
        }

        // ═══ 执行状态 ═══
        if (this.lastAction) {
          Column() {
            Text('最近操作')
              .fontSize(11)
              .fontColor(Colors.TEXT_MUTED)
            Text(this.lastAction)
              .fontSize(13)
              .fontColor(Colors.TEXT_PRIMARY)
              .margin({ top: 4 })
          }
          .width('100%')
          .padding(14)
          .backgroundColor(Colors.BG_CARD)
          .borderRadius(12)
          .margin({ top: 16 })
          .alignItems(HorizontalAlign.Start)
        }

        Blank().height(30)
      }
      .padding(16)
    }
    .width('100%')
    .height('100%')
    .backgroundColor(Colors.BG_DARK)
    .scrollBar(BarState.Off)
  }

  @Builder
  SectionTitle(title: string) {
    Text(title)
      .fontSize(15)
      .fontWeight(600)
      .fontColor(Colors.TEXT_SECONDARY)
      .margin({ top: 20, bottom: 10 })
      .width('100%')
  }

  @Builder
  ControlButton(label: string, bgColor: string, onClick: () => void) {
    Button(label)
      .type(ButtonType.Normal)
      .fontSize(14)
      .fontWeight(500)
      .height(44)
      .backgroundColor(bgColor)
      .fontColor(Colors.TEXT_PRIMARY)
      .borderRadius(12)
      .layoutWeight(1)
      .onClick(onClick)
      .enabled(!this.isExecuting)
  }
}
