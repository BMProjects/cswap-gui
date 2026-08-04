"""Linux 平台集成：XDG 路径、.desktop 启动器、hicolor 图标、进程检测、KDE 快捷键。

移植到 macOS / Windows 时替换本模块即可，core 与界面层不必改动。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from cdp.core import PROFILE_PREFIX, Profile

CLAUDE_BIN = os.environ.get("CDP_CLAUDE_BIN", "claude-desktop")

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
APP_DIR = DATA_HOME / "applications"
ICON_DIR = DATA_HOME / "icons/hicolor/scalable/apps"

DEFAULT_PROFILE_DIR = CONFIG_HOME / "Claude"
DEFAULT_DESKTOP = "com.anthropic.Claude.desktop"
SYSTEM_APP_DIR = Path("/usr/share/applications")

KDE_SHORTCUTS = CONFIG_HOME / "kglobalshortcutsrc"
CLAUDE_SHORTCUT_GROUP = "com.anthropic.Claude"


def claude_available() -> bool:
    return shutil.which(CLAUDE_BIN) is not None


def profile_dir(name: str) -> Path:
    return CONFIG_HOME / f"{PROFILE_PREFIX}{name}"


def managed_profile_names() -> list[str]:
    """cdp 建的 profile 名（不含系统自带的那个），按名称排序。"""
    names = [
        entry.name[len(PROFILE_PREFIX) :]
        for entry in CONFIG_HOME.glob(f"{PROFILE_PREFIX}*")
        if entry.is_dir()
    ]
    return sorted(names, key=str.lower)


def default_profile_exists() -> bool:
    return DEFAULT_PROFILE_DIR.is_dir()


def wm_class(slug: str) -> str:
    return f"claude-profile-{slug}"


def launch_extra_args(profile: Profile) -> list[str]:
    """--class 让每个 profile 拿到独立 WM_CLASS，任务栏得以分开归组。"""
    return [f"--class={wm_class(profile.slug)}"]


def desktop_file(slug: str) -> Path:
    return APP_DIR / f"claude-profile-{slug}.desktop"


def icon_file(slug: str) -> Path:
    return ICON_DIR / f"claude-profile-{slug}.svg"


def has_launcher(profile: Profile) -> bool:
    if profile.is_default:
        return (SYSTEM_APP_DIR / DEFAULT_DESKTOP).is_file() or (
            APP_DIR / DEFAULT_DESKTOP
        ).is_file()
    return desktop_file(profile.slug).is_file()


def _app_processes() -> list[str]:
    """进程名精确匹配的 Electron 进程命令行。

    必须用 pgrep -x 按进程名匹配：chrome_crashpad_handler 的路径里同样含
    "claude-desktop"，用 -f 会把它连同命令行里出现该词的任意进程一起算进来。
    """
    try:
        result = subprocess.run(
            ["pgrep", "-ax", Path(CLAUDE_BIN).name],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def running_profile_dirs() -> set[str]:
    return {
        arg.split("=", 1)[1]
        for line in _app_processes()
        for arg in line.split()
        if arg.startswith("--user-data-dir=")
    }


def default_profile_running() -> bool:
    """未带 --user-data-dir 启动的主进程即系统自带的那个。

    渲染、GPU 等子进程带 --type=，只看主进程。
    """
    return any(
        "--type=" not in line and "--user-data-dir=" not in line
        for line in _app_processes()
    )


def is_running(profile: Profile) -> bool:
    if profile.is_default:
        return default_profile_running()
    return str(profile.directory) in running_profile_dirs()


def _icon_svg(hex_color: str) -> str:
    rays = "\n".join(
        f'    <rect x="60" y="22" width="8" height="30" rx="4" '
        f'transform="rotate({i * 45} 64 64)"/>'
        for i in range(8)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" '
        'viewBox="0 0 128 128">\n'
        f'  <rect x="4" y="4" width="120" height="120" rx="28" fill="{hex_color}"/>\n'
        '  <g fill="#FFFFFF">\n'
        f"{rays}\n"
        '    <circle cx="64" cy="64" r="9"/>\n'
        "  </g>\n"
        "</svg>\n"
    )


def write_icon(slug: str, hex_color: str) -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    icon_file(slug).write_text(_icon_svg(hex_color), encoding="utf-8")


def write_launcher(profile: Profile) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    slug = profile.slug
    exec_line = " ".join(
        [
            CLAUDE_BIN,
            f"--user-data-dir={profile.directory}",
            *launch_extra_args(profile),
        ]
    )
    desktop_file(slug).write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name=Claude — {profile.name}\n"
        f"Comment=Claude Desktop（{profile.name} 账号配置）\n"
        f"Exec={exec_line} %U\n"
        f"Icon=claude-profile-{slug}\n"
        "StartupNotify=true\n"
        f"StartupWMClass={wm_class(slug)}\n"
        "SingleMainWindow=true\n"
        "Categories=Utility;\n"
        f"Keywords=claude;profile;{slug};\n",
        encoding="utf-8",
    )


def remove_launcher(slug: str) -> None:
    desktop_file(slug).unlink(missing_ok=True)
    icon_file(slug).unlink(missing_ok=True)


def refresh_desktop_db() -> None:
    if shutil.which("update-desktop-database"):
        subprocess.run(
            ["update-desktop-database", str(APP_DIR)],
            capture_output=True,
            check=False,
        )


def spawn(argv: list[str]) -> None:
    """脱离当前终端启动，父进程退出后应用继续运行。"""
    subprocess.Popen(
        argv,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def prune_kde_shortcuts() -> tuple[int, int]:
    """清理 KDE 中堆积的失效 Claude 全局快捷键，返回 (已删, 保留)。

    Claude Desktop 启动时无条件注册 Ctrl+Alt+Space（应用内硬编码的默认值，
    不写入 profile 也就无法预先关闭）。每个实例都是一次新注册，而该键已被
    首个实例占用，后来者绑定失败，只留下一条「生效键为空」的惰性条目并弹出
    系统设置的冲突提示；profile 删除后这些条目也不会自动消失。

    条目格式 `<hash>-<键>=<生效键>,<默认键>,<说明>`，第一段为空即未绑定，
    删掉不影响真正生效的那条。
    """
    if not KDE_SHORTCUTS.is_file():
        raise OSError(f"找不到 {KDE_SHORTCUTS}（非 KDE 桌面？）")
    writer = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    if writer is None:
        raise OSError("找不到 kwriteconfig6/5，无法安全修改 KDE 配置")

    removed = kept = 0
    in_group = False
    for raw in KDE_SHORTCUTS.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_group = line == f"[{CLAUDE_SHORTCUT_GROUP}]"
            continue
        if not in_group or "=" not in line or line.startswith("_k_"):
            continue
        key, value = line.split("=", 1)
        if value.split(",", 1)[0]:
            kept += 1
            continue
        subprocess.run(
            [
                writer,
                "--file",
                KDE_SHORTCUTS.name,
                "--group",
                CLAUDE_SHORTCUT_GROUP,
                "--key",
                key,
                "--delete",
            ],
            capture_output=True,
            check=False,
        )
        removed += 1
    return removed, kept
