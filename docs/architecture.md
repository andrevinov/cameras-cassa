# Architecture

## Goal

Replace a proprietary DVR/NVR dependency with a small, auditable Linux stack using open protocols where possible.

## Data flow

    Intelbras iMX C Black
       |
       | RTSP: H.264 + AAC
       v
    MediaMTX /camera1
       |-----------------------> fMP4 recording, 10 minute segments
       |                              |
       |                              v
       |                       camera-upload-segment
       |                              |
       |                              v
       |                         rclone / Drive
       |
       +--> FFmpeg
             video: copy
             audio: AAC -> Opus
                |
                v
          MediaMTX /camera1-web
                |
                +---------------------+
                                      |
    camera DVRIP :37777 backchannel --+--> go2rtc /camera1-talk
                                             |
                                             | loopback HTTP/WebSocket
                                             v
                                    FastAPI authenticated proxy
                                             |
                                             | HTTPS
                                             v
                                         Browser

## Authentication boundary

FastAPI owns the user session. Both the dashboard and go2rtc HTTP/WebSocket traffic cross the same authentication boundary.

- Dashboard: /
- Login: /login
- go2rtc proxy: /go2rtc/*
- go2rtc API itself: 127.0.0.1:1984 only

The application uses SQLite users, Argon2id password hashes, Secure/HttpOnly signed cookies, CSRF protection for login/logout and basic login rate limiting.

During the current private deployment, Tailscale Serve exposes only the FastAPI application. There must be no separate Serve mapping for /go2rtc because that would bypass application authentication.

## Remote access evolution

Current:
- Tailscale Serve provides trusted HTTPS.
- Only tailnet members can reach the site.

Future public family access:
- place the same authenticated FastAPI application behind a public HTTPS domain;
- keep go2rtc:1984 private;
- provide WebRTC reachability with a controlled TURN/public ICE design.

## Storage behavior

A finalized MediaMTX segment triggers camera-upload-segment.

rclone moveto uploads one file and removes the local source only after successful transfer. If transfer fails, the segment remains in the local buffer.

camera-retry-upload runs every five minutes and retries old files. It skips files that are still open.

camera-buffer-guard protects the server filesystem. If free space falls below MIN_FREE_GB, it deletes the oldest safe local segments first.

camera-drive-retention removes remote recordings older than RETENTION_DAYS.

## Ports

- 554/tcp on camera: RTSP source
- 37777/tcp on camera: DVRIP / talkback
- 8554/tcp on server: MediaMTX internal RTSP
- 8555/tcp+udp: go2rtc WebRTC media
- 1984/tcp: loopback-only go2rtc API
- 8090/tcp: loopback-only authenticated FastAPI application
- 443 via Tailscale Serve: HTTPS dashboard

No camera management endpoint is exposed directly to the internet.
