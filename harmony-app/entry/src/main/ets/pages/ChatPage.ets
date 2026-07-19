/**
 * ChatPage - AI护理咨询 (临床风格)
 */
import { apiPost, ConsultResponse, RequestBody } from '../common/ApiService';
import { API, Colors } from '../common/Constants';
import { ChatMessage } from '../common/Types';

@Component
export struct ChatPage {
  @State messages: ChatMessage[] = [];
  @State inputText: string = '';
  @State isWaiting: boolean = false;
  @State patientId: number = 1;
  @State agentName: string = 'AI 护理助手';

  private scrollerCtrl: Scroller = new Scroller();

  private addMessage(role: string, content: string): void {
    const msg = new ChatMessage();
    msg.role = role;
    msg.content = content;
    msg.timestamp = Date.now();
    const newList: ChatMessage[] = [];
    for (let i = 0; i < this.messages.length; i++) {
      newList.push(this.messages[i]);
    }
    newList.push(msg);
    this.messages = newList;
  }

  private async sendMessage(): Promise<void> {
    const text = this.inputText.trim();
    if (text.length === 0 || this.isWaiting) return;

    this.addMessage('user', text);
    this.inputText = '';
    this.isWaiting = true;

    setTimeout(() => { this.scrollerCtrl.scrollEdge(Edge.Bottom); }, 100);

    try {
      const bodyObj = new RequestBody();
      bodyObj.patient_id = this.patientId;
      bodyObj.question = text;
      const bodyStr = JSON.stringify(bodyObj);

      const raw = await apiPost(API.AGENTS_CONSULT, bodyStr);
      const result: ConsultResponse = JSON.parse(raw) as ConsultResponse;

      this.addMessage('assistant', result.response);
      if (result.agent.length > 0) this.agentName = result.agent;
    } catch (e) {
      this.addMessage('assistant', `请求失败: ${(e as Error).message}`);
    }

    this.isWaiting = false;
    setTimeout(() => { this.scrollerCtrl.scrollEdge(Edge.Bottom); }, 100);
  }

  build() {
    Column() {
      // ═══ 顶栏 ═══
      Row() {
        Column()
          .width(3)
          .height(16)
          .backgroundColor('#007AFF')
          .borderRadius(2)
        Column() {
          Text('护理咨询')
            .fontSize(15)
            .fontWeight(600)
            .fontColor('#E5E5EA')
          Text(`${this.agentName} · Kimi-K2.5`)
            .fontSize(10)
            .fontColor('#636366')
            .margin({ top: 2 })
        }
        .alignItems(HorizontalAlign.Start)
        .margin({ left: 8 })
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 14, bottom: 12 })
      .backgroundColor('#0C0C0E')
      .alignItems(VerticalAlign.Center)

      // ═══ 消息列表 ═══
      List({ scroller: this.scrollerCtrl, space: 10 }) {
        if (this.messages.length === 0) {
          ListItem() {
            Column() {
              Text('护理咨询')
                .fontSize(18)
                .fontWeight(600)
                .fontColor('#E5E5EA')
                .margin({ top: 50 })
              Text('可以询问体征分析、护理建议、用药提醒等问题')
                .fontSize(12)
                .fontColor('#636366')
                .margin({ top: 8 })
                .textAlign(TextAlign.Center)

              Column({ space: 6 }) {
                ForEach([
                  '患者血压趋势如何？',
                  '目前受压风险等级？',
                  '给出护理建议',
                ], (q: string) => {
                  Text(q)
                    .fontSize(12)
                    .fontColor('#007AFF')
                    .padding({ left: 14, right: 14, top: 8, bottom: 8 })
                    .backgroundColor('#0A1A2E')
                    .borderRadius(8)
                    .borderWidth(0.5)
                    .borderColor('#007AFF30')
                    .onClick(() => {
                      this.inputText = q;
                      this.sendMessage();
                    })
                })
              }
              .margin({ top: 24 })
            }
            .width('100%')
            .alignItems(HorizontalAlign.Center)
          }
        }

        ForEach(this.messages, (msg: ChatMessage) => {
          ListItem() {
            if (msg.role === 'user') {
              Row() {
                Blank()
                Text(msg.content)
                  .fontSize(14)
                  .fontColor('#FFFFFF')
                  .padding(12)
                  .backgroundColor('#007AFF')
                  .borderRadius({
                    topLeft: 14, topRight: 14,
                    bottomLeft: 14, bottomRight: 4
                  })
                  .constraintSize({ maxWidth: '78%' })
              }
              .width('100%')
            } else {
              Row() {
                Column()
                  .width(3)
                  .height(16)
                  .backgroundColor('#34C759')
                  .borderRadius(2)
                  .margin({ right: 8, top: 4 })
                Text(msg.content)
                  .fontSize(14)
                  .fontColor('#E5E5EA')
                  .padding(12)
                  .backgroundColor('#1C1C1E')
                  .borderRadius({
                    topLeft: 4, topRight: 14,
                    bottomLeft: 14, bottomRight: 14
                  })
                  .constraintSize({ maxWidth: '78%' })
                Blank()
              }
              .width('100%')
              .alignItems(VerticalAlign.Top)
            }
          }
        })

        if (this.isWaiting) {
          ListItem() {
            Row() {
              Text('分析中...')
                .fontSize(13)
                .fontColor('#636366')
                .fontStyle(FontStyle.Italic)
            }
          }
        }
      }
      .layoutWeight(1)
      .padding({ left: 14, right: 14 })

      // ═══ 输入框 ═══
      Row({ space: 8 }) {
        TextInput({ placeholder: '输入咨询问题…', text: this.inputText })
          .onChange((value: string) => { this.inputText = value; })
          .onSubmit(() => { this.sendMessage(); })
          .layoutWeight(1)
          .height(42)
          .backgroundColor('#1C1C1E')
          .fontColor('#E5E5EA')
          .placeholderColor('#48484A')
          .borderRadius(10)
          .padding({ left: 14, right: 14 })
          .borderWidth(0.5)
          .borderColor('#2C2C2E')

        Button('发送')
          .type(ButtonType.Normal)
          .fontSize(14)
          .fontWeight(600)
          .height(42)
          .width(65)
          .backgroundColor(this.inputText.trim().length > 0 ? '#007AFF' : '#1C1C1E')
          .fontColor(this.inputText.trim().length > 0 ? '#FFF' : '#48484A')
          .borderRadius(10)
          .onClick(() => { this.sendMessage(); })
          .enabled(!this.isWaiting)
      }
      .width('100%')
      .padding({ left: 14, right: 14, top: 8, bottom: 14 })
      .backgroundColor('#0C0C0E')
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#000000')
  }
}
