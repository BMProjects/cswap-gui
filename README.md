# claude-swap GUI

*A zero-dependency tkinter front-end for
[claude-swap](https://github.com/realiti4/claude-swap): switch between
Claude Code accounts and watch per-account usage quotas at a glance.*

[claude-swap](https://github.com/realiti4/claude-swap)（`cswap`）的 tkinter 图形前端，
用于在多个 Claude Code 订阅账号之间一键切换，并直观查看各账号的额度用量。

全部逻辑在单个文件 [cswap_gui.py](cswap_gui.py) 中，仅使用 Python 标准库。

## 功能

- 列出所有托管账号，标记当前活跃账号
- 每个账号显示三条额度进度条：
  - **5h** — 5 小时滚动窗口
  - **7d** — 7 天窗口
  - **Fable** — Fable 模型独立周额度（scoped 窗口，cswap ≥ 0.17 提供；
    将来上游新增其它按模型额度会自动显示，无需改代码）
- 每条额度附重置时间与剩余倒计时；非活跃账号的用量由 cswap 提供
  last-known 数据，超过 15 分钟会标注「用量为 X 前数据」
- 凭据失效（`no_credentials` / `token_expired`）的账号显示 ⚠ 警告，
  切换前弹窗提示先用 `/login` + `cswap --add-account` 修复
- 一键添加当前登录账号、升级 cswap
- 可选「每分钟自动刷新」（复选框开启）：自动更新各账号额度，
  状态栏显示最近更新时间；自动刷新失败只在状态栏提示，不弹窗打扰

## 依赖

| 依赖 | 安装方式 |
|------|----------|
| Python 3.10+ 与 tkinter | `sudo apt install python3-tk`（Debian/Ubuntu） |
| claude-swap ≥ 0.17 | `uv tool install claude-swap` |

## 运行

```sh
python3 cswap_gui.py
```

### 安装桌面入口（可选）

```sh
./install.sh
```

脚本会把 [cswap-gui.desktop](cswap-gui.desktop)（`Exec=` 中的
`@PROJECT_DIR@` 占位符替换为仓库实际路径）装入
`~/.local/share/applications/`，图标 [cswap-gui.svg](cswap-gui.svg) 装入
`~/.local/share/icons/hicolor/scalable/apps/`。装完后在应用菜单搜索
「Claude 账号切换」即可启动。卸载则删除这两个安装出的文件。

## 实现说明

- 数据来源为 `cswap --list --json`（`schemaVersion: 1`）。上游承诺该契约
  只增不改；若 schemaVersion 升级，GUI 会明确报错而不是静默误解析。
- 只读取 stdout 解析 JSON，stderr 的警告信息不会污染数据。
- 切换 / 添加账号 / 升级均在后台线程执行，UI 不阻塞。

### 查询额度是否消耗 token？

不消耗。额度查询走 `GET https://api.anthropic.com/api/oauth/usage`
只读元数据接口（与 Claude Code 内置 `/usage` 命令相同），不产生模型推理，
不计入任何额度窗口。频繁查询的唯一风险是该接口本身的 HTTP 429 限速，
cswap 已内置多层保护，GUI 直接受益：

- 结果缓存 30 秒（`SERVE_TTL_S`）：30 秒内重复查询直接读缓存，不发请求
- 失败退避：30s·2ⁿ 指数退避（上限 10 分钟），并遵守服务端 `Retry-After`
- 凭据安全：Claude Code 运行期间不动活跃账号的 OAuth token（避免刷新竞争）

因此 60 秒自动刷新每次最多产生「账号数」个轻量 GET，安全且开销可忽略。

## 配套定时任务（可选参考配置）

以下是作者本机的 systemd user 定时任务，与本 GUI 无直接依赖，
仅作为同一套账号额度管理思路的参考：

| 单元 | 时间 | 作用 |
|------|------|------|
| `ai-cli-maintenance.timer` | 每天 05:00 及开机后 3 分钟 | 升级 CLI 后用 haiku 发一条最小请求，提前触发 5h 额度窗口开始计时（Fable 为周额度，无需预热） |
| `claude-swap-update.timer` | 每周一 00:00 | `uv tool upgrade claude-swap` |

单元文件位于 `~/.config/systemd/user/`。

## 许可证

[MIT](LICENSE)
