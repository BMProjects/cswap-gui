#!/usr/bin/env bash
# Install cdp: symlink the entry point onto PATH and add the interactive
# interface to the application menu. Symlinks rather than copies, so pulling
# updates takes effect immediately. Pure stdlib Python; nothing to install.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"

mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR"

python3 - <<'PY' || { echo "Error: Python 3.10 or newer is required." >&2; exit 1; }
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY

python3 -c 'import curses' 2>/dev/null \
    || { echo "Error: this Python lacks the curses module (unusual; it normally ships with Python)." >&2; exit 1; }

command -v claude-desktop >/dev/null \
    || echo "Warning: claude-desktop not found; profiles will not be able to launch." >&2

ln -sf "$PROJECT_DIR/bin/cdp" "$BIN_DIR/cdp"
chmod +x "$PROJECT_DIR/bin/cdp"

cat > "$ICON_DIR/claude-profiles.svg" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <rect x="4" y="4" width="120" height="120" rx="28" fill="#2F3237"/>
  <circle cx="44" cy="46" r="15" fill="#D97757"/>
  <circle cx="84" cy="46" r="15" fill="#3D74D9"/>
  <circle cx="64" cy="86" r="15" fill="#4C9A5A"/>
</svg>
EOF

cat > "$APP_DIR/claude-profiles.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Claude Desktop Profiles
Name[zh_CN]=Claude Desktop 多账号
Comment=Manage multiple Claude Desktop account profiles and run them side by side
Comment[zh_CN]=管理多个 Claude Desktop 账号配置，可并行运行
Exec=$PROJECT_DIR/bin/cdp tui
Icon=claude-profiles
Terminal=true
Categories=Utility;
Keywords=claude;profile;account;multi-account;
EOF

command -v update-desktop-database >/dev/null && update-desktop-database "$APP_DIR" 2>/dev/null || true

echo "Installed:"
echo "  command    : $BIN_DIR/cdp  ->  $PROJECT_DIR/bin/cdp"
echo "  menu entry : $APP_DIR/claude-profiles.desktop"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "Note: $BIN_DIR is not on PATH. Add it and reopen your terminal." ;;
esac
echo
echo "Get started:  cdp        (interactive interface)"
echo "              cdp list   (command line)"
