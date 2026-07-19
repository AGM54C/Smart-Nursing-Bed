/**
 * Index.ets - 鸿蒙APP主入口
 *
 * 5个Tab页面:
 *   1. 🫀 监护面板 (DashboardPage)
 *   2. 🤖 Agent Swarm (AgentSwarmPage)
 *   3. 🚨 告警中心 (AlertsPage)
 *   4. 💬 AI聊天 (ChatPage)
 *   5. 🎮 远程控制 (ControlPage)
 *
 * 启动时检查登录状态，未登录则显示登录界面
 */
import { login, isLoggedIn } from '../common/ApiService';
import { Colors } from '../common/Constants';
import { DashboardPage } from './DashboardPage';
import { AgentSwarmPage } from './AgentSwarmPage';
import { AlertsPage } from './AlertsPage';
import { ChatPage } from './ChatPage';
import { ControlPage } from './ControlPage';

@Entry
@Component
struct Index {
  @State isAuthenticated: boolean = false;
  @State currentTab: number = 0;

  // 登录表单
  @State loginUser: string = 'admin';
  @State loginPass: string = 'admin123';
  @State loginError: string = '';
  @State isLoggingIn: boolean = false;

  aboutToAppear(): void {
    this.isAuthenticated = isLoggedIn();
  }

  private async doLogin(): Promise<void> {
    if (!this.loginUser.trim() || !this.loginPass.trim()) {
      this.loginError = '请输入用户名和密码';
      return;
    }
    this.isLoggingIn = true;
    this.loginError = '';
    try {
      await login(this.loginUser, this.loginPass);
      this.isAuthenticated = true;
    } catch (e) {
      this.loginError = (e as Error).message || '登录失败';
    }
    this.isLoggingIn = false;
  }

  // ═══ 登录界面 ═══
  @Builder
  LoginView() {
    Column() {
      Blank().height('15%')

      // Logo
      Text('🛏️')
        .fontSize(56)
      Text('智能护理病床')
        .fontSize(24)
        .fontWeight(700)
        .fontColor(Colors.TEXT_PRIMARY)
        .margin({ top: 12 })
      Text('Multi-Agent Nursing Swarm v4.0')
        .fontSize(12)
        .fontColor(Colors.TEAL_500)
        .margin({ top: 6 })

      // 登录表单
      Column({ space: 12 }) {
        TextInput({ placeholder: '用户名', text: this.loginUser })
          .onChange((v: string) => { this.loginUser = v; })
          .height(46)
          .backgroundColor(Colors.BG_SURFACE)
          .fontColor(Colors.TEXT_PRIMARY)
          .placeholderColor(Colors.TEXT_MUTED)
          .borderRadius(12)
          .padding({ left: 16, right: 16 })

        TextInput({ placeholder: '密码', text: this.loginPass })
          .onChange((v: string) => { this.loginPass = v; })
          .type(InputType.Password)
          .height(46)
          .backgroundColor(Colors.BG_SURFACE)
          .fontColor(Colors.TEXT_PRIMARY)
          .placeholderColor(Colors.TEXT_MUTED)
          .borderRadius(12)
          .padding({ left: 16, right: 16 })

        if (this.loginError) {
          Text(this.loginError)
            .fontSize(12)
            .fontColor(Colors.DANGER)
        }

        Button(this.isLoggingIn ? '登录中...' : '登录')
          .type(ButtonType.Normal)
          .width('100%')
          .height(46)
          .fontSize(16)
          .fontWeight(600)
          .backgroundColor(Colors.TEAL_600)
          .borderRadius(12)
          .onClick(() => { this.doLogin(); })
          .enabled(!this.isLoggingIn)
      }
      .width('80%')
      .margin({ top: 40 })

      // 底部信息
      Text('华为云 IoTDA × NearLink × HarmonyOS')
        .fontSize(11)
        .fontColor(Colors.TEXT_MUTED)
        .margin({ top: 40 })
    }
    .width('100%')
    .height('100%')
    .backgroundColor(Colors.BG_DARK)
    .alignItems(HorizontalAlign.Center)
  }

  // ═══ 主界面 (Tabs) ═══
  @Builder
  MainView() {
    Tabs({ barPosition: BarPosition.End, index: this.currentTab }) {
      // Tab 1: 监护面板
      TabContent() {
        DashboardPage()
      }
      .tabBar(this.TabBarItem(0, '监护', '🫀'))

      // Tab 2: Agent Swarm
      TabContent() {
        AgentSwarmPage()
      }
      .tabBar(this.TabBarItem(1, 'Agent', '🤖'))

      // Tab 3: 告警
      TabContent() {
        AlertsPage()
      }
      .tabBar(this.TabBarItem(2, '告警', '🚨'))

      // Tab 4: AI聊天
      TabContent() {
        ChatPage()
      }
      .tabBar(this.TabBarItem(3, '聊天', '💬'))

      // Tab 5: 控制
      TabContent() {
        ControlPage()
      }
      .tabBar(this.TabBarItem(4, '控制', '🎮'))
    }
    .onChange((index: number) => {
      this.currentTab = index;
    })
    .barBackgroundColor(Colors.BG_CARD)
    .barHeight(56)
  }

  @Builder
  TabBarItem(index: number, label: string, icon: string) {
    Column() {
      Text(icon)
        .fontSize(22)
      Text(label)
        .fontSize(10)
        .fontColor(this.currentTab === index ? Colors.TEAL_500 : Colors.TEXT_MUTED)
        .fontWeight(this.currentTab === index ? 600 : 400)
        .margin({ top: 2 })
    }
    .width('100%')
    .height('100%')
    .justifyContent(FlexAlign.Center)
  }

  build() {
    Column() {
      if (this.isAuthenticated) {
        this.MainView()
      } else {
        this.LoginView()
      }
    }
    .width('100%')
    .height('100%')
  }
}
