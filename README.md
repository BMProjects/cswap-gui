# Claude Desktop Profiles for Linux

在 Linux 上并行运行多个 Claude Desktop 账号。每个 profile 拥有独立的登录状态、
聊天记录、设置与 MCP 连接器，可同时开着互不干扰。

纯 stdlib Python：一个命令行 + 一个 curses 交互界面。零安装依赖、无 Electron 包装、无遥测。

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

只需要 Claude Desktop 和 Python 3.10+（发行版自带）。**无第三方依赖，
不用装 python3-tk，不用 pip，不用 npm。**

```bash
git clone https://github.com/BMProjects/claude-desktop-profiles-linux.git
cd claude-desktop-profiles-linux
./install.sh
```

安装脚本把 `cdp` 软链到 `~/.local/bin`，并把「Claude Desktop 多账号」交互界面
装进应用菜单。软链而非拷贝，更新仓库后立即生效。

## 使用

```bash
cdp list                       # 名称 / 配色 / 运行状态 / 磁盘占用 / 启动器
cdp add Work --color blue      # 新建空 profile，首次启动时在其中登录另一个账号
cdp launch Work                # 启动（已运行则聚焦）
cdp color Work purple          # 换配色与图标
cdp remove Work                # 移除启动器，保留数据
cdp remove Work --purge        # 连数据目录一并删除（会二次确认）
cdp                            # 不带参数即打开交互界面
```

配色：`orange` `red` `yellow` `green` `teal` `blue` `purple` `pink`

新建后可直接在应用菜单里搜索「Claude — Work」启动，无需终端。

### 「Default」——系统已装的那个

列表里第一项 `Default` 就是系统已安装的 Claude Desktop 本身
（`~/.config/Claude`）。它**不由 cdp 创建，也不会被复制到别处**，只是被纳入
列表统一管理：

- 可以 `cdp launch Default` 启动，或照旧从应用菜单里的官方「Claude」打开
- **不能改色或移除**——它归 Claude Desktop 安装本身管理，cdp 从不改动它
- 启动它时刻意不带 `--user-data-dir`，进程特征与官方启动器一致

**已登录的账号请继续用它。** `claude://` 登录回调固定由它接管（见下文），
所以它是唯一能顺畅完成登录的配置；新账号才用 `cdp add` 建新 profile。

> 早期版本提供过 `cdp import`（把 Default 复制成新 profile），现已移除：
> 复制会让两个目录持有同一账号的凭据副本，容易触发服务端重新验证，且复制出来
> 的那份因回调归属问题也无法独立完成登录。直接把 Default 当默认账号用即可。

## 交互界面

直接运行 `cdp`（不带参数），或在应用菜单打开「Claude Desktop 多账号」。

```
 Claude Desktop 多账号                         2 个 · 1 个运行中
────────────────────────────────────────────────────────────────
 ▸ ● Default      系统自带   运行中    594M
   ● work         blue                 12M
────────────────────────────────────────────────────────────────
 已启动「Default」
 ↑↓ 选择  Enter 启动  c 配色  d 删除  a 新建  r 刷新  ? 帮助  q 退出
```

按键提示常驻底部，删除等破坏性操作一律二次确认且默认为「否」。
运行状态每 3 秒自动刷新（磁盘占用较慢，只在按 `r` 时重算）。

界面用 stdlib `curses` 写成——它随 Python 一起安装，不像 `tkinter` 那样
需要另装系统包，因此在任何发行版上开箱即用。所有动作都委托给同一套操作层，
与命令行行为完全一致。

## 在新 profile 里登录时会跳回 Default（重要）

**现象**：在新建的 profile 里点登录，验证走完却跳回 `Default` 的账号，
该 profile 依旧是空的。

**原因**：登录回调走 `claude://` 协议，而系统里该协议的处理器是官方的
`com.anthropic.Claude.desktop`，其 `Exec=claude-desktop %U` **不带
`--user-data-dir`**——回调因此必然由 `Default` 接管，发起登录的 profile 收不到。
这是单一全局协议与多 profile 的固有冲突：系统无从知道是哪个 profile 发起的。

这也正是**已登录的账号应当继续用 `Default`** 的原因：它是回调的天然归属方。

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

## 项目结构

```
cdp/
├── core.py            跨平台核心：数据模型、配色、启动命令拼装
├── platform_linux.py  平台集成：.desktop、hicolor 图标、进程检测、KDE 快捷键
├── manager.py         操作层：增删改查与全部守卫，两个前端共用
├── __main__.py        命令行：参数解析与文本输出
└── tui.py             curses 交互界面
```

平台相关的代码全部收在 `platform_linux.py` 一处，移植到 macOS / Windows 时
只需替换该模块——`core`、`manager` 与两个前端都不必改动。业务规则只存在于
`manager.py`，命令行与交互界面因此不会出现行为分叉。

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
