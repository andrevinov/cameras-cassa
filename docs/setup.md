# Setup and recovery

## Fresh server

Target: Ubuntu Server x86_64.

    git clone https://github.com/andrevinov/cameras-cassa.git
    cd cameras-cassa
    sudo ./install.sh

The installer asks for server LAN settings, camera settings, Drive path, retention and buffer thresholds. It also creates the initial website user.

## Secret/runtime locations

- /etc/cameras-cassa/secrets.env
- /etc/cameras-cassa/session-secret
- /etc/mediamtx.env
- /etc/go2rtc.yaml
- /home/USER/.config/rclone/rclone.conf
- /var/lib/cameras-cassa/users.sqlite3

Never copy these files into the public repository.

## Google Drive

The OAuth project uses a Desktop client and the drive.file scope.

For a headless server, a local SSH callback tunnel can be used during rclone authentication:

    ssh -L 127.0.0.1:53682:127.0.0.1:53682 USER@SERVER

Then run rclone config on the server and open the localhost authorization URL in the desktop browser.

## Website users

    sudo -u andre camera-user add monalise
    sudo -u andre camera-user passwd monalise
    sudo -u andre camera-user disable monalise
    sudo -u andre camera-user enable monalise
    sudo -u andre camera-user list

## Tailscale Serve

The current private HTTPS deployment publishes only FastAPI:

    sudo tailscale serve reset
    sudo tailscale serve --bg --https=443 http://127.0.0.1:8090

Do not publish /go2rtc separately. FastAPI proxies that path after authentication.

## Validation

Services:

    systemctl status mediamtx go2rtc camera1-webrtc-audio camera-web tailscaled

Timers:

    systemctl list-timers 'camera-*'

Web backend:

    curl http://127.0.0.1:8090/health

Drive:

    rclone about gdrive:

Users:

    sudo -u andre camera-user list

## Re-running install.sh

The installer is intended to be repeatable. It refreshes pinned binaries, the Python virtual environment, scripts, generated runtime configs and systemd units, while preserving the existing session secret and user database.
