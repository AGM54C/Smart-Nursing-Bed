/**
 * ChatPage - AI 护理咨询聊天
 *
 * 多轮对话，对接 /api/agents/consult 接口
 */
import { apiPost } from '../common/ApiService';
import { API, Colors } from '../common/Constants';
import { ChatMessage } from '../common/Types';

@Component
export struct ChatPage {
  @State messages: ChatMessage[] = [];
  @State inputText: string = '';
  @State isWaiting: boolean = false;
  @State patientId: number = 1;
  @State agentName: string = 'AI 护理助手';
  @State agentIcon: string = '🤖';

  private scrollerCtrl: Scroller = new Scroller();

  private async sendMessage(): Promise<void> {
    const text = this.inputText.trim();
    if (!text || this.isWaiting) return;

    // 添加用户消息
    const userMsg: ChatMessage = { role: 'user', content: text, timestamp: Date.now() };
    this.messages = [...this.messages, userMsg];
    this.inputText = '';
    this.isWaiting = true;

    // 滚动到底部
    setTimeout(() => {
      this.scrollerCtrl.scrollEdge(Edge.Bottom);
    }, 100);

    try {
      // 调用AI咨询接口
      const result = await apiPost<{
        agent: string;
        agent_icon: string;
        response: string;
        patient_name: string;
      }>(API.AGENTS_CONSULT, {
        patient_id: this.patientId,
        question: text,
      });

      const aiMsg: ChatMessage = {
        role: 'assistant',
        content: result.response,
        timestamp: Date.now(),
      };
      this.messages = [...this.messages, aiMsg];
      this.agentName = result.agent || this.agentName;
      this.agentIcon = result.agent_icon || this.agentIcon;
    } catch (e) {
      const errMsg: ChatMessage = {
        role: 'assistant',
        content: `⚠️ 请求失败: ${(e as Error).message}`,
        timestamp: Date.now(),
      };
      this.messages = [...this.messages, errMsg];
    }

    this.isWaiting = false;
    setTimeout(() => {
      this.scrollerCtrl.scrollEdge(Edge.Bottom);
    }, 100);
  }

  build() {
    Column() {
      // ═══ 标题栏 ═══
      Row() {
        Text(`${this.agentIcon} ${this.agentName}`)
          .fontSize(18)
          .fontWeight(700)
          .fontColor(Colors.TEXT_PRIMARY)
        Text('Kimi-K2.5')
          .fontSize(11)
          .fontColor(Colors.TEAL_500)
          .padding({ left: 8, right: 8, top: 2, bottom: 2 })
          .backgroundColor(Colors.TEAL_500 + '20')
          .borderRadius(10)
      }
      .width('100%')
      .justifyContent(FlexAlign.SpaceBetween)
      .padding(16)

      // ═══ 消息列表 ═══
      List({ scroller: this.scrollerCtrl, space: 12 }) {
        // 欢迎消息
        if (this.messages.length === 0) {
          ListItem() {
            Column() {
              Text('🏥')
                .fontSize(40)
              Text('您好！我是您的AI护理助手')
                .fontSize(15)
                .fontWeight(500)
                .fontColor(Colors.TEXT_PRIMARY)
                .margin({ top: 12 })
              Text('您可以询问关于患者体征、护理建议、用药提醒等问题')
                .fontSize(12)
                .fontColor(Colors.TEXT_MUTED)
                .margin({ top: 6 })
                .textAlign(TextAlign.Center)

              // 快捷问题
              Column({ space: 8 }) {
                ForEach([
                  '患者最近血压趋势如何？',
                  '目前受压风险等级是多少？',
                  '有什么护理建议？',
                ], (q: string) => {
                  Text(q)
                    .fontSize(12)
                    .fontColor(Colors.TEAL_500)
                    .padding({ left: 14, right: 14, top: 8, bottom: 8 })
                    .backgroundColor(Colors.TEAL_500 + '15')
                    .borderRadius(16)
                    .onClick(() => {
                      this.inputText = q;
                      this.sendMessage();
                    })
                })
              }
              .margin({ top: 16 })
            }
            .width('100%')
            .alignItems(HorizontalAlign.Center)
            .padding({ top: 40, bottom: 20 })
          }
        }

        // 消息气泡
        ForEach(this.messages, (msg: ChatMessage, index: number) => {
          ListItem() {
            if (msg.role === 'user') {
              // 用户消息 - 右对齐
              Row() {
                Blank()
                Text(msg.content)
                  .fontSize(14)
                  .fontColor('#FFF')
                  .padding(12)
                  .backgroundColor(Colors.TEAL_600)
                  .borderRadius({
                    topLeft: 16, topRight: 16,
                    bottomLeft: 16, bottomRight: 4
                  })
                  .constraintSize({ maxWidth: '75%' })
              }
              .width('100%')
            } else {
              // AI消息 - 左对齐
              Row() {
                Text(this.agentIcon)
                  .fontSize(20)
                  .margin({ right: 8, top: 4 })

                Text(msg.content)
                  .fontSize(14)
                  .fontColor(Colors.TEXT_PRIMARY)
                  .padding(12)
                  .backgroundColor(Colors.BG_CARD)
                  .borderRadius({
                    topLeft: 4, topRight: 16,
                    bottomLeft: 16, bottomRight: 16
                  })
                  .constraintSize({ maxWidth: '75%' })

                Blank()
              }
              .width('100%')
              .alignItems(VerticalAlign.Top)
            }
          }
        })

        // 等待指示器
        if (this.isWaiting) {
          ListItem() {
            Row() {
              Text(this.agentIcon)
                .fontSize(20)
                .margin({ right: 8 })
              Text('思考中...')
                .fontSize(13)
                .fontColor(Colors.TEXT_MUTED)
                .fontStyle(FontStyle.Italic)
            }
          }
        }
      }
      .layoutWeight(1)
      .padding({ left: 16, right: 16 })

      // ═══ 输入框 ═══
      Row({ space: 8 }) {
        TextInput({ placeholder: '请输入您的问题…', text: this.inputText })
          .onChange((value: string) => { this.inputText = value; })
          .onSubmit(() => { this.sendMessage(); })
          .layoutWeight(1)
          .height(42)
          .backgroundColor(Colors.BG_SURFACE)
          .fontColor(Colors.TEXT_PRIMARY)
          .placeholderColor(Colors.TEXT_MUTED)
          .borderRadius(21)
          .padding({ left: 16, right: 16 })

        Button('发送')
          .type(ButtonType.Normal)
          .fontSize(14)
          .fontWeight(600)
          .height(42)
          .width(70)
          .backgroundColor(this.inputText.trim() ? Colors.TEAL_600 : Colors.BG_SURFACE)
          .fontColor(this.inputText.trim() ? '#FFF' : Colors.TEXT_MUTED)
          .borderRadius(21)
          .onClick(() => { this.sendMessage(); })
          .enabled(!this.isWaiting)
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 8, bottom: 16 })
      .backgroundColor(Colors.BG_DARK)
    }
    .width('100%')
    .height('100%')
    .backgroundColor(Colors.BG_DARK)
  }
}
