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
    """Names of cdp-created profiles (excluding the system one), sorted by name."""
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
    """--class gives each profile its own WM_CLASS so taskbars group them separately."""
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
    """Command lines of Electron processes matched exactly by process name.

    pgrep -x (match on process name) is required: chrome_crashpad_handler also
    has "claude-desktop" in its path, so -f would sweep it up along with any
    other process that happens to mention the word on its command line.
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
    """A main process started without --user-data-dir is the system profile.

    Renderer, GPU and other helpers carry --type=; only main processes count.
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
        f"Comment=Claude Desktop ({profile.name} profile)\n"
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
    """Start detached, so the app keeps running after the parent exits."""
    subprocess.Popen(
        argv,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def prune_kde_shortcuts() -> tuple[int, int]:
    """Drop stale Claude global shortcuts accumulated in KDE. Returns (removed, kept).

    Claude Desktop unconditionally registers Ctrl+Alt+Space on startup (a default
    hard-coded in the app; it is never written into the profile directory, so it
    cannot be disabled up front). Every instance re-registers it, but the key is
    already held by the first one, so later instances fail to bind and leave an
    inert entry behind — which is what raises the conflict prompt in System
    Settings. Deleting a profile does not clean these up either.

    Entry format: `<hash>-<key>=<active>,<default>,<description>`. An empty first
    field means unbound; removing those leaves the one actually in use untouched.
    """
    if not KDE_SHORTCUTS.is_file():
        raise OSError(f"{KDE_SHORTCUTS} not found (not a KDE desktop?)")
    writer = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    if writer is None:
        raise OSError(
            "kwriteconfig6/5 not found; cannot safely modify the KDE configuration"
        )

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
