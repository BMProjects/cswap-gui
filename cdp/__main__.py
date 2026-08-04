"""cdp 命令行入口。不带子命令时直接打开 TUI。"""

from __future__ import annotations

import argparse
import sys

from cdp import manager
from cdp.core import DEFAULT_NAME, CdpError

EPILOG = f"""\
「{DEFAULT_NAME}」是系统已安装的 Claude Desktop 本身，自动出现在列表里，
可启动但不能改色或移除——它由安装本身管理，cdp 从不改动它。
claude:// 登录回调固定由它接管，所以已登录的账号请继续用它。

新建的 profile 数据独立存放，互不共享登录态、设置与 MCP 连接器；
新账号在其首次启动时自行登录。

不带任何参数运行 cdp 会打开交互界面。
"""


def _print_table(rows: list[manager.ProfileStatus]) -> None:
    if not rows:
        print("没有检测到 Claude Desktop 配置。请先正常启动一次 Claude Desktop。")
        return
    # 表头一律 ASCII：中文字符宽度与字节数不一致，混排会让列错位。
    print(f"{'NAME':<18} {'COLOR':<8} {'STATE':<9} {'SIZE':<7} LAUNCHER")
    for row in rows:
        state = "running" if row.running else "-"
        launcher = "ok" if row.has_launcher else "MISSING"
        print(f"{row.name:<18} {row.color:<8} {state:<9} {row.size:<7} {launcher}")


def cmd_list(args: argparse.Namespace) -> int:
    rows = manager.list_status(with_size=not args.no_size)
    if args.porcelain:
        for row in rows:
            print(
                "\t".join(
                    [
                        row.name,
                        row.color,
                        "1" if row.running else "0",
                        row.size,
                        "1" if row.has_launcher else "0",
                    ]
                )
            )
    else:
        _print_table(rows)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    profile = manager.add_profile(args.name, args.color)
    print(f"已创建 profile「{profile.name}」({profile.color})")
    print(f"  数据目录: {profile.directory}")
    print(
        f"  启动    : cdp launch {profile.name}（或在应用菜单搜索 Claude — {profile.name}）"
    )
    print("  提示    : 首次启动时在该 profile 内登录另一个账号即可")
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    profile, already = manager.launch(args.name)
    if already:
        print(f"「{profile.name}」已在运行，Electron 会聚焦其已有窗口。")
    print(f"已启动「{profile.name}」")
    return 0


def cmd_color(args: argparse.Namespace) -> int:
    profile = manager.set_color(args.name, args.color)
    print(f"profile「{profile.name}」配色已改为 {profile.color}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    if args.purge and sys.stdin.isatty():
        target = manager.find_profile(args.name).directory
        reply = input(f"确认删除数据目录 {target}?（登录态与聊天记录不可恢复）[y/N] ")
        if not reply.strip().lower().startswith("y"):
            print("已取消。")
            return 0
    profile, purged = manager.remove_profile(args.name, purge=args.purge)
    print("已移除启动器与图标。")
    if purged:
        print(f"已删除数据目录 {profile.directory}")
    else:
        print(f"数据目录保留在 {profile.directory}（加 --purge 可一并删除）")
    return 0


def cmd_prune(_args: argparse.Namespace) -> int:
    removed, kept = manager.prune_shortcuts()
    print(f"已清理 {removed} 条失效的 Claude 全局快捷键条目，保留 {kept} 条生效中的。")
    if removed:
        print("提示：注销重登后系统设置界面才会完全同步。")
    return 0


def cmd_tui(_args: argparse.Namespace) -> int:
    from cdp.tui import run

    return run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cdp",
        description="Claude Desktop Profiles — 在 Linux 上并行运行多个 Claude Desktop 账号",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subs = parser.add_subparsers(dest="command")

    p_list = subs.add_parser("list", aliases=["ls"], help="列出所有 profile")
    p_list.add_argument(
        "--porcelain", action="store_true", help="机器可读的制表符分隔输出"
    )
    p_list.add_argument(
        "--no-size", action="store_true", help="跳过磁盘占用统计（更快）"
    )
    p_list.set_defaults(func=cmd_list)

    p_add = subs.add_parser("add", help="新建空 profile 并生成应用菜单启动器")
    p_add.add_argument("name")
    p_add.add_argument(
        "--color", default="orange", help=" / ".join(manager.color_names())
    )
    p_add.set_defaults(func=cmd_add)

    p_launch = subs.add_parser(
        "launch", aliases=["run"], help="启动 profile（已运行则聚焦）"
    )
    p_launch.add_argument("name")
    p_launch.set_defaults(func=cmd_launch)

    p_color = subs.add_parser("color", help="更换配色与图标")
    p_color.add_argument("name")
    p_color.add_argument("color", help=" / ".join(manager.color_names()))
    p_color.set_defaults(func=cmd_color)

    p_remove = subs.add_parser(
        "remove", aliases=["rm"], help="移除启动器；--purge 连数据一起删"
    )
    p_remove.add_argument("name")
    p_remove.add_argument(
        "--purge", action="store_true", help="同时删除数据目录（不可恢复）"
    )
    p_remove.set_defaults(func=cmd_remove)

    p_prune = subs.add_parser(
        "prune-shortcuts", help="清理 KDE 中堆积的失效 Claude 全局快捷键"
    )
    p_prune.set_defaults(func=cmd_prune)

    p_tui = subs.add_parser("tui", help="打开交互界面（等同于不带参数运行）")
    p_tui.set_defaults(func=cmd_tui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        return cmd_tui(args)
    try:
        return args.func(args)
    except CdpError as error:
        print(f"cdp: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
