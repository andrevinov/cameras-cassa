# Setup and recovery

## Fresh server

Target: Ubuntu Server x86_64.

    git clone https://github.com/andrevinov/cameras-cassa.git
    cd cameras-cassa
    sudo ./install.sh

The installer asks for server LAN settings, camera settings, Drive path, retention and buffer thresholds.

## Secret locations

Runtime-only files:

- /etc/cameras-cassa/secrets.env
- /etc/mediamtx.env
- /etc/go2rtc.yaml
- /home/USER/.config/rclone/rclone.conf

Never copy these files into the public repository.

## Google Drive

The OAuth project uses a Desktop client and the drive.file scope.

For a headless server, a local SSH callback tunnel can be used during rclone authentication:

    ssh -L 127.0.0.1:53682:127.0.0.1:53682 USER@SERVER

Then run rclone config on the server and open the localhost authorization URL in the desktop browser.

## Validation

Services:

    systemctl status mediamtx go2rtc camera1-webrtc-audio camera-web

Timers:

    systemctl list-timers 'camera-*'

Drive:

    rclone about gdrive:

Upload log:

    tail -f /var/log/cameras-cassa/upload.log

## Local UI

Dashboard:

    http://SERVER_LAN_IP:8090

Video and audio work over the LAN. Browser microphone permission requires HTTPS or localhost.

## Re-running install.sh

The installer is intended to be repeatable. It refreshes pinned binaries, scripts, generated runtime configs and systemd units, while reusing an existing rclone remote when present.
