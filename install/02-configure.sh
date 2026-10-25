#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

if [ "$EUID" -ne 0 ]; then
  echo "This helper must run as root." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_USER="$(logname 2>/dev/null || true)"

prompt() {
  local name="$1"
  local label="$2"
  local default="$3"
  local value
  printf "%s [%s]: " "$label" "$default" >/dev/tty
  IFS= read -r value </dev/tty
  printf -v "$name" '%s' "${value:-$default}"
}

if [ -z "$SERVICE_USER" ] || [ "$SERVICE_USER" = "root" ]; then
  prompt SERVICE_USER "Non-root service user" "andre"
fi

id "$SERVICE_USER" >/dev/null
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

prompt SERVER_LAN_IP "Server LAN IP" "192.168.0.10"
prompt LAN_CIDR "Home LAN CIDR" "192.168.0.0/24"
prompt CAMERA1_IP "Camera IP" "192.168.0.9"
prompt CAMERA1_USER "Camera user" "admin"
prompt CAMERA1_RTSP_PORT "Camera RTSP port" "554"
prompt RCLONE_REMOTE "rclone remote name" "gdrive"
prompt RCLONE_BASE_PATH "Drive recordings path" "Cameras-Casa/Gravacoes"
prompt RECORD_SEGMENT_DURATION "Segment duration" "10m"
prompt RETENTION_DAYS "Drive retention (days)" "7"
prompt MIN_FREE_GB "Minimum free disk space (GiB)" "20"

printf "Camera password: " >/dev/tty
IFS= read -r -s CAMERA1_PASSWORD </dev/tty
printf "\n" >/dev/tty

if [ -z "$CAMERA1_PASSWORD" ]; then
  echo "Camera password cannot be empty." >&2
  exit 1
fi

BUFFER_DIR="/var/lib/cameras-cassa/buffer"
STATE_DIR="/var/lib/cameras-cassa/state"
LOG_DIR="/var/log/cameras-cassa"
WEB_DIR="/opt/cameras-cassa/web"
VENV_DIR="/opt/cameras-cassa/venv"
USERS_DB="/var/lib/cameras-cassa/users.sqlite3"
SESSION_SECRET_FILE="/etc/cameras-cassa/session-secret"

install -d -o root -g "$SERVICE_GROUP" -m 0750 /etc/cameras-cassa
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0750 "$BUFFER_DIR" "$STATE_DIR" "$LOG_DIR"
install -d -m 0755 "$WEB_DIR"

rm -rf "$WEB_DIR"/*
cp -a "$ROOT/web/." "$WEB_DIR/"
chown -R root:root "$WEB_DIR"
find "$WEB_DIR" -type d -exec chmod 0755 {} +
find "$WEB_DIR" -type f -exec chmod 0644 {} +

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$WEB_DIR/requirements.txt"

for script in "$ROOT"/scripts/*; do
  install -m 0755 "$script" "/usr/local/bin/$(basename "$script")"
done

if [ ! -s "$SESSION_SECRET_FILE" ]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > "$SESSION_SECRET_FILE"
fi
chown root:"$SERVICE_GROUP" "$SESSION_SECRET_FILE"
chmod 0640 "$SESSION_SECRET_FILE"

{
  printf 'SERVICE_USER=%q\n' "$SERVICE_USER"
  printf 'SERVICE_GROUP=%q\n' "$SERVICE_GROUP"
  printf 'SERVER_LAN_IP=%q\n' "$SERVER_LAN_IP"
  printf 'LAN_CIDR=%q\n' "$LAN_CIDR"
  printf 'CAMERA_BUFFER_DIR=%q\n' "$BUFFER_DIR"
  printf 'CAMERA_STATE_DIR=%q\n' "$STATE_DIR"
  printf 'CAMERA_LOG_DIR=%q\n' "$LOG_DIR"
  printf 'RCLONE_REMOTE=%q\n' "$RCLONE_REMOTE"
  printf 'RCLONE_BASE_PATH=%q\n' "$RCLONE_BASE_PATH"
  printf 'RETRY_MIN_AGE_MINUTES=2\n'
  printf 'BUFFER_GUARD_MIN_AGE_MINUTES=15\n'
  printf 'MIN_FREE_GB=%q\n' "$MIN_FREE_GB"
  printf 'RETENTION_DAYS=%q\n' "$RETENTION_DAYS"
} > /etc/cameras-cassa/config.env
chown root:"$SERVICE_GROUP" /etc/cameras-cassa/config.env
chmod 0640 /etc/cameras-cassa/config.env

PASSWORD_B64="$(printf '%s' "$CAMERA1_PASSWORD" | base64 -w0)"
printf 'CAMERA1_PASSWORD_B64=%s\n' "$PASSWORD_B64" > /etc/cameras-cassa/secrets.env
chmod 0600 /etc/cameras-cassa/secrets.env

urlencode() {
  python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read(), safe=""))'
}

USER_URL="$(printf '%s' "$CAMERA1_USER" | urlencode)"
PASS_URL="$(printf '%s' "$CAMERA1_PASSWORD" | urlencode)"

cat > /etc/mediamtx.env <<EOF
MTX_MOQ=false
MTX_RTMP=false
MTX_SRT=false
MTX_PATHS_CAMERA1_SOURCE=rtsp://$USER_URL:$PASS_URL@$CAMERA1_IP:$CAMERA1_RTSP_PORT/cam/realmonitor?channel=1&subtype=0
MTX_PATHS_CAMERA1_RTSPTRANSPORT=tcp
MTX_PATHS_CAMERA1_RECORD=true
MTX_PATHS_CAMERA1_RECORDPATH=$BUFFER_DIR/%path/%Y-%m-%d/%H-%M-%S-%f
MTX_PATHS_CAMERA1_RECORDFORMAT=fmp4
MTX_PATHS_CAMERA1_RECORDPARTDURATION=1s
MTX_PATHS_CAMERA1_RECORDSEGMENTDURATION=$RECORD_SEGMENT_DURATION
MTX_PATHS_CAMERA1_RECORDDELETEAFTER=0s
MTX_PATHS_CAMERA1_RUNONRECORDSEGMENTCOMPLETE=/usr/local/bin/camera-upload-segment
EOF
chown root:"$SERVICE_GROUP" /etc/mediamtx.env
chmod 0640 /etc/mediamtx.env

# Talkback is intentionally disabled here.
# The Intelbras iMX C RTSP/ONVIF endpoint exposes recvonly audio and the
# old dvrip:// experiment used the wrong protocol family. See docs/talkback.md.
cat > /etc/go2rtc.yaml <<EOF
api:
  listen: "127.0.0.1:1984"
rtsp:
  listen: ""
webrtc:
  listen: ":8555/tcp"
  candidates: []
streams:
  camera1-talk:
    - 'rtsp://127.0.0.1:8554/camera1-web#backchannel=0'
EOF
chown root:"$SERVICE_GROUP" /etc/go2rtc.yaml
chmod 0640 /etc/go2rtc.yaml

if ! sudo -H -u "$SERVICE_USER" env CAMERAS_USERS_DB="$USERS_DB" "$VENV_DIR/bin/python" "$WEB_DIR/manage_users.py" has-users; then
  prompt WEB_ADMIN_USER "Initial website username" "$SERVICE_USER"
  sudo -H -u "$SERVICE_USER" env CAMERAS_USERS_DB="$USERS_DB"     "$VENV_DIR/bin/python" "$WEB_DIR/manage_users.py" add "$WEB_ADMIN_USER"
fi

echo "Runtime configuration written under /etc and /var/lib/cameras-cassa."
