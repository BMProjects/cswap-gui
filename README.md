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
- Optional auto-refresh every 5 minutes (off by default, enable via
  the checkbox). It refreshes **only the active account**, via
  `cswap --status --json`, so accounts you have switched away from
  are never polled and spend nothing from their own rate-limit
  budget. The manual "刷新" button still refreshes every account via
  `cswap --list --json`. Auto-refresh failures only appear in the
  status bar instead of popping up dialogs
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
and counts against no quota window.

The real constraint is **HTTP 429 rate limiting on that endpoint**.
Per cswap's own measurements (`poll_policy.py`), the budget is roughly
**28-30 requests per rolling 60-minute window, per token**, and it is
not a leaky bucket: capacity returns only as old requests age out of
the trailing hour, so a burst can saturate a token for a full hour and
pausing does not restore headroom early.

The GUI is deliberately conservative about this:

- Auto-refresh is **off by default**, and when enabled runs every
  5 minutes (12/hour) — comfortably under cswap's own ≤20/hour target,
  leaving headroom for manual commands and other surfaces
- Auto-refresh queries **only the active account**; switched-away
  accounts are never polled
- cswap itself adds a 180 s shared cache (multiple open surfaces do
  not multiply requests), a 360 s floor for an hour after any 429, and
  AIMD backoff up to 30 minutes on a contended token
- Credential safety: while Claude Code is running, the active
  account's OAuth token is never refreshed (avoids refresh races)

Worth knowing: if an account breaks (expired subscription, dead
credentials), its failing fetches keep consuming that token's budget.
Consider removing such an account until it is fixed.

## Companion timers (optional, for reference)

This is the author's own systemd user timer. The GUI does not depend
on it; it is listed as a reference for the same quota-management
setup:

| Unit | Schedule | Purpose |
|------|----------|---------|
| `ai-cli-maintenance.timer` | daily 05:00 + 3 min after boot | upgrade the CLIs, then send one minimal haiku request so the 5h quota window starts early in the day (Fable is a weekly quota — no warmup needed) |

Unit files live in `~/.config/systemd/user/`. Keeping claude-swap
itself up to date is done on demand via the GUI's "upgrade cswap"
button (a former weekly auto-upgrade timer has been retired).

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
