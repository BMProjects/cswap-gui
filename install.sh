#!/usr/bin/env bash
# 安装 cdp:把入口软链到 PATH,并把交互界面装进应用菜单。
# 软链而非拷贝,更新仓库后立即生效。纯 stdlib Python,无需安装任何依赖。
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"

mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR"

python3 - <<'PY' || { echo "错误: 需要 Python 3.10 或更高版本。" >&2; exit 1; }
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY

python3 -c 'import curses' 2>/dev/null \
    || { echo "错误: 该 Python 缺少 curses 模块（异常情况，通常随 Python 一起安装）。" >&2; exit 1; }

command -v claude-desktop >/dev/null \
    || echo "警告: 未找到 claude-desktop,profile 将无法启动。" >&2

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
Name=Claude Desktop 多账号
Name[en]=Claude Desktop Profiles
Comment=管理多个 Claude Desktop 账号配置，可并行运行
Comment[en]=Manage multiple Claude Desktop account profiles, run them side by side
Exec=$PROJECT_DIR/bin/cdp tui
Icon=claude-profiles
Terminal=true
Categories=Utility;
Keywords=claude;profile;account;多账号;
EOF

command -v update-desktop-database >/dev/null && update-desktop-database "$APP_DIR" 2>/dev/null || true

echo "已安装:"
echo "  命令    : $BIN_DIR/cdp  ->  $PROJECT_DIR/bin/cdp"
echo "  菜单入口: $APP_DIR/claude-profiles.desktop"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "提示: $BIN_DIR 不在 PATH 中,请将其加入后重开终端。" ;;
esac
echo
echo "开始使用:  cdp        （打开交互界面）"
echo "           cdp list   （命令行查看）"
