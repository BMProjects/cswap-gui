# Claude Desktop Profiles for Linux

Run multiple Claude Desktop accounts side by side on Linux. Each profile keeps its
own login, chat history, settings, and MCP connectors — open them at the same time
without interference.

Pure stdlib Python: one CLI plus a curses interface. No dependencies to install,
no Electron wrapper, no telemetry.

> Inspired by [odahcam/claude-desktop-profiles](https://github.com/odahcam/claude-desktop-profiles),
> which solves the same problem beautifully on macOS. See [Credits](#credits).

## How it works

Claude Desktop is an Electron app, so it honours Chromium's `--user-data-dir`.
A profile is simply an isolated data directory:

```
~/.config/Claude-Work/       # Cookies, Local Storage, config.json and
~/.config/Claude-Personal/   # claude_desktop_config.json are all separate
```

Electron's single-instance lock is scoped per `--user-data-dir`, which gives us:

- Launching the same profile twice → focuses the existing window, no second instance
- Different profiles → independent processes that run concurrently

`--class` gives each profile its own `WM_CLASS`, which together with
`StartupWMClass` in the `.desktop` file makes taskbars and docks group each
profile's windows separately.

## Install

You need Claude Desktop and Python 3.10+ (shipped by every current distro).
**No third-party dependencies — no `python3-tk`, no pip, no npm.**

```bash
git clone https://github.com/BMProjects/claude-desktop-profiles-linux.git
cd claude-desktop-profiles-linux
./install.sh
```

The script symlinks `cdp` into `~/.local/bin` and adds the interactive interface
to your application menu. It symlinks rather than copies, so pulling updates takes
effect immediately.

## Usage

```bash
cdp list                       # name / colour / running state / disk usage / launcher
cdp add Work --color blue      # create an empty profile, then sign in on first launch
cdp launch Work                # launch (focuses the window if already running)
cdp color Work purple          # change colour and icon
cdp remove Work                # remove the launcher, keep the data
cdp remove Work --purge        # also delete the data directory (asks to confirm)
cdp                            # no arguments opens the interactive interface
```

Colours: `orange` `red` `yellow` `green` `teal` `blue` `purple` `pink`

Once created, a profile can be started straight from the application menu by
searching for "Claude — Work" — no terminal needed.

### "Default" — the Claude Desktop you already have

The first entry in the list, `Default`, is the system's existing Claude Desktop
installation (`~/.config/Claude`). It is **not created by cdp and never copied
anywhere** — it is simply adopted into the list:

- Launch it with `cdp launch Default`, or from the official "Claude" menu entry
- **It cannot be recoloured or removed** — it belongs to the Claude Desktop
  installation, and cdp never modifies it
- It is deliberately launched *without* `--user-data-dir`, so its process
  signature matches the official launcher

**Keep using it for the account you are already signed in with.** The `claude://`
login callback is always handled by this profile (see below), which makes it the
one configuration where signing in works smoothly. Use `cdp add` for additional
accounts.

> Earlier versions had a `cdp import` command that copied `Default` into a new
> profile. It has been removed: copying leaves two directories holding credentials
> for the same account, which tends to trigger server-side re-verification, and the
> copy could not complete a login of its own because of the callback ownership
> described below. Just use `Default` as your primary account.

## Interactive interface

Run `cdp` with no arguments, or open "Claude Desktop Profiles" from the
application menu.

```
 Claude Desktop Profiles                      2 profiles · 1 running
────────────────────────────────────────────────────────────────────
 ▸ ● Default      system     running    594M
   ● work         blue                   12M
────────────────────────────────────────────────────────────────────
 Launched 'Default'
 ↑↓ select  Enter launch  c colour  d delete  a new  r refresh  ? help  q quit
```

Key hints stay pinned to the bottom, and destructive actions always ask for
confirmation with "no" as the default. Running state refreshes every 3 seconds;
disk usage is slower to compute, so it is only recalculated when you press `r`.

The interface is built on stdlib `curses`, which ships with Python itself — unlike
`tkinter`, it needs no extra system package, so it works out of the box on any
distribution. Every action is delegated to the same operations layer the CLI uses,
so the two never diverge in behaviour.

## Signing in from a new profile falls back to Default (important)

**Symptom**: you click sign-in inside a newly created profile, complete the
verification, and end up back on `Default`'s account — while the new profile is
still empty.

**Cause**: the login callback travels over the `claude://` URL scheme, and the
system handler for that scheme is the official `com.anthropic.Claude.desktop`,
whose `Exec=claude-desktop %U` carries **no `--user-data-dir`**. The callback is
therefore always claimed by `Default`, and the profile that started the login never
receives it. This is an inherent conflict between a single global URL scheme and
multiple profiles: the system has no way to know which profile initiated the flow.

This is also exactly why **the account you are already signed in with should stay
on `Default`** — it is the natural owner of the callback.

**Workaround**: point the scheme at the target profile for the duration of the
login, then restore it.

```bash
# 1. Before signing in: point claude:// at the target profile (here: apple)
xdg-mime default claude-profile-apple.desktop x-scheme-handler/claude

# 2. Launch that profile and complete the login
cdp launch apple

# 3. Restore afterwards
xdg-mime default com.anthropic.Claude.desktop x-scheme-handler/claude
```

Profile launchers already carry `%U` in their `Exec` line, so they can receive the
callback URL. To check what the scheme currently points at:

```bash
xdg-mime query default x-scheme-handler/claude
```

Once restored, everyday `claude://` links open in `Default` again.

## KDE global shortcuts pile up

After launching profiles, System Settings may show a shortcut conflict prompt, and
a pile of useless entries accumulates under "Claude". This is Claude Desktop's own
behaviour, not a side effect of the profile mechanism:

- `Ctrl+Alt+Space` (quick entry) is a **hard-coded default inside the app**. It is
  not written into the profile directory, so it cannot be disabled up front —
  seeding `quickEntryShortcut: "off"` was tested and has no effect.
- Every instance re-registers it on startup. The key is already held by the first
  instance, so later ones fail to bind and leave behind an inert entry with an
  empty binding, which is what triggers the conflict prompt.
- Deleting a profile does not remove these entries.

To clean up:

```bash
cdp prune-shortcuts     # drop every unbound stale entry, keep the live one
```

It only deletes entries whose active binding is empty, so the shortcut actually in
use is untouched. Safe to run repeatedly. System Settings fully reflects the change
after you log out and back in.

## Project layout

```
cdp/
├── core.py            Cross-platform: data model, colours, launch argv
├── platform_linux.py  Platform integration: .desktop, hicolor icons,
│                      process detection, KDE shortcuts
├── manager.py         Operations layer: CRUD plus every guard, shared by both frontends
├── __main__.py        CLI: argument parsing and text output
└── tui.py             curses interface
```

Every platform-specific detail lives in `platform_linux.py` alone, so a port to
macOS or Windows only has to replace that module — `core`, `manager`, and both
frontends stay as they are. Business rules exist solely in `manager.py`, which is
why the CLI and the interactive interface cannot drift apart.

## Known limitations

- **Windows cannot be focused externally under Wayland.** Focusing relies on
  Electron's own single-instance mechanism, which works fine; if a profile's window
  is minimised to the tray, the behaviour is up to Claude Desktop.
- **A fresh profile takes about 12 MB**, growing with chat history and cache.
- **Not sharing login state is the point, not a bug** — each profile signs in once.

## Relationship to cswap

This project manages multiple accounts for the **Claude Desktop app**. To switch
accounts in the **Claude Code CLI**, use
[claude-swap](https://github.com/realiti4/claude-swap) (`cswap`) instead. The two
are independent and can be used together.

## Credits

This project owes its design to
**[odahcam/claude-desktop-profiles](https://github.com/odahcam/claude-desktop-profiles)**
— a native SwiftUI profile manager for macOS. Thank you for working out the
approach and publishing it: the core insight that Claude Desktop's profiles can be
isolated purely through Chromium's `--user-data-dir`, along with the per-profile
colour-coded launcher model, both come from that project.

This is an independent Linux implementation of the same idea. The isolation
mechanism is identical; the platform integration is not. Where macOS needs APFS
copy-on-write clones of the app, `NSWorkspace.setIcon` for tinted icons,
LaunchServices bundle identifiers, and AppleScript applets, Linux needs none of
that — the same binary is simply launched with different arguments, and desktop
integration is a matter of writing `.desktop` files and SVG icons. That makes the
Linux side considerably simpler, which is the only reason this implementation is
as small as it is.

If you are on macOS, use the original — it is the better fit there.

## License

MIT
