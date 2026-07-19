/**
 * Index.ets - 主入口 (临床监护风格)
 *
 * 底部导航: 监护 | 智能体 | 告警 | 咨询 | 控制
 * 去掉emoji，纯文字+状态指示
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

  @State loginUser: string = 'admin';
  @State loginPass: string = 'admin123';
  @State loginError: string = '';
  @State isLoggingIn: boolean = false;

  aboutToAppear(): void {
    this.isAuthenticated = isLoggedIn();
  }

  private async doLogin(): Promise<void> {
    if (this.loginUser.trim().length === 0 || this.loginPass.trim().length === 0) {
      this.loginError = '请输入用户名和密码';
      return;
    }
    this.isLoggingIn = true;
    this.loginError = '';
    try {
      await login(this.loginUser, this.loginPass);
      this.isAuthenticated = true;
    } catch (e) {
      this.loginError = (e as Error).message;
    }
    this.isLoggingIn = false;
  }

  // ═══ 登录界面 (医疗系统风格) ═══
  @Builder
  LoginView() {
    Column() {
      Blank().height('18%')

      // Logo区
      Column() {
        Text('+')
          .fontSize(48)
          .fontWeight(200)
          .fontColor('#34C759')
        Text('智能护理病床监护系统')
          .fontSize(20)
          .fontWeight(600)
          .fontColor('#E5E5EA')
          .margin({ top: 16 })
        Text('Smart Nursing Bed Monitoring System')
          .fontSize(11)
          .fontColor('#636366')
          .margin({ top: 6 })
          .letterSpacing(0.5)
      }
      .alignItems(HorizontalAlign.Center)

      // 登录表单
      Column({ space: 12 }) {
        Text('医护人员登录')
          .fontSize(13)
          .fontColor('#8E8E93')
          .width('100%')
          .margin({ bottom: 4 })

        TextInput({ placeholder: '工号 / 用户名', text: this.loginUser })
          .onChange((v: string) => { this.loginUser = v; })
          .height(48)
          .backgroundColor('#1C1C1E')
          .fontColor('#E5E5EA')
          .placeholderColor('#48484A')
          .borderRadius(10)
          .padding({ left: 16, right: 16 })
          .borderWidth(0.5)
          .borderColor('#2C2C2E')

        TextInput({ placeholder: '密码', text: this.loginPass })
          .onChange((v: string) => { this.loginPass = v; })
          .type(InputType.Password)
          .height(48)
          .backgroundColor('#1C1C1E')
          .fontColor('#E5E5EA')
          .placeholderColor('#48484A')
          .borderRadius(10)
          .padding({ left: 16, right: 16 })
          .borderWidth(0.5)
          .borderColor('#2C2C2E')

        if (this.loginError.length > 0) {
          Text(this.loginError)
            .fontSize(12)
            .fontColor('#FF3B5C')
        }

        Button(this.isLoggingIn ? '验证中...' : '登 录')
          .type(ButtonType.Normal)
          .width('100%')
          .height(48)
          .fontSize(16)
          .fontWeight(600)
          .backgroundColor('#007AFF')
          .borderRadius(10)
          .onClick(() => { this.doLogin(); })
          .enabled(!this.isLoggingIn)
      }
      .width('82%')
      .margin({ top: 48 })

      Blank()

      // 底部
      Column() {
        Text('IoT智能护理 · HarmonyOS NEXT')
          .fontSize(10)
          .fontColor('#3A3A3C')
        Text('v4.0')
          .fontSize(10)
          .fontColor('#2C2C2E')
          .margin({ top: 2 })
      }
      .margin({ bottom: 30 })
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#000000')
    .alignItems(HorizontalAlign.Center)
  }

  // ═══ 主界面 ═══
  @Builder
  MainView() {
    Tabs({ barPosition: BarPosition.End, index: this.currentTab }) {
      TabContent() {
        DashboardPage()
      }
      .tabBar(this.TabBarItem(0, '监护'))

      TabContent() {
        AgentSwarmPage()
      }
      .tabBar(this.TabBarItem(1, '智能体'))

      TabContent() {
        AlertsPage()
      }
      .tabBar(this.TabBarItem(2, '告警'))

      TabContent() {
        ChatPage()
      }
      .tabBar(this.TabBarItem(3, '咨询'))

      TabContent() {
        ControlPage()
      }
      .tabBar(this.TabBarItem(4, '控制'))
    }
    .onChange((index: number) => {
      this.currentTab = index;
    })
    .barBackgroundColor('#0C0C0E')
    .barHeight(50)
  }

  @Builder
  TabBarItem(index: number, label: string) {
    Column() {
      // 选中指示条
      Column()
        .width(this.currentTab === index ? 20 : 0)
        .height(2)
        .backgroundColor('#007AFF')
        .borderRadius(1)
        .margin({ bottom: 4 })

      Text(label)
        .fontSize(12)
        .fontColor(this.currentTab === index ? '#007AFF' : '#636366')
        .fontWeight(this.currentTab === index ? 600 : 400)
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
