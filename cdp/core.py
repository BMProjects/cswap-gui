"""跨平台核心：profile 的数据模型、配色元数据与启动命令拼装。

本模块不涉及任何平台设施——不生成启动器、不画图标、不查进程。
那些都在 platform_* 模块里，移植到其他系统时只需替换那一层。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

COLORS: dict[str, str] = {
    "orange": "#D97757",
    "red": "#C6483C",
    "yellow": "#D9A441",
    "green": "#4C9A5A",
    "teal": "#3F8F8A",
    "blue": "#3D74D9",
    "purple": "#7A5AA8",
    "pink": "#C05B87",
}
DEFAULT_COLOR = "orange"

# 系统已安装的 Claude Desktop 本身在列表中的名字。它不由 cdp 创建，
# 也不会被复制，只是纳入统一管理；名称匹配对大小写不敏感。
DEFAULT_NAME = "Default"
SYSTEM_COLOR = "system"

PROFILE_PREFIX = "Claude-"
COLOR_FILE = ".cdp-color"


class CdpError(Exception):
    """An expected, user-readable error: printed by the CLI, shown in the TUI status line."""


@dataclass(frozen=True)
class Profile:
    name: str
    directory: Path
    color: str
    is_default: bool

    @property
    def slug(self) -> str:
        return slugify(self.name)


@dataclass(frozen=True)
class ProfileStatus:
    """A profile plus the state that has to be probed live, for list display."""

    profile: Profile
    running: bool
    size: str
    has_launcher: bool

    @property
    def name(self) -> str:
        return self.profile.name

    @property
    def color(self) -> str:
        return self.profile.color

    @property
    def is_default(self) -> bool:
        return self.profile.is_default


def slugify(name: str) -> str:
    """Name to a filename-safe identifier. An empty result means the name is unusable."""
    kept = [c if c.isascii() and c.isalnum() else "-" for c in name.lower()]
    return "-".join(part for part in "".join(kept).split("-") if part)


def is_default_name(name: str) -> bool:
    return name.strip().lower() == DEFAULT_NAME.lower()


def resolve_color(color: str) -> str:
    if color not in COLORS:
        raise CdpError(f"Unknown colour {color!r}. Available: {' '.join(COLORS)}")
    return COLORS[color]


def read_color(directory: Path) -> str:
    try:
        color = (directory / COLOR_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_COLOR
    return color if color in COLORS else DEFAULT_COLOR


def write_color(directory: Path, color: str) -> None:
    (directory / COLOR_FILE).write_text(color + "\n", encoding="utf-8")


def launch_argv(
    binary: str, profile: Profile, extra: list[str] | None = None
) -> list[str]:
    """Full command line for launching a profile.

    The system-installed profile is deliberately launched with no arguments at
    all: only then does its process signature match the official launcher, which
    is what makes the claude:// login callback (whose handler likewise carries no
    --user-data-dir) land on it.
    """
    if profile.is_default:
        return [binary]
    return [binary, f"--user-data-dir={profile.directory}", *(extra or [])]


def human_size(total_bytes: int) -> str:
    size = float(total_bytes)
    for unit in ("B", "K", "M", "G"):
        if size < 1024 or unit == "G":
            return f"{size:.0f}{unit}" if unit != "B" else f"{size:.0f}B"
        size /= 1024
    return f"{size:.0f}G"


def directory_size(directory: Path) -> int:
    total = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total
