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
for port in 8090 1984 8555 8888 8889; do
  ufw allow from "$LAN_CIDR" to any port "$port" proto tcp >/dev/null
done
for port in 8555 8189; do
  ufw allow from "$LAN_CIDR" to any port "$port" proto udp >/dev/null
done

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

systemctl daemon-reload
systemctl enable --now mediamtx.service
systemctl enable --now camera1-webrtc-audio.service
systemctl enable --now go2rtc.service
systemctl enable --now camera-web.service
systemctl enable --now camera-retry-upload.timer
systemctl enable --now camera-buffer-guard.timer
systemctl enable --now camera-drive-retention.timer

echo
echo "Dashboard: http://$SERVER_LAN_IP:8090"
echo "MediaMTX HLS: http://$SERVER_LAN_IP:8888/camera1/"
echo "MediaMTX WebRTC: http://$SERVER_LAN_IP:8889/camera1/"
echo "go2rtc: http://$SERVER_LAN_IP:1984/"
echo
echo "Microphone access in browsers requires HTTPS or localhost."
