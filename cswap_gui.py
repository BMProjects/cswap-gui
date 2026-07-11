#!/usr/bin/env python3
"""Simple tkinter GUI for claude-swap (cswap) account switching.

Requires: python3-tk, claude-swap >= 0.17 (`uv tool install claude-swap`).

Reads `cswap --list --json` (schemaVersion 1). Usage windows are rendered
dynamically: the base 5h/7d windows plus any scoped per-model windows
(e.g. Fable). cswap serves last-known usage for inactive accounts itself,
so no local cache is kept; stale measurements are marked with their age.
"""

import json
import os
import shutil
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

BASE_WINDOWS = (("fiveHour", "5h"), ("sevenDay", "7d"))
STALE_STATUSES = frozenset({"no_credentials", "token_expired", "relogin_required"})
STATUS_NOTES = {
    "token_expired": "令牌已过期（Claude Code 使用中，其下次请求后自动恢复）",
    "relogin_required": "需重新登录：先在 Claude CLI /login，再 cswap --add-account",
    "no_credentials": "凭据缺失",
    "keychain_unavailable": "钥匙串不可用",
    "unavailable": "用量获取失败",
    "api_key": "API key 账号，无订阅额度",
}
AGE_NOTE_THRESHOLD_S = 900
# 自动刷新间隔。查询走 api.anthropic.com/api/oauth/usage 只读接口,不消耗
# 模型 token;cswap 自带 30s 结果缓存(SERVE_TTL_S)和失败退避,60s 间隔
# 每次最多产生账号数个轻量 GET。
AUTO_REFRESH_INTERVAL_MS = 60_000
# 进度条按用量分级变色:绿(宽裕)/琥珀(过半)/红(接近上限)。
USAGE_BAR_COLORS = (("Low", "#4CAF50"), ("Mid", "#E8A33D"), ("High", "#D9534F"))
USAGE_MID_PCT = 50
USAGE_HIGH_PCT = 80
# 深色主题(stdlib ttk 'clam' 自定义),无第三方依赖。统一背景色,
# 卡片仅以细边框区分,自定义样式压到最少。
PALETTE = {
    "bg": "#26282B",
    "text": "#E4E6EA",
    "muted": "#9AA0A8",
    "border": "#3F4248",
    "trough": "#3A3D42",
    "hover": "#34373C",
    "accent": "#3D74D9",
    "accent_active": "#4A83F5",
    "disabled": "#4A4D52",
}
STALE_FG = "#E0B341"


def usage_style(percent: float) -> str:
    """ttk progressbar style name for a usage percentage."""
    if percent >= USAGE_HIGH_PCT:
        level = "High"
    elif percent >= USAGE_MID_PCT:
        level = "Mid"
    else:
        level = "Low"
    return f"{level}.Usage.Horizontal.TProgressbar"


def apply_theme(root: tk.Tk) -> None:
    """Dark theme built on the stdlib 'clam' theme: one shared background,
    thin-border cards, accent switch button, color-graded usage bars."""
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
        troughcolor=p["trough"],
        focuscolor=p["accent"],
    )
    style.configure("Muted.TLabel", foreground=p["muted"])
    style.configure("Card.TFrame", relief="solid", borderwidth=1)
    style.configure("TButton", padding=(10, 4))
    style.map(
        "TButton", background=[("pressed", p["trough"]), ("active", p["hover"])]
    )
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
    style.configure(
        "TCheckbutton",
        indicatorbackground=p["trough"],
        indicatorforeground=p["text"],
    )
    style.map("TCheckbutton", background=[("active", p["bg"])])
    for level, color in USAGE_BAR_COLORS:
        style.configure(
            f"{level}.Usage.Horizontal.TProgressbar",
            thickness=12,
            background=color,
            bordercolor=p["trough"],
            lightcolor=color,
            darkcolor=color,
        )


def find_cswap() -> str:
    path = shutil.which("cswap") or shutil.which(
        "cswap", path=os.path.expanduser("~/.local/bin")
    )
    if path is None:
        raise FileNotFoundError("cswap not found; run: uv tool install claude-swap")
    return path


