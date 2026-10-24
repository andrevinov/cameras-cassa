#!/usr/bin/env bash
set -Eeuo pipefail

MEDIAMTX_VERSION="1.21.2"
GO2RTC_VERSION="1.9.14"

if [ "$EUID" -ne 0 ]; then
  echo "This helper must run as root." >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64) ARCH="amd64" ;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y curl ca-certificates caddy ffmpeg python3 ufw psmisc tar

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl -fL https://downloads.rclone.org/rclone-current-linux-amd64.deb -o "$tmp/rclone.deb"
apt-get install -y "$tmp/rclone.deb"

curl -fL "https://github.com/bluenviron/mediamtx/releases/download/v$MEDIAMTX_VERSION/mediamtx_v${MEDIAMTX_VERSION}_linux_${ARCH}.tar.gz" -o "$tmp/mediamtx.tar.gz"
tar -xzf "$tmp/mediamtx.tar.gz" -C "$tmp"
install -m 0755 "$tmp/mediamtx" /usr/local/bin/mediamtx
install -d -m 0755 /usr/local/etc/mediamtx
install -m 0644 "$tmp/mediamtx.yml" /usr/local/etc/mediamtx/mediamtx.yml

curl -fL "https://github.com/AlexxIT/go2rtc/releases/download/v$GO2RTC_VERSION/go2rtc_linux_${ARCH}" -o /usr/local/bin/go2rtc
chmod 0755 /usr/local/bin/go2rtc

echo "Installed Caddy, MediaMTX $MEDIAMTX_VERSION, go2rtc $GO2RTC_VERSION, FFmpeg and rclone."
