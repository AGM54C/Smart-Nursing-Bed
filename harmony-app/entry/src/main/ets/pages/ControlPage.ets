/**
 * ControlPage - 设备控制面板 (临床风格)
 */
import { piRequest, SimpleResponse, NlcResponse, RequestBody } from '../common/ApiService';
import { API, Colors } from '../common/Constants';

@Component
export struct ControlPage {
  @State nlcInput: string = '';
  @State nlcResult: string = '';
  @State isExecuting: boolean = false;
  @State lastAction: string = '';
  @State piConnected: boolean = true;

  private async sendCommand(action: string, room: string): Promise<void> {
    this.isExecuting = true;
    this.lastAction = action;
    try {
      const bodyObj = new RequestBody();
      bodyObj.action = action;
      if (room.length > 0) {
        bodyObj.room = room;
      }
      const bodyStr = JSON.stringify(bodyObj);
      const raw = await piRequest(API.PI_REMOTE, bodyStr);
      const result: SimpleResponse = JSON.parse(raw) as SimpleResponse;
      const msg = result.message.length > 0 ? result.message : '已执行';
      this.lastAction = `${action}: ${msg}`;
      this.piConnected = true;
    } catch (e) {
      this.lastAction = `${action}: ${(e as Error).message}`;
      this.piConnected = false;
    }
    this.isExecuting = false;
  }

  private async sendNLC(): Promise<void> {
    const text = this.nlcInput.trim();
    if (text.length === 0) return;
    this.isExecuting = true;
    this.nlcResult = '解析中...';
    try {
      const nlcBody = new RequestBody();
      nlcBody.text = text;
      const bodyStr = JSON.stringify(nlcBody);
      const raw = await piRequest(API.PI_NLC, bodyStr);
      const result: NlcResponse = JSON.parse(raw) as NlcResponse;
      const msg = result.response.length > 0 ? result.response : result.action;
      this.nlcResult = msg;
      this.nlcInput = '';
    } catch (e) {
      this.nlcResult = `错误: ${(e as Error).message}`;
    }
    this.isExecuting = false;
  }

  build() {
    Scroll() {
      Column() {
        // ═══ 顶栏 ═══
        Row() {
          Column()
            .width(3)
            .height(16)
            .backgroundColor(this.piConnected ? '#34C759' : '#FF3B5C')
            .borderRadius(2)
          Text('设备控制')
            .fontSize(16)
            .fontWeight(600)
            .fontColor('#E5E5EA')
            .margin({ left: 8 })

          Blank()

          Row() {
            Circle()
              .width(6)
              .height(6)
              .fill(this.piConnected ? '#34C759' : '#FF3B5C')
            Text(this.piConnected ? '设备在线' : '连接断开')
              .fontSize(11)
              .fontColor(this.piConnected ? '#34C759' : '#FF3B5C')
              .margin({ left: 4 })
          }
        }
        .width('100%')
        .alignItems(VerticalAlign.Center)

        // ═══ 病床控制 ═══
        this.SectionTitle('病床升降')
        Row({ space: 10 }) {
          this.ControlButton('抬升靠背', '#007AFF', () => this.sendCommand('raise_bed', ''))
          this.ControlButton('降低靠背', '#1C1C1E', () => this.sendCommand('lower_bed', ''))
        }
        .width('100%')

        // ═══ 导航 ═══
        this.SectionTitle('自主导航')
        Row({ space: 8 }) {
          this.ControlButton('301房', '#0A3A6B', () => this.sendCommand('navigate', '301'))
          this.ControlButton('302房', '#0A3A6B', () => this.sendCommand('navigate', '302'))
          this.ControlButton('303房', '#0A3A6B', () => this.sendCommand('navigate', '303'))
        }
        .width('100%')

        Row({ space: 10 }) {
          this.ControlButton('急停', '#4A1020', () => this.sendCommand('stop_nav', ''))
          this.ControlButton('返回基站', '#1C1C1E', () => this.sendCommand('return_home', ''))
        }
        .width('100%')
        .margin({ top: 8 })

        // ═══ 气囊 ═══
        this.SectionTitle('气囊控制')
        Row({ space: 8 }) {
          this.ControlButton('充气', '#007AFF', () => this.sendCommand('air_inflate', ''))
          this.ControlButton('放气', '#1C1C1E', () => this.sendCommand('air_deflate', ''))
          this.ControlButton('减压循环', '#0A3A6B', () => this.sendCommand('air_relief_cycle', ''))
        }
        .width('100%')

        // ═══ 语音指令 ═══
        this.SectionTitle('自然语言控制')
        Text('输入自然语言指令，AI解析后自动执行')
          .fontSize(11)
          .fontColor('#48484A')
          .margin({ bottom: 8 })

        Row({ space: 8 }) {
          TextInput({
            placeholder: '例: 帮我抬高靠背',
            text: this.nlcInput
          })
            .onChange((v: string) => { this.nlcInput = v; })
            .onSubmit(() => { this.sendNLC(); })
            .layoutWeight(1)
            .height(42)
            .backgroundColor('#1C1C1E')
            .fontColor('#E5E5EA')
            .placeholderColor('#48484A')
            .borderRadius(10)
            .padding({ left: 14, right: 14 })
            .borderWidth(0.5)
            .borderColor('#2C2C2E')

          Button('执行')
            .type(ButtonType.Normal)
            .fontSize(14)
            .height(42)
            .width(60)
            .backgroundColor('#007AFF')
            .borderRadius(10)
            .onClick(() => { this.sendNLC(); })
            .enabled(!this.isExecuting)
        }
        .width('100%')

        if (this.nlcResult.length > 0) {
          Text(this.nlcResult)
            .fontSize(13)
            .fontColor('#AEAEB2')
            .padding(12)
            .backgroundColor('#0D0D11')
            .borderRadius(8)
            .width('100%')
            .margin({ top: 8 })
            .borderWidth(0.5)
            .borderColor('#1C1C1E')
        }

        // ═══ 操作日志 ═══
        if (this.lastAction.length > 0) {
          Column() {
            Text('最近操作')
              .fontSize(11)
              .fontColor('#48484A')
            Text(this.lastAction)
              .fontSize(13)
              .fontColor('#AEAEB2')
              .margin({ top: 4 })
          }
          .width('100%')
          .padding(12)
          .backgroundColor('#0D0D11')
          .borderRadius(10)
          .margin({ top: 14 })
          .alignItems(HorizontalAlign.Start)
          .borderWidth(0.5)
          .borderColor('#1C1C1E')
        }

        Blank().height(30)
      }
      .padding(14)
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#000000')
    .scrollBar(BarState.Off)
  }

  @Builder
  SectionTitle(title: string) {
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
    .margin({ top: 20, bottom: 10 })
    .alignItems(VerticalAlign.Center)
  }

  @Builder
  ControlButton(label: string, bgColor: string, onClick: () => void) {
    Button(label)
      .type(ButtonType.Normal)
      .fontSize(13)
      .fontWeight(500)
      .height(44)
      .backgroundColor(bgColor)
      .fontColor('#E5E5EA')
      .borderRadius(10)
      .layoutWeight(1)
      .onClick(onClick)
      .enabled(!this.isExecuting)
      .borderWidth(0.5)
      .borderColor('#2C2C2E')
  }
}
