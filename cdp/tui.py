"""curses 交互界面。

仅用 stdlib：curses 随 CPython 一起安装，无需像 tkinter 那样另装系统包。
所有动作都委托给 manager，界面本身不含业务规则。

布局：标题 / profile 列表 / 状态行 / 常驻按键提示。
"""

from __future__ import annotations

import curses
import unicodedata

from cdp import manager
from cdp.core import COLORS, DEFAULT_NAME, CdpError, ProfileStatus

# 运行状态的探测很廉价，可以频繁刷新；磁盘占用要遍历整个目录树，
# 只在启动时和用户按 r 时才重算。
RUNNING_POLL_MS = 3000

_CURSES_COLOR = {
    "orange": (208, curses.COLOR_YELLOW),
    "red": (203, curses.COLOR_RED),
    "yellow": (221, curses.COLOR_YELLOW),
    "green": (71, curses.COLOR_GREEN),
    "teal": (73, curses.COLOR_CYAN),
    "blue": (68, curses.COLOR_BLUE),
    "purple": (98, curses.COLOR_MAGENTA),
    "pink": (168, curses.COLOR_MAGENTA),
    "system": (245, curses.COLOR_WHITE),
}
PAIR_SELECTED = 100
PAIR_DIM = 101
PAIR_RUNNING = 102
PAIR_HEADER = 103


