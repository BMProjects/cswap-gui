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
                f"{plat.DEFAULT_PROFILE_DIR} not found. Start Claude Desktop normally once first."
            )
        return _default_profile()

    directory = plat.profile_dir(name)
    if not directory.is_dir():
        raise CdpError(
            f"No profile named {name!r}. Run 'cdp list' to see them, or 'cdp add' to create one."
        )
    return Profile(
        name=name, directory=directory, color=read_color(directory), is_default=False
    )


def list_profiles() -> list[Profile]:
    """The system-installed profile first, then the ones cdp created."""
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
            f"{DEFAULT_NAME!r} is the system's own Claude Desktop profile, managed by the "
            f"installation itself. It cannot be {action}."
        )


def _require_claude() -> None:
    if not plat.claude_available():
        raise CdpError(
            f"{plat.CLAUDE_BIN} not found. Install Claude Desktop, or point CDP_CLAUDE_BIN "
            "at the executable."
        )


def add_profile(name: str, color: str = DEFAULT_COLOR) -> Profile:
    name = name.strip()
    if not name:
        raise CdpError("The name cannot be empty.")
    if is_default_name(name):
        raise CdpError(f"{DEFAULT_NAME!r} is a reserved name. Please choose another.")
    if not slugify(name):
        raise CdpError(
            f"The name {name!r} cannot be turned into a valid identifier. Use letters or digits."
        )
    resolve_color(color)
    _require_claude()

    directory = plat.profile_dir(name)
    if directory.is_dir():
        raise CdpError(f"A profile named {name!r} already exists.")

    directory.mkdir(parents=True)
    profile = Profile(name=name, directory=directory, color=color, is_default=False)
    _write_desktop_integration(profile)
    return profile


def set_color(name: str, color: str) -> Profile:
    profile = find_profile(name)
    _reject_default(profile, "recoloured (it uses the official icon)")
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
    """Launch a profile. Returns (profile, whether it was already running)."""
    profile = find_profile(name)
    _require_claude()
    already = plat.is_running(profile)
    extra = [] if profile.is_default else plat.launch_extra_args(profile)
    plat.spawn(launch_argv(plat.CLAUDE_BIN, profile, extra))
    return profile, already


def remove_profile(name: str, purge: bool = False) -> tuple[Profile, bool]:
    """Remove the launcher and icon; also delete the data directory when purge is set.

    The caller is responsible for confirming with the user before purging —
    the data is unrecoverable.
    """
    profile = find_profile(name)
    _reject_default(profile, "removed")
    if plat.is_running(profile):
        raise CdpError(f"Profile {name!r} is running. Quit it before removing.")

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
