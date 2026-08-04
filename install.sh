#!/usr/bin/env bash
# 安装 cdp:把 CLI 软链到 PATH,并把图形管理界面装进应用菜单。
# 软链而非拷贝,便于就地更新仓库后立即生效。
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"

mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR"

command -v claude-desktop >/dev/null \
    || echo "警告: 未找到 claude-desktop,profile 将无法启动。" >&2
python3 -c 'import tkinter' 2>/dev/null \
    || echo "警告: 系统 python3 缺少 tkinter,图形界面无法启动。请运行: sudo apt install python3-tk" >&2

ln -sf "$PROJECT_DIR/bin/cdp" "$BIN_DIR/cdp"
chmod +x "$PROJECT_DIR/bin/cdp" "$PROJECT_DIR/app/cdp_gui.py"

# 管理界面的图标:中性石板底 + 三色点,区别于各 profile 的单色图标。
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
Exec=$PROJECT_DIR/app/cdp_gui.py
Icon=claude-profiles
Terminal=false
Categories=Utility;
Keywords=claude;profile;account;多账号;
EOF

command -v update-desktop-database >/dev/null && update-desktop-database "$APP_DIR" 2>/dev/null || true

echo "已安装:"
echo "  CLI    : $BIN_DIR/cdp  ->  $PROJECT_DIR/bin/cdp"
echo "  管理界面: $APP_DIR/claude-profiles.desktop"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "提示: $BIN_DIR 不在 PATH 中,请将其加入后重开终端。" ;;
esac
echo
echo "开始使用:  cdp add Work --color blue   然后  cdp list"
