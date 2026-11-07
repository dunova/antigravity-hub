#!/bin/bash
# Antigravity Hub Linux 一键安装与系统守护注册脚本
set -euo pipefail

HUB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="${HOME}/.config/systemd/user"
APP_DIR="${HOME}/.local/share/applications"

echo "🚀 [Antigravity Hub] 开始部署 Linux 环境..."

# 1. 确保数据目录就绪
mkdir -p "${HOME}/.antigravity_hub/data"
mkdir -p "${HOME}/.antigravity_hub/browser_profiles"
mkdir -p "${SERVICE_DIR}"
mkdir -p "${APP_DIR}"

# 2. 生成并安装专属优化 Logo 图标套件
python3 "${HUB_DIR}/scripts/generate_hub_logo.py" || true
gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" 2>/dev/null || true

# 3. 安装 systemd user service
cp "${HUB_DIR}/deploy/antigravity-hub.service" "${SERVICE_DIR}/antigravity-hub.service"
systemctl --user daemon-reload
systemctl --user enable antigravity-hub.service
systemctl --user restart antigravity-hub.service
echo "✅ systemd user 守护服务已安装并启动: antigravity-hub.service"

# 4. 安装桌面图标
cp "${HUB_DIR}/deploy/antigravity-hub.desktop" "${APP_DIR}/antigravity-hub.desktop"
update-desktop-database "${APP_DIR}" 2>/dev/null || true
echo "✅ 桌面启动器已注册: ${APP_DIR}/antigravity-hub.desktop"

# 4. 验收服务状态
sleep 1
if systemctl --user is-active --quiet antigravity-hub.service; then
    echo "🎉 [部署成功] Antigravity Hub 正在后台运行！"
    echo "👉 Web 控制台: http://127.0.0.1:18088"
else
    echo "⚠️ 服务未在运行，请检查日志: journalctl --user -u antigravity-hub.service -n 50"
fi
