#!/usr/bin/env bash
set -Eeuo pipefail
umask 027
export LC_ALL=C

if [ "$EUID" -ne 0 ] || [ "$#" -ne 4 ] || [ "$1" != "--sdk" ]; then
  echo "Use: sudo ./install/dahua-talkback.sh --sdk /path/NetSDK-Linux64.tar.gz CAMERA_IP CAMERA_USER" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVE="$2"
CAMERA_IP="$3"
CAMERA_USER="$4"
if [ ! -r /etc/cameras-cassa/config.env ] || [ ! -d /opt/cameras-cassa/web ] ||
   [ ! -x /opt/cameras-cassa/venv/bin/pip ]; then
  echo "Install the base cameras-cassa stack before enabling talkback." >&2
  exit 2
fi
source /etc/cameras-cassa/config.env

python3 -c 'import ipaddress,sys; ipaddress.IPv4Address(sys.argv[1])' "$CAMERA_IP"
if [[ ! "$CAMERA_USER" =~ ^[a-zA-Z0-9_.-]+$ ]]; then
  echo "Camera user contains unsupported characters." >&2
  exit 2
fi
if [ ! -f "$ARCHIVE" ] || ! command -v g++ >/dev/null; then
  echo "SDK archive and g++ are required (sudo apt install g++)." >&2
  exit 2
fi

TMP_DIR="$(mktemp -d /tmp/cameras-talk-install.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT
tar -xf "$ARCHIVE" -C "$TMP_DIR"
HEADER="$TMP_DIR/Include/Common/dhnetsdk.h"
LIBRARY="$TMP_DIR/Bin/libdhnetsdk.so"
if [ ! -f "$HEADER" ] || [ ! -f "$LIBRARY" ]; then
  echo "Archive is missing Include/Common/dhnetsdk.h or Bin/libdhnetsdk.so." >&2
  exit 2
fi

g++ -std=c++11 -O2 -Wall -Wextra \
  -isystem "$TMP_DIR/Include/Common" \
  "$ROOT/tools/dahua-talk-bridge.cpp" \
  -L "$TMP_DIR/Bin" -Wl,-rpath-link,"$TMP_DIR/Bin" \
  -ldhnetsdk -o "$TMP_DIR/dahua-talk-bridge"

/opt/cameras-cassa/venv/bin/pip install -r "$ROOT/web/requirements.txt"
if ! /opt/cameras-cassa/venv/bin/python -c 'from starlette import status; from fastapi import FastAPI' >/dev/null 2>&1; then
  echo "Repairing incomplete Starlette installation..." >&2
  /opt/cameras-cassa/venv/bin/pip install --no-cache-dir --force-reinstall --no-deps 'starlette==0.50.0'
fi
/opt/cameras-cassa/venv/bin/python -c 'from starlette import status; from fastapi import FastAPI'

install -d -o root -g root -m 0755 /opt/cameras-cassa/talk-sdk/lib
for library in "$TMP_DIR"/Bin/*.so*; do
  target="/opt/cameras-cassa/talk-sdk/lib/$(basename "$library")"
  install -o root -g root -m 0644 "$library" "$target.new"
  mv -f "$target.new" "$target"
done
install -o root -g root -m 0755 "$TMP_DIR/dahua-talk-bridge" /opt/cameras-cassa/talk-sdk/dahua-talk-bridge.new
mv -f /opt/cameras-cassa/talk-sdk/dahua-talk-bridge.new /opt/cameras-cassa/talk-sdk/dahua-talk-bridge

printf "Camera password: " >/dev/tty
IFS= read -r -s CAMERA_PASSWORD </dev/tty
printf "\n" >/dev/tty
if [ -z "$CAMERA_PASSWORD" ] || [ "${#CAMERA_PASSWORD}" -gt 256 ]; then
  echo "Camera password must contain 1 to 256 bytes." >&2
  exit 2
fi

install -d -o root -g "$SERVICE_GROUP" -m 0750 /etc/cameras-cassa
PASSWORD_TMP="$(mktemp /etc/cameras-cassa/talkback-password.XXXXXX)"
printf '%s' "$CAMERA_PASSWORD" > "$PASSWORD_TMP"
unset CAMERA_PASSWORD
chown root:"$SERVICE_GROUP" "$PASSWORD_TMP"
chmod 0640 "$PASSWORD_TMP"
mv -f "$PASSWORD_TMP" /etc/cameras-cassa/talkback-password

ENV_TMP="$(mktemp /etc/cameras-cassa/talkback.env.XXXXXX)"
{
  printf 'CAMERAS_TALK_ENABLED=1\n'
  printf 'CAMERAS_TALK_BRIDGE=/opt/cameras-cassa/talk-sdk/dahua-talk-bridge\n'
  printf 'CAMERAS_TALK_CAMERA_IP=%s\n' "$CAMERA_IP"
  printf 'CAMERAS_TALK_CAMERA_USER=%s\n' "$CAMERA_USER"
  printf 'CAMERAS_TALK_PASSWORD_FILE=/etc/cameras-cassa/talkback-password\n'
  printf 'CAMERAS_TALK_SDK_LIB=/opt/cameras-cassa/talk-sdk/lib\n'
} > "$ENV_TMP"
chown root:root "$ENV_TMP"
chmod 0600 "$ENV_TMP"
mv -f "$ENV_TMP" /etc/cameras-cassa/talkback.env

cp -a "$ROOT/web/." /opt/cameras-cassa/web/
chown -R root:root /opt/cameras-cassa/web
find /opt/cameras-cassa/web -type d -exec chmod 0755 {} +
find /opt/cameras-cassa/web -type f -exec chmod 0644 {} +
sed -e "s/__SERVICE_USER__/$SERVICE_USER/g" \
    -e "s/__SERVICE_GROUP__/$SERVICE_GROUP/g" \
    "$ROOT/systemd/camera-web.service" > /etc/systemd/system/camera-web.service
chmod 0644 /etc/systemd/system/camera-web.service
systemctl daemon-reload
systemctl restart camera-web.service
healthy=0
for attempt in {1..20}; do
  if curl --silent --fail http://127.0.0.1:8090/health >/dev/null; then
    healthy=1
    break
  fi
  sleep 1
done
if [ "$healthy" -ne 1 ]; then
  echo "camera-web failed its local health check after restart." >&2
  systemctl status camera-web.service --no-pager -l >&2 || true
  exit 1
fi
echo "Talkback enabled. Hold the Talk button in the authenticated dashboard to test."
