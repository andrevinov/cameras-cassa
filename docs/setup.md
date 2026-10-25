# Setup and recovery

## Fresh server

Target: Ubuntu Server x86_64.

    git clone https://github.com/andrevinov/cameras-cassa.git
    cd cameras-cassa
    sudo ./install.sh

The installer asks for server LAN settings, camera settings, Drive path, retention and buffer thresholds. It also creates the initial website user and configures Tailscale Funnel.

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

## Tailscale Funnel

The public family deployment exposes two Funnel endpoints:

    sudo tailscale serve reset
    sudo tailscale funnel --bg --https=443 http://127.0.0.1:8090
    sudo tailscale funnel --bg --tcp=10000 tcp://127.0.0.1:8555

The installer derives the node DNS name from:

    tailscale status --json

and writes it into the go2rtc WebRTC candidates list as:

    NODE_NAME.ts.net:10000

The HTTPS Funnel exposes only FastAPI. Do not add a separate /go2rtc Funnel mapping; FastAPI proxies /go2rtc after authentication.

## Talkback

Talkback is disabled on fresh installations until explicitly enabled. The local
Dahua TCP/37777 channel was verified with a short tone, and the browser path
was heard from the camera speaker on 2026-10-25. On the Ubuntu x86_64 server,
make the updated repo
and the official Linux64 NetSDK `.tar.gz` archive available, then run:

    sudo apt install g++
    sudo ./install/dahua-talkback.sh --sdk /path/to/General_NetSDK_Eng_Linux64_IS_V3.060.0000003.0.R.251127.tar.gz CAMERA_IP CAMERA_USER

The helper asks for the **camera's local device password**. It compiles and
installs the bridge and vendor libraries under `/opt/cameras-cassa/talk-sdk`,
updates the web virtual environment from `web/requirements.txt`,
copies the web code, creates `/etc/cameras-cassa/talkback-password` and
`talkback.env`, updates the camera-web service, and restarts that service. It
does not change go2rtc or MediaMTX. Only `camera-web` receives the optional
configuration; the vendor libraries are loaded by its short-lived bridge
process.

Open the authenticated dashboard over HTTPS. Hold **Segure para falar**, allow
microphone access, speak while holding, then release. Have someone next to the
camera report whether the voice played. The button shows connection errors.
For a quick rollback, disable the optional environment file and restart the
web service:

    sudo mv /etc/cameras-cassa/talkback.env /etc/cameras-cassa/talkback.env.disabled
    sudo systemctl restart camera-web.service

See docs/talkback.md for protocol evidence and details.

Do not add the old dvrip:// backchannel to /etc/go2rtc.yaml.

## Validation

Services:

    systemctl status mediamtx go2rtc camera1-webrtc-audio camera-web tailscaled

Timers:

    systemctl list-timers 'camera-*'

Web backend:

    curl http://127.0.0.1:8090/health

Funnel:

    tailscale funnel status

Drive:

    rclone about gdrive:

Users:

    sudo -u andre camera-user list

go2rtc:

    curl -s 'http://127.0.0.1:1984/api/streams?src=camera1-talk' | python3 -m json.tool

## Re-running install.sh

The installer is intended to be repeatable. It refreshes pinned binaries, the Python virtual environment, scripts, generated runtime configs and systemd units, while preserving the existing session secret and user database.
