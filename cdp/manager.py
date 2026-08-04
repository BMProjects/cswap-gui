"""操作层：CLI 与 TUI 共用的全部业务动作。

界面只负责收集意图与呈现结果，规则与守卫都在这里，两个前端因此不会跑偏。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from cdp import platform_linux as plat
from cdp.core import (
    COLORS,
    DEFAULT_COLOR,
    DEFAULT_NAME,
    SYSTEM_COLOR,
    CdpError,
    Profile,
    ProfileStatus,
    directory_size,
    human_size,
    is_default_name,
    launch_argv,
    read_color,
    resolve_color,
    slugify,
    write_color,
)


def _default_profile() -> Profile:
    return Profile(
        name=DEFAULT_NAME,
        directory=plat.DEFAULT_PROFILE_DIR,
        color=SYSTEM_COLOR,
        is_default=True,
    )


def find_profile(name: str) -> Profile:
    if is_default_name(name):
        if not plat.default_profile_exists():
            raise CdpError(
                f"找不到 {plat.DEFAULT_PROFILE_DIR}，请先正常启动一次 Claude Desktop。"
            )
        return _default_profile()

    directory = plat.profile_dir(name)
    if not directory.is_dir():
        raise CdpError(f"profile「{name}」不存在。用 cdp list 查看，或 cdp add 创建。")
    return Profile(
        name=name, directory=directory, color=read_color(directory), is_default=False
    )


def list_profiles() -> list[Profile]:
    """系统自带的排在最前，其后是 cdp 建的。"""
    profiles: list[Profile] = []
    if plat.default_profile_exists():
        profiles.append(_default_profile())
    for name in plat.managed_profile_names():
        directory = plat.profile_dir(name)
        profiles.append(
            Profile(
                name=name,
                directory=directory,
                color=read_color(directory),
                is_default=False,
            )
        )
    return profiles


def list_status(with_size: bool = True) -> list[ProfileStatus]:
    running_dirs = plat.running_profile_dirs()
    default_running = plat.default_profile_running()
    result = []
    for profile in list_profiles():
        running = (
            default_running
            if profile.is_default
            else str(profile.directory) in running_dirs
        )
        size = human_size(directory_size(profile.directory)) if with_size else "—"
        result.append(
            ProfileStatus(
                profile=profile,
                running=running,
                size=size,
                has_launcher=plat.has_launcher(profile),
            )
        )
    return result


def _reject_default(profile: Profile, action: str) -> None:
    if profile.is_default:
        raise CdpError(
            f"「{DEFAULT_NAME}」是系统自带的 Claude Desktop 配置，"
            f"由安装本身管理，不能{action}。"
        )


def _require_claude() -> None:
    if not plat.claude_available():
        raise CdpError(
            f"找不到 {plat.CLAUDE_BIN}。请先安装 Claude Desktop，"
            "或设置 CDP_CLAUDE_BIN 指向可执行文件。"
        )


def add_profile(name: str, color: str = DEFAULT_COLOR) -> Profile:
    name = name.strip()
    if not name:
        raise CdpError("名称不能为空。")
    if is_default_name(name):
        raise CdpError(f"「{DEFAULT_NAME}」是保留名称，请换一个。")
    if not slugify(name):
        raise CdpError(f"名称「{name}」无法转成合法标识，请改用字母或数字。")
    resolve_color(color)
    _require_claude()

    directory = plat.profile_dir(name)
    if directory.is_dir():
        raise CdpError(f"profile「{name}」已存在。")

    directory.mkdir(parents=True)
    profile = Profile(name=name, directory=directory, color=color, is_default=False)
    _write_desktop_integration(profile)
    return profile


def set_color(name: str, color: str) -> Profile:
    profile = find_profile(name)
    _reject_default(profile, "改配色（它用的是官方图标）")
    resolve_color(color)
    updated = Profile(
        name=profile.name,
        directory=profile.directory,
        color=color,
        is_default=False,
    )
    _write_desktop_integration(updated)
    return updated


def _write_desktop_integration(profile: Profile) -> None:
    write_color(profile.directory, profile.color)
    plat.write_icon(profile.slug, resolve_color(profile.color))
    plat.write_launcher(profile)
    plat.refresh_desktop_db()


def launch(name: str) -> tuple[Profile, bool]:
    """启动 profile，返回 (profile, 启动前是否已在运行)。"""
    profile = find_profile(name)
    _require_claude()
    already = plat.is_running(profile)
    extra = [] if profile.is_default else plat.launch_extra_args(profile)
    plat.spawn(launch_argv(plat.CLAUDE_BIN, profile, extra))
    return profile, already


def remove_profile(name: str, purge: bool = False) -> tuple[Profile, bool]:
    """移除启动器与图标；purge 为真时连数据目录一并删除。

    调用方负责在 purge 前向用户确认——数据不可恢复。
    """
    profile = find_profile(name)
    _reject_default(profile, "移除")
    if plat.is_running(profile):
        raise CdpError(f"profile「{name}」正在运行，请先退出再移除。")

    plat.remove_launcher(profile.slug)
    plat.refresh_desktop_db()
    if purge:
        shutil.rmtree(profile.directory, ignore_errors=True)
    return profile, purge


def prune_shortcuts() -> tuple[int, int]:
    try:
        return plat.prune_kde_shortcuts()
    except OSError as error:
        raise CdpError(str(error)) from error


def color_names() -> list[str]:
    return list(COLORS)


def default_profile_path() -> Path:
    return plat.DEFAULT_PROFILE_DIR
