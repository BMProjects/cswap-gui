#!/usr/bin/env python3
"""Claude Desktop Profiles — 图形管理界面。

所有实际操作都委托给 `cdp` CLI(单一事实来源),本界面只负责展示与交互:
每个 profile 一张卡片,显示配色、运行状态与磁盘占用,可一键启动、换色、移除。

依赖:python3-tk。profile 数据由 cdp 存放在 $XDG_CONFIG_HOME/Claude-<名称>/。
"""

import os
import shutil
import subprocess
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, simpledialog, ttk

COLORS = {
    "orange": "#D97757",
    "red": "#C6483C",
    "yellow": "#D9A441",
    "green": "#4C9A5A",
    "teal": "#3F8F8A",
    "blue": "#3D74D9",
    "purple": "#7A5AA8",
    "pink": "#C05B87",
}
# 深色主题(stdlib ttk 'clam' 自定义),与 cdp 生成的图标配色同源。
PALETTE = {
    "bg": "#26282B",
    "text": "#E4E6EA",
    "muted": "#9AA0A8",
    "border": "#3F4248",
    "hover": "#34373C",
    "accent": "#3D74D9",
    "accent_active": "#4A83F5",
    "disabled": "#4A4D52",
}
RUNNING_FG = "#4C9A5A"
REFRESH_INTERVAL_MS = 5_000
# cdp 用这个色名标记「系统自带的 Claude Desktop」这一内置条目。
SYSTEM_COLOR = "system"
SYSTEM_DOT = "#8A9099"


def find_cdp() -> str:
    """cdp 可执行文件路径:优先 PATH,再退到与本文件同级的 bin/。"""
    path = shutil.which("cdp")
    if path:
        return path
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "cdp")
    local = os.path.normpath(local)
    if os.access(local, os.X_OK):
        return local
    raise FileNotFoundError("找不到 cdp，请先运行 install.sh")


def run_cdp(*args: str) -> str:
    result = subprocess.run(
        [find_cdp(), *args], capture_output=True, text=True, timeout=120, check=False
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr + result.stdout).strip() or "cdp 执行失败")
    return result.stdout


def parse_profiles(porcelain: str) -> list[dict]:
    """解析 `cdp list --porcelain`:每行 name/color/running/size/launcher。"""
    profiles = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 5:
            continue
        name, color, running, size, launcher = fields[:5]
        profiles.append(
            {
                "name": name,
                "color": color,
                "running": running == "1",
                "size": size or "?",
                "launcher": launcher == "1",
                # 色名 "system" 是 cdp 对「系统自带的那个」的标记:它由
                # Claude Desktop 安装本身管理,只能启动,不能改色或移除。
                "builtin": color == SYSTEM_COLOR,
            }
        )
    return profiles


