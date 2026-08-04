# Claude Desktop Profiles for Linux

在 Linux 上并行运行多个 Claude Desktop 账号。每个 profile 拥有独立的登录状态、
聊天记录、设置与 MCP 连接器，可同时开着互不干扰。

一个 shell CLI + 一个 tkinter 管理界面，无第三方依赖、无 Electron 包装、无遥测。

## 工作原理

Claude Desktop 是 Electron 应用，因此支持 Chromium 的 `--user-data-dir`。
每个 profile 就是一个独立的数据目录：

```
~/.config/Claude-Work/       # Cookies、Local Storage、config.json、
~/.config/Claude-Personal/   # claude_desktop_config.json 各自独立
```

Electron 的单实例锁按 `--user-data-dir` 划分，因此：

- 同一 profile 重复启动 → 聚焦已有窗口，不会开出第二个实例
- 不同 profile → 各自独立的进程，可同时运行

`--class` 让每个 profile 拿到独立的 `WM_CLASS`，配合 `.desktop` 里的
`StartupWMClass`，任务栏/程序坞会把各 profile 的窗口分开归组。

## 安装

需要 Claude Desktop、`python3-tk`（仅图形界面需要）：

```bash
sudo apt install python3-tk     # Debian/Ubuntu
git clone https://github.com/BMProjects/claude-desktop-profiles-linux.git
cd claude-desktop-profiles-linux
./install.sh
```

安装脚本把 `cdp` 软链到 `~/.local/bin`，并把「Claude Desktop 多账号」管理界面
装进应用菜单。软链而非拷贝，更新仓库后立即生效。

## 使用

```bash
cdp import Personal            # 复制当前已登录的账号，开箱即登录
cdp add Work --color blue      # 创建空 profile，首次启动时自行登录
cdp list                       # 名称 / 配色 / 运行状态 / 磁盘占用 / 启动器
cdp launch Work                # 启动（已运行则聚焦）
cdp color Work purple          # 换配色与图标
cdp remove Work                # 移除启动器，保留数据
cdp remove Work --purge        # 连数据目录一并删除（会二次确认）
cdp gui                        # 打开图形管理界面
```

配色：`orange` `red` `yellow` `green` `teal` `blue` `purple` `pink`

创建后可直接在应用菜单里搜索「Claude — Work」启动，无需终端。

### 导入当前已登录的账号

`cdp import <名称>` 把 Claude Desktop 默认配置（`~/.config/Claude`）里的登录态
复制到新 profile，省去重新登录。典型用法是先把现有环境收编成一个具名 profile，
再新建其他账号：

```bash
cdp import Personal --color green   # 现有账号 → Personal
cdp add Work --color blue           # 另一个账号 → Work，启动后登录
```

复制的是承载登录态的五项：`Cookies`（会话）、`config.json`（OAuth 令牌）、
`Local Storage`、`Local State` 及 `Cookies-journal`。

**刻意不复制 `ant-did`（设备标识）**：复制它会让新 profile 与来源伪装成同一台
设备，同一标识被两个会话并发使用会触发服务端的重新验证。留空则首次启动时自行
生成新的，代价是可能需要过一次设备验证——这才是它本该有的样子。

注意事项：

- **导入前请完全退出 Claude Desktop**。运行中复制 SQLite 会得到写入中途的快照，
  导入的登录态可能损坏；`cdp import` 检测到其运行会直接拒绝。
- **目标 profile 必须是空的**，已有数据时拒绝覆盖。
- 导入后该 profile 与默认配置是**同一个账号**，且各自持有一份凭据副本。
  想换账号就在新 profile 里退出登录再重新登录。

## 图形界面

`cdp gui`，或在应用菜单打开「Claude Desktop 多账号」。每个 profile 一张卡片，
显示配色、运行状态与占用，可一键启动、换色、移除，每 5 秒自动刷新运行状态
（Claude Desktop 在界面外被启停也能反映出来）。

所有操作都委托给 `cdp` CLI，界面本身不含业务逻辑。

## 在 profile 里登录时会跳回默认账号（重要）

**现象**：在某个 profile 里点登录，验证走完却跳回默认账号，该 profile 依旧是空的。

**原因**：登录回调走 `claude://` 协议，而系统里该协议的处理器是官方的
`com.anthropic.Claude.desktop`，其 `Exec=claude-desktop %U` **不带
`--user-data-dir`**——回调因此必然由默认配置接管，发起登录的 profile 收不到。
这是单一全局协议与多 profile 的固有冲突：系统无从知道是哪个 profile 发起的。

**规避办法**：登录期间把该协议临时指向目标 profile 的启动器，完成后还原。

```bash
# 1. 登录前：把 claude:// 指向目标 profile（这里是 apple）
xdg-mime default claude-profile-apple.desktop x-scheme-handler/claude

# 2. 启动该 profile 并完成登录
cdp launch apple

# 3. 登录完成后还原
xdg-mime default com.anthropic.Claude.desktop x-scheme-handler/claude
```

profile 启动器的 `Exec` 里已带 `%U`，能正常接收回调 URL。查看当前指向：

```bash
xdg-mime query default x-scheme-handler/claude
```

还原后，日常点击 `claude://` 链接仍由默认配置打开。

## KDE 全局快捷键会堆积

启动 profile 后，系统设置里可能弹出快捷键冲突提示，且「Claude」名下积攒出
一堆无用条目。这是 Claude Desktop 自身的行为，不是 profile 机制的副作用：

- `Ctrl+Alt+Space`（快速输入）是**应用内硬编码的默认值**，不写入 profile 目录，
  因此无法通过预置配置提前关闭（实测预置 `quickEntryShortcut: "off"` 无效）。
- 每个实例启动时都会重新向 KDE 注册一次。该键已被首个实例占用，后来者绑定
  失败，只留下一条「生效键为空」的惰性条目，并触发冲突提示。
- profile 删除后，这些条目不会自动消失。

清理：

```bash
cdp prune-shortcuts     # 删除所有未绑定的失效条目，保留真正生效的那条
```

只删除生效键为空的条目，不影响正在使用的快捷键；可反复执行。注销重登后
系统设置界面才会完全同步。

## 已知限制

- **Wayland 下无法由外部聚焦窗口**：聚焦依赖 Electron 自身的单实例机制，
  正常可用；但若某 profile 的窗口被最小化到托盘，行为取决于 Claude Desktop。
- **profile 首次创建约占 12 MB**，随聊天记录与缓存增长。
- **不共享登录态是特性而非缺陷**：每个 profile 都需各自登录一次。

## 与 cswap 的关系

本项目管理的是 **Claude Desktop 桌面应用**的多账号。若要在 **Claude Code CLI**
中切换账号，请用 [claude-swap](https://github.com/realiti4/claude-swap)（`cswap`），
两者互不冲突、可同时使用。

## 致谢

设计借鉴 [odahcam/claude-desktop-profiles](https://github.com/odahcam/claude-desktop-profiles)
（macOS，SwiftUI + Shell）。本项目是面向 Linux 的重新实现：隔离机制同样基于
`--user-data-dir`，但 Linux 无需 APFS 克隆、无需改 app 签名与图标，
直接以不同参数启动同一个二进制即可，因而实现更简单。

## 许可

MIT