def run_cswap(*args: str) -> str:
    result = subprocess.run(
        [find_cswap(), *args], capture_output=True, text=True, timeout=120
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise RuntimeError(output or f"cswap {' '.join(args)} failed")
    return output


def run_cswap_json(*args: str) -> str:
    """Run cswap with --json; return stdout only so stderr noise
    (upgrade notices, warnings) can't corrupt the JSON payload."""
    result = subprocess.run(
        [find_cswap(), *args, "--json"], capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        message = (result.stderr + result.stdout).strip()
        raise RuntimeError(message or f"cswap {' '.join(args)} failed")
    return result.stdout


def _parse_window(window: dict) -> dict:
    return {
        "percent": window["pct"],
        "reset": window.get("clock"),
        "remaining": window.get("countdown"),
    }


def parse_accounts(json_text: str) -> list[dict]:
    """Parse `cswap --list --json` output into account dicts for display.

    Usage keys are display labels ("5h", "7d", then scoped names like
    "Fable") in that order. Accounts with a non-"ok" usageStatus carry an
    empty usage dict; credential problems are flagged via "stale".
    """
    data = json.loads(json_text)
    version = data.get("schemaVersion")
    if version != 1:
        raise ValueError(f"不支持的 cswap JSON schemaVersion: {version}")
    accounts: list[dict] = []
    for row in data["accounts"]:
        raw_usage = row.get("usage") or {}
        usage: dict[str, dict] = {}
        for key, label in BASE_WINDOWS:
            if key in raw_usage:
                usage[label] = _parse_window(raw_usage[key])
        for scoped in raw_usage.get("scoped", []):
            usage[scoped["name"]] = _parse_window(scoped)
        accounts.append(
            {
                "slot": str(row["number"]),
                "email": row["email"],
                "active": row["active"],
                "status": row["usageStatus"],
                "stale": row["usageStatus"] in STALE_STATUSES,
                "age_seconds": row.get("usageAgeSeconds"),
                "usage": usage,
            }
        )
    return accounts


def merge_last_good(accounts: list[dict], cache: dict, now: float) -> list[dict]:
    """Session-memory fallback: keep showing the last good usage of an
    account whose current status is not "ok" (token expired, re-login
    needed, fetch failure), with its age accumulated so the staleness
    note stays honest. In-memory only — nothing is written to disk."""
    for account in accounts:
        email = account["email"]
        if account["usage"]:
            cache[email] = {
                "usage": account["usage"],
                "age_seconds": account["age_seconds"] or 0.0,
                "at": now,
            }
        elif email in cache:
            saved = cache[email]
            account["usage"] = saved["usage"]
            account["age_seconds"] = saved["age_seconds"] + (now - saved["at"])
    return accounts


def format_age(seconds: float | None) -> str | None:
    """Human-readable age of a usage measurement; None when fresh enough."""
    if seconds is None or seconds < AGE_NOTE_THRESHOLD_S:
        return None
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


class CswapGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Claude 账号切换")
        root.minsize(460, 220)

        apply_theme(root)

        base_font = tkfont.nametofont("TkDefaultFont")
        self.title_font = base_font.copy()
        self.title_font.configure(weight="bold", size=base_font.actual("size") + 1)

        self.accounts_frame = ttk.Frame(root)
        self.accounts_frame.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        button_row = ttk.Frame(root)
        button_row.pack(fill="x", padx=12, pady=8)
        ttk.Button(button_row, text="刷新", command=self.refresh).pack(side="left")
        ttk.Button(button_row, text="添加当前登录账号", command=self.add_account).pack(
            side="left", padx=6
        )
        self.auto_refresh_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            button_row,
            text="每分钟自动刷新",
            variable=self.auto_refresh_var,
            command=self._toggle_auto_refresh,
        ).pack(side="left", padx=6)
        self.upgrade_button = ttk.Button(
            button_row, text="升级 cswap", command=self.upgrade
        )
        self.upgrade_button.pack(side="right")
        self._upgrade_running = False
        self._upgrade_seconds = 0
        self._refreshing = False
        self._auto_job: str | None = None
        self._last_good: dict[str, dict] = {}

        self.message_var = tk.StringVar(value="加载中…")
        ttk.Label(root, textvariable=self.message_var, style="Muted.TLabel").pack(
            anchor="w", padx=12, pady=(0, 8)
        )

        self.refresh()
        self._toggle_auto_refresh()

    def run_async(self, work, on_done, on_error=None, notify: bool = True) -> None:
        def task() -> None:
            try:
                result = work()
            except Exception as error:
                message = str(error)

                def handle() -> None:
                    if on_error is not None:
                        on_error(message)
                    if notify:
                        messagebox.showerror("出错", message)

                self.root.after(0, handle)
                return
            self.root.after(0, lambda: on_done(result))

        threading.Thread(target=task, daemon=True).start()

    def refresh(self, auto: bool = False) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self.message_var.set("刷新中…")
        self.run_async(
            lambda: parse_accounts(run_cswap_json("--list")),
            self._on_refresh_done,
            on_error=self._on_refresh_error,
            notify=not auto,
        )

    def _on_refresh_done(self, accounts: list[dict]) -> None:
        self._refreshing = False
        self.show_accounts(merge_last_good(accounts, self._last_good, time.time()))

    def _on_refresh_error(self, message: str) -> None:
        self._refreshing = False
        self.message_var.set(f"刷新失败：{message.splitlines()[0][:80]}")

    def _toggle_auto_refresh(self) -> None:
        if self.auto_refresh_var.get():
            if self._auto_job is None:
                self._auto_job = self.root.after(
                    AUTO_REFRESH_INTERVAL_MS, self._auto_tick
                )
        elif self._auto_job is not None:
            self.root.after_cancel(self._auto_job)
            self._auto_job = None

    def _auto_tick(self) -> None:
        self._auto_job = None
        if not self.auto_refresh_var.get():
            return
        self.refresh(auto=True)
        self._auto_job = self.root.after(AUTO_REFRESH_INTERVAL_MS, self._auto_tick)

    def show_accounts(self, accounts: list[dict]) -> None:
        for child in self.accounts_frame.winfo_children():
            child.destroy()

        if not accounts:
            ttk.Label(
                self.accounts_frame,
                justify="left",
                style="Muted.TLabel",
                text=(
                    "尚未添加任何账号。\n\n"
                    "1. 在终端运行 claude，用 /login 登录目标账号\n"
                    "2. 点击下方「添加当前登录账号」\n\n"
                    "多账号：换号登录后重复以上步骤。"
                ),
            ).pack(anchor="w", pady=12)

        for account in accounts:
            card = ttk.Frame(self.accounts_frame, padding=(12, 8), style="Card.TFrame")
            card.pack(fill="x", pady=6)

            header = ttk.Frame(card)
            header.pack(fill="x")
            title = f"{account['slot']}. {account['email']}"
            if account["active"]:
                title += "（当前）"
            stale = account["stale"] and not account["active"]
            if stale:
                title += " ⚠ 凭据失效"
            ttk.Label(
                header,
                text=title,
                font=self.title_font,
                foreground=STALE_FG if stale else "",
            ).pack(side="left")
            switch_button = ttk.Button(
                header,
                text="切换（需先修复）" if stale else "切换到此账号",
                style="Accent.TButton",
                command=lambda account=account: self.switch_to(account),
            )
            if account["active"]:
                switch_button.state(["disabled"])
            switch_button.pack(side="right")

            if account["status"] != "ok":
                note = STATUS_NOTES.get(
                    account["status"], f"暂无数据（{account['status']}）"
                )
                note_label = ttk.Label(card, text=note, style="Muted.TLabel")
                if account["stale"]:
                    note_label.configure(foreground=STALE_FG)
                note_label.pack(anchor="w")

            if not account["usage"]:
                continue

            age = format_age(account["age_seconds"])
            if age is not None:
                ttk.Label(
                    card, text=f"用量为 {age} 前数据", style="Muted.TLabel"
                ).pack(anchor="w")

            for window, usage in account["usage"].items():
                row = ttk.Frame(card)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text=window, width=6).pack(side="left")
                bar = ttk.Progressbar(
                    row,
                    style=usage_style(usage["percent"]),
                    maximum=100,
                    value=usage["percent"],
                    length=140,
                )
                bar.pack(side="left", fill="x", expand=True, padx=(2, 6))
                detail = f"{usage['percent']:3.0f}%"
                if usage["reset"] is not None:
                    detail += f"  重置 {usage['reset']}（剩 {usage['remaining']}）"
                ttk.Label(row, text=detail, style="Muted.TLabel").pack(side="left")

        self.message_var.set(
            f"共 {len(accounts)} 个账号 · {time.strftime('%H:%M:%S')} 更新"
        )

    def switch_to(self, account: dict) -> None:
        slot = account["slot"]
        if account["stale"]:
            proceed = messagebox.askyesno(
                "凭据已失效",
                f"账号 {slot}（{account['email']}）的存储凭据已失效，\n"
                "切换过去后 Claude Code 会报 401 授权错误。\n\n"
                "正确做法：先在 Claude CLI 用该账号 /login 登录，\n"
                "再运行 cswap --add-account 刷新凭据。\n\n"
                "仍要强行切换吗？",
                icon="warning",
                default="no",
            )
            if not proceed:
                self.message_var.set("已取消切换")
                return
        self.message_var.set(f"正在切换到账号 {slot}…")
        self.run_async(
            lambda: run_cswap("--switch-to", slot),
            lambda output: (self.message_var.set(output), self.refresh()),
        )

    def add_account(self) -> None:
        self.message_var.set("正在添加当前登录的账号…")
        self.run_async(
            lambda: run_cswap("--add-account"),
            lambda output: (self.message_var.set(output), self.refresh()),
        )

    def upgrade(self) -> None:
        if self._upgrade_running:
            return
        self._upgrade_running = True
        self._upgrade_seconds = 0
        self.upgrade_button.state(["disabled"])
        self._tick_upgrade()
        self.run_async(
            lambda: run_cswap("--upgrade"),
            self._on_upgrade_done,
            self._on_upgrade_error,
        )

    def _tick_upgrade(self) -> None:
        if not self._upgrade_running:
            return
        self.message_var.set(
            f"正在升级 claude-swap…（已用 {self._upgrade_seconds} 秒，正在联网下载，请稍候）"
        )
        self._upgrade_seconds += 1
        self.root.after(1000, self._tick_upgrade)

    def _finish_upgrade(self) -> None:
        self._upgrade_running = False
        self.upgrade_button.state(["!disabled"])

    def _on_upgrade_done(self, output: str) -> None:
        self._finish_upgrade()
        self.message_var.set("升级完成")
        messagebox.showinfo("升级结果", output or "已是最新版本，无需升级。")

    def _on_upgrade_error(self, message: str) -> None:
        self._finish_upgrade()
        self.message_var.set("升级失败")


def main() -> None:
    root = tk.Tk()
    CswapGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