def apply_theme(root: tk.Tk) -> None:
    p = PALETTE
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(background=p["bg"])
    style.configure(
        ".",
        background=p["bg"],
        foreground=p["text"],
        bordercolor=p["border"],
        lightcolor=p["bg"],
        darkcolor=p["bg"],
        focuscolor=p["accent"],
    )
    style.configure("Muted.TLabel", foreground=p["muted"])
    style.configure("Running.TLabel", foreground=RUNNING_FG)
    style.configure("Card.TFrame", relief="solid", borderwidth=1)
    style.configure("TButton", padding=(10, 4))
    style.map("TButton", background=[("pressed", p["border"]), ("active", p["hover"])])
    style.configure(
        "Accent.TButton",
        background=p["accent"],
        foreground="white",
        bordercolor=p["accent"],
        lightcolor=p["accent"],
        darkcolor=p["accent"],
    )
    style.map(
        "Accent.TButton",
        background=[("disabled", p["disabled"]), ("active", p["accent_active"])],
        bordercolor=[("disabled", p["disabled"])],
        lightcolor=[("disabled", p["disabled"]), ("active", p["accent_active"])],
        darkcolor=[("disabled", p["disabled"]), ("active", p["accent_active"])],
    )
    # Combobox 的 readonly 态自带一套配色,不单独映射就会露出浅色默认皮肤;
    # 下拉列表是 Tk 原生 Listbox,只能经 option database 上色。
    style.configure("TCombobox", arrowcolor=p["text"])
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", p["bg"])],
        background=[("readonly", p["bg"]), ("active", p["hover"])],
        foreground=[("readonly", p["text"])],
        selectbackground=[("readonly", p["bg"])],
        selectforeground=[("readonly", p["text"])],
        bordercolor=[("readonly", p["border"])],
        lightcolor=[("readonly", p["bg"])],
        darkcolor=[("readonly", p["bg"])],
    )
    root.option_add("*TCombobox*Listbox.background", p["bg"])
    root.option_add("*TCombobox*Listbox.foreground", p["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "white")


class ProfilesGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Claude Desktop 多账号")
        root.minsize(560, 260)
        apply_theme(root)

        base = tkfont.nametofont("TkDefaultFont")
        self.title_font = base.copy()
        self.title_font.configure(weight="bold", size=base.actual("size") + 1)
        self.dot_font = base.copy()
        self.dot_font.configure(size=base.actual("size") + 6)

        self.cards_frame = ttk.Frame(root)
        self.cards_frame.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        row = ttk.Frame(root)
        row.pack(fill="x", padx=12, pady=8)
        ttk.Button(
            row, text="新建 Profile", style="Accent.TButton", command=self.add_profile
        ).pack(side="left")
        ttk.Button(row, text="刷新", command=self.refresh).pack(side="left", padx=6)

        self.message_var = tk.StringVar(value="加载中…")
        ttk.Label(root, textvariable=self.message_var, style="Muted.TLabel").pack(
            anchor="w", padx=12, pady=(0, 8)
        )

        self._busy = False
        self.refresh()
        root.after(REFRESH_INTERVAL_MS, self._tick)

    def run_async(self, work, on_done, notify: bool = True) -> None:
        def task() -> None:
            try:
                result = work()
            except Exception as error:  # noqa: BLE001 - 后台线程必须兜住一切异常，否则静默死掉
                message = str(error)

                def fail() -> None:
                    self.message_var.set(message.splitlines()[0][:90])
                    if notify:
                        messagebox.showerror("出错", message)

                self.root.after(0, fail)
                return
            self.root.after(0, lambda: on_done(result))

        threading.Thread(target=task, daemon=True).start()

    def _tick(self) -> None:
        """周期性刷新运行状态（Claude Desktop 可能在界面外被启动或关闭）。"""
        if not self._busy:
            self.refresh(quiet=True)
        self.root.after(REFRESH_INTERVAL_MS, self._tick)

    def refresh(self, quiet: bool = False) -> None:
        if not quiet:
            self.message_var.set("刷新中…")
        self.run_async(
            lambda: parse_profiles(run_cdp("list", "--porcelain")),
            self.show_profiles,
            notify=not quiet,
        )

    def show_profiles(self, profiles: list[dict]) -> None:
        for child in self.cards_frame.winfo_children():
            child.destroy()

        if not profiles:
            ttk.Label(
                self.cards_frame,
                justify="left",
                style="Muted.TLabel",
                text=(
                    "没有检测到 Claude Desktop 配置。\n\n"
                    "请先正常启动一次 Claude Desktop，它会作为「系统自带」\n"
                    "条目出现在这里；再用「新建 Profile」添加其他账号。"
                ),
            ).pack(anchor="w", pady=12)

        for profile in profiles:
            self._build_card(profile)

        running = sum(1 for p in profiles if p["running"])
        self.message_var.set(f"共 {len(profiles)} 个 profile · {running} 个运行中")

    def _build_card(self, profile: dict) -> None:
        name = profile["name"]
        card = ttk.Frame(self.cards_frame, padding=(12, 8), style="Card.TFrame")
        card.pack(fill="x", pady=6)

        header = ttk.Frame(card)
        header.pack(fill="x")
        builtin = profile["builtin"]
        ttk.Label(
            header,
            text="●",
            font=self.dot_font,
            foreground=SYSTEM_DOT
            if builtin
            else COLORS.get(profile["color"], COLORS["orange"]),
        ).pack(side="left", padx=(0, 8))
        ttk.Label(header, text=name, font=self.title_font).pack(side="left")
        if builtin:
            ttk.Label(header, text="系统自带", style="Muted.TLabel").pack(
                side="left", padx=8
            )
        if profile["running"]:
            ttk.Label(header, text="运行中", style="Running.TLabel").pack(
                side="left", padx=8
            )

        launch = ttk.Button(
            header,
            text="切换到此账号" if profile["running"] else "启动",
            style="Accent.TButton",
            command=lambda: self.launch(name),
        )
        launch.pack(side="right")

        detail = ttk.Frame(card)
        detail.pack(fill="x", pady=(6, 0))
        note = f"占用 {profile['size']}"
        if builtin:
            note += " · 由 Claude Desktop 安装管理，登录回调归它接管"
        elif not profile["launcher"]:
            note += " · ⚠ 应用菜单启动器缺失"
        ttk.Label(detail, text=note, style="Muted.TLabel").pack(side="left")

        # 系统自带的那个不提供改色/移除:它不归 cdp 管,也不该被 cdp 删掉。
        if builtin:
            return

        ttk.Button(detail, text="移除", command=lambda: self.remove(name)).pack(
            side="right"
        )
        picker = ttk.Combobox(
            detail,
            values=list(COLORS),
            width=8,
            state="readonly",
        )
        picker.set(profile["color"])
        picker.bind(
            "<<ComboboxSelected>>",
            lambda _event, n=name, w=picker: self.set_color(n, w.get()),
        )
        picker.pack(side="right", padx=6)

    def add_profile(self) -> None:
        name = simpledialog.askstring(
            "新建 Profile", "名称（例如 Work、Personal）：", parent=self.root
        )
        if not name or not name.strip():
            return
        name = name.strip()
        self._busy = True
        self.message_var.set(f"正在创建「{name}」…")
        self.run_async(
            lambda: run_cdp("add", name),
            lambda _out: self._done(f"已创建「{name}」"),
        )

    def launch(self, name: str) -> None:
        self._busy = True
        self.message_var.set(f"正在启动「{name}」…")
        self.run_async(
            lambda: run_cdp("launch", name),
            lambda _out: self._done(f"已启动「{name}」"),
        )

    def set_color(self, name: str, color: str) -> None:
        self._busy = True
        self.run_async(
            lambda: run_cdp("color", name, color),
            lambda _out: self._done(f"「{name}」配色已改为 {color}"),
        )

    def remove(self, name: str) -> None:
        purge = messagebox.askyesnocancel(
            "移除 Profile",
            f"移除「{name}」的应用菜单启动器。\n\n"
            "是 = 同时删除数据目录（登录态与聊天记录不可恢复）\n"
            "否 = 仅移除启动器，保留数据\n"
            "取消 = 不做任何操作",
            icon="warning",
            default="no",
        )
        if purge is None:
            return
        args = ["remove", name] + (["--purge"] if purge else [])
        self._busy = True
        self.message_var.set(f"正在移除「{name}」…")
        self.run_async(
            lambda: run_cdp(*args), lambda _out: self._done(f"已移除「{name}」")
        )

    def _done(self, message: str) -> None:
        self._busy = False
        self.message_var.set(message)
        self.refresh(quiet=True)


def main() -> None:
    root = tk.Tk()
    ProfilesGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
