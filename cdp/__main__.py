"""cdp command-line entry point. With no subcommand it opens the TUI."""

from __future__ import annotations

import argparse
import sys

from cdp import manager
from cdp.core import DEFAULT_NAME, CdpError

EPILOG = f"""\
"{DEFAULT_NAME}" is the Claude Desktop installation you already have. It appears in
the list automatically and can be launched, but not recoloured or removed -- it is
managed by the installation itself and cdp never modifies it. The claude:// login
callback is always handled by it, so keep using it for the account you are already
signed in with.

Profiles created by cdp store their data separately and share no login state,
settings or MCP connectors; sign in to a new account on its first launch.

Running cdp with no arguments opens the interactive interface.
"""


def _print_table(rows: list[manager.ProfileStatus]) -> None:
    if not rows:
        print(
            "No Claude Desktop configuration found. Start Claude Desktop normally once first."
        )
        return
    # ASCII headers only: display width and byte count differ for wide characters.
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
    print(f"Created profile {profile.name!r} ({profile.color})")
    print(f"  Data directory: {profile.directory}")
    print(
        f"  Launch        : cdp launch {profile.name}  (or search the app menu for Claude - {profile.name})"
    )
    print("  Next          : sign in to another account on its first launch")
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    profile, already = manager.launch(args.name)
    if already:
        print(
            f"{profile.name!r} is already running; Electron will focus its existing window."
        )
    print(f"Launched {profile.name!r}")
    return 0


def cmd_color(args: argparse.Namespace) -> int:
    profile = manager.set_color(args.name, args.color)
    print(f"Profile {profile.name!r} recoloured to {profile.color}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    if args.purge and sys.stdin.isatty():
        target = manager.find_profile(args.name).directory
        reply = input(
            f"Delete the data directory {target}? Login state and chat history are unrecoverable. [y/N] "
        )
        if not reply.strip().lower().startswith("y"):
            print("Cancelled.")
            return 0
    profile, purged = manager.remove_profile(args.name, purge=args.purge)
    print("Launcher and icon removed.")
    if purged:
        print(f"Deleted data directory {profile.directory}")
    else:
        print(
            f"Data directory kept at {profile.directory}  (add --purge to delete it too)"
        )
    return 0


def cmd_prune(_args: argparse.Namespace) -> int:
    removed, kept = manager.prune_shortcuts()
    print(
        f"Removed {removed} stale Claude global-shortcut entries, kept {kept} live one(s)."
    )
    if removed:
        print(
            "Note: System Settings fully reflects this after you log out and back in."
        )
    return 0


def cmd_tui(_args: argparse.Namespace) -> int:
    from cdp.tui import run

    return run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cdp",
        description="Claude Desktop Profiles - run multiple Claude Desktop accounts side by side on Linux",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subs = parser.add_subparsers(dest="command")

    p_list = subs.add_parser("list", aliases=["ls"], help="list every profile")
    p_list.add_argument(
        "--porcelain", action="store_true", help="machine-readable tab-separated output"
    )
    p_list.add_argument(
        "--no-size", action="store_true", help="skip disk-usage measurement (faster)"
    )
    p_list.set_defaults(func=cmd_list)

    p_add = subs.add_parser(
        "add", help="create an empty profile and its application-menu launcher"
    )
    p_add.add_argument("name")
    p_add.add_argument(
        "--color", default="orange", help=" / ".join(manager.color_names())
    )
    p_add.set_defaults(func=cmd_add)

    p_launch = subs.add_parser(
        "launch",
        aliases=["run"],
        help="launch a profile (focuses it if already running)",
    )
    p_launch.add_argument("name")
    p_launch.set_defaults(func=cmd_launch)

    p_color = subs.add_parser("color", help="change the colour and icon")
    p_color.add_argument("name")
    p_color.add_argument("color", help=" / ".join(manager.color_names()))
    p_color.set_defaults(func=cmd_color)

    p_remove = subs.add_parser(
        "remove",
        aliases=["rm"],
        help="remove the launcher; --purge deletes the data too",
    )
    p_remove.add_argument("name")
    p_remove.add_argument(
        "--purge",
        action="store_true",
        help="also delete the data directory (unrecoverable)",
    )
    p_remove.set_defaults(func=cmd_remove)

    p_prune = subs.add_parser(
        "prune-shortcuts", help="clean up stale Claude global shortcuts in KDE"
    )
    p_prune.set_defaults(func=cmd_prune)

    p_tui = subs.add_parser(
        "tui",
        help="open the interactive interface (same as running cdp with no arguments)",
    )
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