def display_width(text: str) -> int:
    """终端列宽：中日韩字符占两列，按字符数算会让列错位。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    out, used = [], 0
    for char in text:
        w = 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if used + w > width:
            break
        out.append(char)
        used += w
    return "".join(out)


def pad(text: str, width: int) -> str:
    return truncate(text, width) + " " * max(
        0, width - display_width(truncate(text, width))
    )


class Tui:
    def __init__(self, stdscr: curses.window) -> None:
        self.stdscr = stdscr
        self.rows: list[ProfileStatus] = []
        self.cursor = 0
        self.message = ""
        self._init_colors()
        self.reload(with_size=True)

    # ---------- 基础设施 ----------

    def _init_colors(self) -> None:
        self.has_color = curses.has_colors()
        if not self.has_color:
            return
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        extended = curses.COLORS >= 256
        for index, (name, (rich, basic)) in enumerate(_CURSES_COLOR.items(), start=1):
            try:
                curses.init_pair(index, rich if extended else basic, -1)
            except curses.error:
                curses.init_pair(index, basic, -1)
            setattr(self, f"_pair_{name}", index)
        curses.init_pair(PAIR_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(PAIR_DIM, curses.COLOR_WHITE, -1)
        curses.init_pair(PAIR_RUNNING, curses.COLOR_GREEN, -1)
        curses.init_pair(PAIR_HEADER, curses.COLOR_CYAN, -1)

    def color_attr(self, name: str) -> int:
        if not self.has_color:
            return curses.A_NORMAL
        index = getattr(self, f"_pair_{name}", None)
        if index is None:
            index = getattr(self, "_pair_orange", 1)
        return curses.color_pair(index)

    def pair(self, number: int) -> int:
        return curses.color_pair(number) if self.has_color else curses.A_NORMAL

    def put(self, y: int, x: int, text: str, attr: int = curses.A_NORMAL) -> None:
        """越界写入会让 curses 抛错，统一在这里裁剪。"""
        height, width = self.stdscr.getmaxyx()
        if y < 0 or y >= height or x >= width:
            return
        text = truncate(text, width - x - 1)
        if text:
            try:
                self.stdscr.addstr(y, x, text, attr)
            except curses.error:
                pass

    # ---------- 数据 ----------

    def reload(self, with_size: bool = True) -> None:
        try:
            self.rows = manager.list_status(with_size=with_size)
        except CdpError as error:
            self.rows = []
            self.message = str(error)
        self.cursor = max(0, min(self.cursor, len(self.rows) - 1))

    def poll_running(self) -> None:
        """只更新运行状态，不重算磁盘占用。"""
        if not self.rows:
            return
        try:
            fresh = {r.name: r.running for r in manager.list_status(with_size=False)}
        except CdpError:
            return
        self.rows = [
            ProfileStatus(
                profile=row.profile,
                running=fresh.get(row.name, row.running),
                size=row.size,
                has_launcher=row.has_launcher,
            )
            for row in self.rows
        ]

    @property
    def current(self) -> ProfileStatus | None:
        return self.rows[self.cursor] if self.rows else None

    # ---------- 绘制 ----------

    def draw(self) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        if height < 8 or width < 46:
            self.put(0, 0, "终端太小，请放大窗口", curses.A_BOLD)
            self.stdscr.refresh()
            return

        self.put(0, 1, "Claude Desktop 多账号", curses.A_BOLD | self.pair(PAIR_HEADER))
        running = sum(1 for r in self.rows if r.running)
        self.put(
            0,
            width - 22,
            f"{len(self.rows)} 个 · {running} 个运行中",
            self.pair(PAIR_DIM),
        )
        self.put(1, 0, "─" * (width - 1), self.pair(PAIR_DIM))

        self._draw_rows(top=2, bottom=height - 4, width=width)

        self.put(height - 3, 0, "─" * (width - 1), self.pair(PAIR_DIM))
        self.put(height - 2, 1, truncate(self.message, width - 3), self.pair(PAIR_DIM))
        self._draw_hints(height - 1, width)
        self.stdscr.refresh()

    def _draw_rows(self, top: int, bottom: int, width: int) -> None:
        if not self.rows:
            self.put(top + 1, 2, "没有检测到 Claude Desktop 配置。", curses.A_BOLD)
            self.put(
                top + 3,
                2,
                "请先正常启动一次 Claude Desktop，它会作为",
                self.pair(PAIR_DIM),
            )
            self.put(
                top + 4,
                2,
                "「Default」出现在这里；再按 a 添加其他账号。",
                self.pair(PAIR_DIM),
            )
            return

        visible = bottom - top
        start = max(0, min(self.cursor - visible // 2, len(self.rows) - visible))
        start = max(0, start)
        name_w = max(12, min(24, width - 40))

        for offset, row in enumerate(self.rows[start : start + visible]):
            y = top + offset
            selected = start + offset == self.cursor
            base = (
                self.pair(PAIR_SELECTED) | curses.A_BOLD
                if selected
                else curses.A_NORMAL
            )
            self.put(y, 0, " " * (width - 1), base)
            self.put(y, 1, "▸" if selected else " ", base)
            self.put(y, 3, "●", base if selected else self.color_attr(row.color))
            self.put(
                y,
                5,
                pad(row.name, name_w),
                base | (curses.A_BOLD if not selected else 0),
            )

            x = 5 + name_w + 1
            tag = "系统自带" if row.is_default else row.color
            self.put(y, x, pad(tag, 10), base if selected else self.pair(PAIR_DIM))
            x += 11
            if row.running:
                self.put(
                    y,
                    x,
                    pad("运行中", 8),
                    base if selected else self.pair(PAIR_RUNNING),
                )
            else:
                self.put(y, x, pad("", 8), base)
            x += 9
            self.put(y, x, pad(row.size, 7), base if selected else self.pair(PAIR_DIM))
            if not row.has_launcher:
                self.put(
                    y, x + 8, "启动器缺失", base if selected else self.pair(PAIR_DIM)
                )

    def _draw_hints(self, y: int, width: int) -> None:
        row = self.current
        hints = [("↑↓", "选择"), ("Enter", "启动")]
        if row is not None and not row.is_default:
            hints += [("c", "配色"), ("d", "删除")]
        hints += [("a", "新建"), ("r", "刷新"), ("?", "帮助"), ("q", "退出")]
        x = 1
        for key, label in hints:
            if x + len(key) + display_width(label) + 3 >= width:
                break
            self.put(y, x, key, curses.A_BOLD | self.pair(PAIR_HEADER))
            x += len(key) + 1
            self.put(y, x, label, self.pair(PAIR_DIM))
            x += display_width(label) + 2

    # ---------- 交互原语 ----------

    def prompt(self, label: str, allowed: str | None = None) -> str | None:
        """底部单行输入。Enter 确认，Esc 取消。"""
        height, width = self.stdscr.getmaxyx()
        buffer = ""
        curses.curs_set(1)
        try:
            while True:
                self.put(height - 2, 0, " " * (width - 1))
                self.put(height - 2, 1, label, curses.A_BOLD)
                field_x = 1 + display_width(label) + 1
                self.put(height - 2, field_x, buffer)
                self.stdscr.move(
                    height - 2, min(field_x + display_width(buffer), width - 2)
                )
                self.stdscr.refresh()

                key = self.stdscr.get_wch()
                if key in ("\x1b",):
                    return None
                if key in ("\n", "\r", curses.KEY_ENTER):
                    return buffer.strip()
                if key in ("\x7f", "\b", curses.KEY_BACKSPACE):
                    buffer = buffer[:-1]
                    continue
                accepted = allowed is None or (isinstance(key, str) and key in allowed)
                if isinstance(key, str) and key.isprintable() and accepted:
                    buffer += key
        finally:
            curses.curs_set(0)

    def confirm(self, question: str, danger: bool = False) -> bool:
        """默认为「否」：破坏性操作必须显式按 y。"""
        height, width = self.stdscr.getmaxyx()
        attr = curses.A_BOLD | (
            self.pair(PAIR_RUNNING) if not danger else curses.A_REVERSE
        )
        while True:
            self.put(height - 2, 0, " " * (width - 1))
            self.put(height - 2, 1, truncate(f"{question} [y/N] ", width - 3), attr)
            self.stdscr.refresh()
            key = self.stdscr.getch()
            if key in (ord("y"), ord("Y")):
                return True
            if key in (ord("n"), ord("N"), 27, ord("\n")):
                return False

    def choose(self, title: str, options: list[str]) -> str | None:
        """居中弹出的单选列表。↑↓ 移动，Enter 选中，Esc 取消。"""
        index = 0
        while True:
            height, width = self.stdscr.getmaxyx()
            box_h = len(options) + 4
            box_w = max(display_width(title) + 4, 24)
            top = max(0, (height - box_h) // 2)
            left = max(0, (width - box_w) // 2)

            for i in range(box_h):
                self.put(top + i, left, " " * box_w, curses.A_REVERSE)
            self.put(top + 1, left + 2, title, curses.A_REVERSE | curses.A_BOLD)
            for i, option in enumerate(options):
                selected = i == index
                mark = "▸ " if selected else "  "
                attr = curses.A_REVERSE | (curses.A_BOLD if selected else 0)
                self.put(top + 2 + i, left + 2, pad(mark + option, box_w - 4), attr)
            self.put(
                top + box_h - 1, left + 2, "Enter 选中 · Esc 取消", curses.A_REVERSE
            )
            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key in (curses.KEY_UP, ord("k")):
                index = (index - 1) % len(options)
            elif key in (curses.KEY_DOWN, ord("j")):
                index = (index + 1) % len(options)
            elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                return options[index]
            elif key == 27:
                return None

    def show_help(self) -> None:
        lines = [
            "cdp — Claude Desktop 多账号",
            "",
            "↑ ↓ / k j   选择 profile",
            "Enter       启动（已运行则聚焦其窗口）",
            "a           新建 profile（随后在其中登录另一个账号）",
            "c           更换配色与图标",
            "d           删除（可选是否连数据一起删）",
            "r           刷新（含重算磁盘占用）",
            "q           退出",
            "",
            f"「{DEFAULT_NAME}」是系统已装的 Claude Desktop 本身，",
            "由安装本身管理，只能启动，不能改色或删除。",
            "claude:// 登录回调固定由它接管，已登录的账号请继续用它。",
            "",
            "按任意键返回",
        ]
        height, width = self.stdscr.getmaxyx()
        box_w = min(width - 2, max(display_width(line) for line in lines) + 6)
        box_h = min(height - 2, len(lines) + 2)
        top = max(0, (height - box_h) // 2)
        left = max(0, (width - box_w) // 2)
        for i in range(box_h):
            self.put(top + i, left, " " * box_w, curses.A_REVERSE)
        for i, line in enumerate(lines[: box_h - 2]):
            self.put(top + 1 + i, left + 3, line, curses.A_REVERSE)
        self.stdscr.refresh()
        self.stdscr.getch()

    # ---------- 动作 ----------

    def act_launch(self) -> None:
        row = self.current
        if row is None:
            return
        try:
            profile, already = manager.launch(row.name)
        except CdpError as error:
            self.message = str(error)
            return
        self.message = (
            f"「{profile.name}」已在运行，已聚焦其窗口。"
            if already
            else f"已启动「{profile.name}」"
        )
        self.poll_running()

    def act_add(self) -> None:
        name = self.prompt("新 profile 名称（字母或数字）：")
        if not name:
            self.message = "已取消新建。" if name is None else "名称不能为空。"
            return
        color = self.choose("选择配色", list(COLORS))
        if color is None:
            self.message = "已取消新建。"
            return
        try:
            profile = manager.add_profile(name, color)
        except CdpError as error:
            self.message = str(error)
            return
        self.reload()
        for i, row in enumerate(self.rows):
            if row.name == profile.name:
                self.cursor = i
                break
        self.message = f"已创建「{profile.name}」，按 Enter 启动并在其中登录账号。"

    def act_color(self) -> None:
        row = self.current
        if row is None or row.is_default:
            self.message = f"「{DEFAULT_NAME}」用的是官方图标，不能改配色。"
            return
        color = self.choose(f"「{row.name}」的配色", list(COLORS))
        if color is None:
            return
        try:
            manager.set_color(row.name, color)
        except CdpError as error:
            self.message = str(error)
            return
        self.reload(with_size=False)
        self.message = f"「{row.name}」配色已改为 {color}"

    def act_remove(self) -> None:
        row = self.current
        if row is None:
            return
        if row.is_default:
            self.message = f"「{DEFAULT_NAME}」由 Claude Desktop 安装管理，不能删除。"
            return
        if not self.confirm(f"移除「{row.name}」的启动器？"):
            self.message = "已取消。"
            return
        purge = self.confirm(
            f"同时删除数据目录？登录态与聊天记录不可恢复（{row.size}）", danger=True
        )
        try:
            profile, purged = manager.remove_profile(row.name, purge=purge)
        except CdpError as error:
            self.message = str(error)
            return
        self.reload()
        self.message = (
            f"已删除「{profile.name}」及其数据。"
            if purged
            else f"已移除「{profile.name}」的启动器，数据保留在 {profile.directory}"
        )

    # ---------- 主循环 ----------

    def loop(self) -> None:
        self.stdscr.timeout(RUNNING_POLL_MS)
        while True:
            self.draw()
            try:
                key = self.stdscr.getch()
            except KeyboardInterrupt:
                return

            if key == -1:
                self.poll_running()
                continue
            if key in (ord("q"), ord("Q")):
                return
            if key == curses.KEY_RESIZE:
                continue
            if key in (curses.KEY_UP, ord("k")) and self.rows:
                self.cursor = (self.cursor - 1) % len(self.rows)
            elif key in (curses.KEY_DOWN, ord("j")) and self.rows:
                self.cursor = (self.cursor + 1) % len(self.rows)
            elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                self.act_launch()
            elif key in (ord("a"), ord("A")):
                self.act_add()
            elif key in (ord("c"), ord("C")):
                self.act_color()
            elif key in (ord("d"), ord("D"), curses.KEY_DC):
                self.act_remove()
            elif key in (ord("r"), ord("R")):
                self.reload(with_size=True)
                self.message = "已刷新。"
            elif key in (ord("?"), ord("h")):
                self.show_help()


def run() -> int:
    def _main(stdscr: curses.window) -> int:
        curses.curs_set(0)
        stdscr.keypad(True)
        Tui(stdscr).loop()
        return 0

    try:
        return curses.wrapper(_main)
    except KeyboardInterrupt:
        return 130
