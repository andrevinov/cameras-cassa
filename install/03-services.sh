#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$EUID" -ne 0 ]; then
  echo "This helper must run as root." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source /etc/cameras-cassa/config.env

for unit in "$ROOT"/systemd/*; do
  name="$(basename "$unit")"
  sed     -e "s/__SERVICE_USER__/$SERVICE_USER/g"     -e "s/__SERVICE_GROUP__/$SERVICE_GROUP/g"     -e "s/__SERVER_LAN_IP__/$SERVER_LAN_IP/g"     "$unit" > "/etc/systemd/system/$name"
  chmod 0644 "/etc/systemd/system/$name"
done

ufw allow OpenSSH >/dev/null

if ! ufw status | grep -q '^Status: active'; then
  printf "UFW is inactive. Enable it now? [y/N]: " >/dev/tty
  IFS= read -r answer </dev/tty
  if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    ufw --force enable
  fi
fi

if ! sudo -H -u "$SERVICE_USER" rclone listremotes 2>/dev/null | grep -qx "$RCLONE_REMOTE:"; then
  echo
  echo "rclone remote '$RCLONE_REMOTE' is not configured for $SERVICE_USER."
  echo "Use the Google Drive OAuth client with scope drive.file."
  echo "For headless OAuth, open an SSH local port forward to 127.0.0.1:53682 first."
  printf "Run rclone config now? [Y/n]: " >/dev/tty
  IFS= read -r answer </dev/tty
  if [ "$answer" != "n" ] && [ "$answer" != "N" ]; then
    sudo -H -u "$SERVICE_USER" rclone config
  fi
fi

if ! tailscale ip -4 >/dev/null 2>&1; then
  echo
  echo "Tailscale needs authentication."
  tailscale up --hostname=linuxrocks
fi

TAILSCALE_DNS="$(
  tailscale status --json |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'
)"

if [ -z "$TAILSCALE_DNS" ]; then
  echo "Could not determine Tailscale DNS name." >&2
  exit 1
fi

sed -i   "s#^  candidates: \[\]#  candidates:\n    - $TAILSCALE_DNS:10000#"   /etc/go2rtc.yaml

systemctl daemon-reload
systemctl enable --now mediamtx.service
systemctl enable --now camera1-webrtc-audio.service
systemctl enable --now go2rtc.service
systemctl restart go2rtc.service
systemctl enable --now camera-web.service
systemctl restart camera-web.service
systemctl enable --now camera-retry-upload.timer
systemctl enable --now camera-buffer-guard.timer
systemctl enable --now camera-drive-retention.timer

# Public family access: authenticated HTTPS app plus WebRTC TCP transport.
# go2rtc HTTP signaling remains loopback-only behind FastAPI.
tailscale serve reset
tailscale funnel --bg --https=443 http://127.0.0.1:8090
tailscale funnel --bg --tcp=10000 tcp://127.0.0.1:8555

echo
echo "Public authenticated dashboard and WebRTC transport:"
tailscale funnel status
