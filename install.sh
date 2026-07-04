#!/usr/bin/env bash
# 安装桌面入口:把 cswap-gui.desktop(替换为本机路径)和图标
# 装入 XDG 用户目录,应用菜单随即出现「Claude 账号切换」。
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"

mkdir -p "$APP_DIR" "$ICON_DIR"
sed "s|@PROJECT_DIR@|$PROJECT_DIR|" "$PROJECT_DIR/cswap-gui.desktop" \
    > "$APP_DIR/cswap-gui.desktop"
cp "$PROJECT_DIR/cswap-gui.svg" "$ICON_DIR/cswap-gui.svg"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" || true
fi

echo "已安装: $APP_DIR/cswap-gui.desktop"
echo "已安装: $ICON_DIR/cswap-gui.svg"
