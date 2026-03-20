#!/usr/bin/env bash
# Octobot installation script
# Run as root: sudo bash install.sh
set -euo pipefail

INSTALL_DIR="/opt/octobot"
CONFIG_DIR="/etc/octobot"
SERVICE_USER="octobot"

echo "==> Creating system user '$SERVICE_USER'..."
id "$SERVICE_USER" &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"

echo "==> Creating directories..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"

echo "==> Copying source files..."
cp -r src pyproject.toml "$INSTALL_DIR/"

echo "==> Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/.venv"

echo "==> Installing octobot..."
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet -e "$INSTALL_DIR"

echo "==> Setting up config..."
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    cp config/config.yaml.example "$CONFIG_DIR/config.yaml"
    echo "   Config template written to $CONFIG_DIR/config.yaml — fill it in before starting the service."
else
    echo "   Config already exists at $CONFIG_DIR/config.yaml — skipping."
fi

echo "==> Making 'analyze' globally available..."
ln -sf "$INSTALL_DIR/.venv/bin/analyze" /usr/local/bin/analyze

echo "==> Installing systemd service..."
cp octobot.service /etc/systemd/system/octobot.service
sed -i "s|Environment=OCTOBOT_CONFIG=.*|Environment=OCTOBOT_CONFIG=$CONFIG_DIR/config.yaml|" /etc/systemd/system/octobot.service
systemctl daemon-reload

echo ""
echo "Installation complete."
echo ""
echo "Next steps:"
echo "  1. Edit $CONFIG_DIR/config.yaml with your tokens and settings"
echo "  2. sudo systemctl enable --now octobot"
echo "  3. sudo journalctl -fu octobot   # to follow logs"
echo ""
echo "Manual analysis:"
echo "  analyze PROJ-123"
echo "  analyze --comment PROJ-123   # force re-analysis"
