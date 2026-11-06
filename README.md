<div align="center">

<img src="assets/icon.ico" width="96" alt="icon">

# 小米预装应用卸载助手

**MiPreinstallUninstaller**

不用装 Android Studio、不用配 adb 环境变量，双击就能卸载小米手机上那些看不见的预装应用。

[![Platform](https://img.shields.io/badge/平台-Windows%2010%20%2F%2011-0078D4?style=flat-square&logo=windows)](https://github.com/chokoketsu)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![PyInstaller](https://img.shields.io/badge/PyInstaller-onefile-2E8B57?style=flat-square)](https://pyinstaller.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![Release](https://img.shields.io/badge/Release-v1.1.0-blue?style=flat-square)](../../releases)

</div>

---

![界面截图](assets/screenshot.png)

## 这是什么

起因很简单：一台小米手机的 `/system/priv-app/` 里躺着一个叫 **SystemHelper**（`com.mobiletools.systemhelper`）的特权应用——没有桌面图标、不在应用列表里出现、开机自启、定期唤醒，把设备信息以**明文 HTTP** 上报给运营商管理平台。

手动清理要敲一串 adb 命令，还容易误删系统组件把手机变成砖。于是就有了这个工具：把整套流程做成了图形界面，**adb 直接打包进 exe**，拷到任何一台 Windows 上双击就能用。

## 功能

| | 功能 | 说明 |
|---|---|---|
| 🔍 | **自动发现设备** | 启动即扫描，显示「机型 ｜ 序列号 ｜ USB/无线」，不用敲 `adb devices` |
| 📶 | **无线调试** | 一键扫描局域网内已开无线调试的手机，也支持手动填 `IP:端口` |
| 🩺 | **状态检测** | 目标应用是否安装、版本号、安装路径、是否为特权应用，一目了然 |
| 💾 | **卸载前自动备份** | 把 APK 拉到桌面 `MI卸载备份_时间戳`，并附一份安装态快照 |
| 🧹 | **一键卸载** | `pm uninstall --user 0`，只移除当前用户的安装，**可逆** |
| ↩️ | **一键恢复** | `pm install-existing`，从系统分区原地装回来 |
| 🛡️ | **防误删保护** | 内置核心组件黑名单（系统 UI、桌面、电话、设置…），点不动也输不进去 |
| 🎭 | **演示模式** | `--demo` 启动，用模拟设备数据预览界面，不碰真机 |

## 快速开始

**方式一：直接下载现成的 exe**（推荐）

到 [Releases](../../releases) 下载 `MiUninstaller.exe`，双击运行，无需安装。

> Windows 11 可能提示「已保护你的电脑」——因为没有购买代码签名证书，点「更多信息」→「仍要运行」即可。

**方式二：从源码运行 / 自行打包**

```bash
git clone https://github.com/chokoketsu/MiPreinstallUninstaller.git
cd MiPreinstallUninstaller

# 直接运行
python src/mi_uninstaller.py

# 或打包成单文件 exe
pip install pyinstaller
python build.py
```

打包产物在 `dist/MiUninstaller.exe`。

## 使用步骤

1. **连接手机**：数据线连电脑；或手机开启「开发者选项 → 无线调试」并与电脑同 WiFi
2. 手机弹出「允许 USB 调试吗」→ 勾选「一律允许」→ 允许
3. 启动工具，「已连接设备」下拉框里出现机型 → 说明连上了
4. 包名框输入目标包名（默认已填 `com.mobiletools.systemhelper`），点「检测状态」
5. 确认「已安装」→ 点「一键卸载」→ 二次确认
6. 看到「卸载成功，校验通过」即完成

反悔了随时点「恢复」按钮。

## 内置包名预设

下拉框里预置了 14 个小米机型上常见、相对安全可移除的包：

| 包名 | 说明 |
|---|---|
| `com.mobiletools.systemhelper` | 联通设备注册组件（隐藏无图标） |
| `com.miui.systemAdSolution` | 系统广告服务 |
| `com.miui.analytics` | 小米分析统计 |
| `com.miui.msa.global` | MSA 广告标识服务 |
| `com.xiaomi.mipicks` | 应用中心推荐 |
| `com.miui.hybrid` | 快应用框架 |
| `com.miui.video` / `com.miui.news` / `com.miui.browser` | 小米视频 / 资讯 / 浏览器 |
| `com.xiaomi.gamecenter` / `com.xiaomi.gsgservice` | 游戏中心 / 游戏服务框架 |
| `com.miui.miservice` | 服务与反馈 |
| `com.iflytek.inputmethod.miui` | 讯飞输入法（小米定制） |
| `com.xiaomi.market` | 小米应用商店 |

也可以手输任意包名。查包名：

```bash
adb shell pm list packages | findstr 关键词
```

## 为什么卸载是可逆的

工具用的是：

```bash
adb shell pm uninstall --user 0 <包名>
```

它不是删除 `/system` 分区里的文件，只是把「这个包对 user 0 安装」这个状态标记为 `installed=false`。系统分区中的 APK 本体原封不动，所以随时可以：

```bash
adb shell pm install-existing <包名>
```

真正的删除需要 Root 或解锁 bootloader 改写系统分区，本工具**不做**这件事。

想验证当前状态：

```bash
adb shell pm path <包名>              # 有输出=已安装，空=未安装
adb shell pm list packages -u | findstr 关键词   # -u 可看到已卸载的残留定义
adb shell dumpsys package <包名> | findstr installed
```

## 技术实现

- **Python 3.9+ / tkinter** 写界面，无第三方 GUI 依赖
- **PyInstaller `--onefile --windowed`** 打包，内置 `adb.exe` + `AdbWinApi.dll` + `AdbWinUsbApi.dll`
- 运行时把 adb 释放到 `_MEIPASS/adb/`，查找优先级：内置 → 程序同级 `adb/` → 系统 Android SDK → `PATH`
- 所有 adb 调用带 `CREATE_NO_WINDOW`，不会闪黑框
- 耗时操作跑在子线程，UI 不阻塞；关键操作前后都做状态校验
- 关键系统包黑名单在 `PROTECTED_PKGS`，直接拒绝执行

## 常见问题

<details>
<summary><b>提示「未检测到设备」</b></summary>

- 数据线连接：确认手机已弹「允许 USB 调试」并点允许；部分机型需在开发者选项里额外打开「USB 调试（安全设置）」
- 无线调试：手机和电脑必须在同一 WiFi，且手机「无线调试」处于开启状态
- 驱动问题：Windows 需要小米 USB 驱动，或装过小米手机助手
</details>

<details>
<summary><b>卸载报 <code>-25</code> / <code>DELETE_FAILED_INTERNAL_ERROR</code></b></summary>

个别厂商强锁的应用不允许当前用户移除，这类只有 Root 后改写系统分区才能处理，本工具做不到。
</details>

<details>
<summary><b>卸载后系统升级又回来了</b></summary>

OTA 大版本升级会重新写入预装应用，重跑一次卸载即可。
</details>

<details>
<summary><b>备份出来的 APK 为什么装不上</b></summary>

系统应用用的是平台签名，直接 `adb install` 会报签名冲突。恢复请用工具里的「恢复」按钮（即 `pm install-existing`）。
</details>

## 免责声明

- 本项目仅供**自己拥有的设备**做本地调试与清理使用。
- 卸载任何应用前请确认它不影响你的日常功能。**不要卸载不认识的系统组件**，可能导致无法开机。
- 因误操作导致的设备异常、数据丢失，作者不承担责任。
- 内置 adb 来自 Android SDK Platform-Tools，遵循其原始许可（Apache License 2.0）。

## License

[MIT](LICENSE)
