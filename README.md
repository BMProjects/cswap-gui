# claude-swap GUI

A zero-dependency tkinter front-end for
[claude-swap](https://github.com/realiti4/claude-swap) (`cswap`):
switch between Claude Code subscription accounts with one click and
watch per-account usage quotas at a glance.

Everything lives in a single file, [cswap_gui.py](cswap_gui.py),
using only the Python standard library.

> Note: the interface text is currently Chinese.

## Features

- Lists all managed accounts and marks the active one
- Three usage bars per account:
  - **5h** — the 5-hour rolling window
  - **7d** — the 7-day window
  - **Fable** — the separate weekly quota for the Fable model
    (a scoped window, provided by cswap ≥ 0.17; any per-model quotas
    the upstream adds later will show up automatically, no code change)
- Each bar shows the reset time and remaining countdown; for inactive
  accounts cswap serves last-known data, and measurements older than
  15 minutes are labelled with their age
- Accounts with broken credentials (`no_credentials` / `token_expired`)
  get a ⚠ warning, and switching to them prompts to fix via `/login` +
  `cswap --add-account` first
- One-click "add current account" and "upgrade cswap"
- Auto-refresh every 60 s (on by default, checkbox to disable):
  quotas update by themselves and the status bar shows the last
  update time; auto-refresh failures only appear in the status bar
  instead of popping up dialogs
- Resilient display during token hiccups: when an account's status
  turns `token_expired` / `relogin_required` / `unavailable`, the GUI
  keeps showing the last good usage bars (with an accumulating age
  label) alongside the status note, instead of blanking out —
  a long-open window recovers by itself on the next good tick
- Handles cswap 0.19's `relogin_required` status (dead refresh token,
  account quarantined): flagged like other credential problems, with
  a hint to `/login` + `cswap --add-account`

## Dependencies

| Dependency | Install |
|------------|---------|
| Python 3.10+ with tkinter | `sudo apt install python3-tk` (Debian/Ubuntu) |
| claude-swap ≥ 0.17 | `uv tool install claude-swap` |

## Running

```sh
python3 cswap_gui.py
```

### Desktop entry (optional)

```sh
./install.sh
```

The script installs [cswap-gui.desktop](cswap-gui.desktop) (with the
`@PROJECT_DIR@` placeholder in `Exec=` replaced by the repository's
actual path) into `~/.local/share/applications/`, and the icon
[cswap-gui.svg](cswap-gui.svg) into
`~/.local/share/icons/hicolor/scalable/apps/`. Afterwards search for
"Claude Account Switcher" in your application menu. To uninstall,
delete those two installed files.

## Implementation notes

- Data comes from `cswap --list --json` (`schemaVersion: 1`). Upstream
  promises this contract is additive-only; if the schemaVersion is ever
  bumped, the GUI fails loudly instead of silently misparsing.
- Only stdout is parsed as JSON, so warnings on stderr cannot corrupt
  the payload.
- Switching, adding accounts and upgrading all run in background
  threads; the UI never blocks.

### Does querying the quota consume tokens?

No. The usage query goes to the read-only metadata endpoint
`GET https://api.anthropic.com/api/oauth/usage` (the same one Claude
Code's built-in `/usage` command uses). It triggers no model inference
and counts against no quota window. The only theoretical risk of
frequent polling is HTTP 429 rate limiting on that endpoint itself,
and cswap already guards against it — the GUI benefits directly:

- 30-second result cache (`SERVE_TTL_S`): repeated queries within 30 s
  are served from cache with zero network requests
- Failure backoff: exponential 30 s · 2ⁿ (capped at 10 minutes),
  honouring the server's `Retry-After`
- Credential safety: while Claude Code is running, the active
  account's OAuth token is never refreshed (avoids refresh races)

A 60-second auto-refresh therefore produces at most one lightweight
GET per account per tick — safe and negligible.

## Companion timers (optional, for reference)

These are the author's own systemd user timers. The GUI does not
depend on them; they are listed as a reference for the same
quota-management setup:

| Unit | Schedule | Purpose |
|------|----------|---------|
| `ai-cli-maintenance.timer` | daily 05:00 + 3 min after boot | upgrade the CLIs, then send one minimal haiku request so the 5h quota window starts early in the day (Fable is a weekly quota — no warmup needed) |
| `claude-swap-update.timer` | Mondays 00:00 | `uv tool upgrade claude-swap` |

Unit files live in `~/.config/systemd/user/`.

## Acknowledgements

- [claude-swap](https://github.com/realiti4/claude-swap) by
  [@realiti4](https://github.com/realiti4) — the multi-account
  switcher that does all the real work; this project is only a thin
  graphical shell over its excellent JSON interface
- [Claude Code](https://claude.com/claude-code) by
  [Anthropic](https://www.anthropic.com) — the coding agent whose
  accounts are being switched

## License

[MIT](LICENSE)
