# Architecture

## Goal

Replace a proprietary DVR/NVR dependency with a small, auditable Linux stack using open protocols where possible.

## Current data flow

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
                v
          go2rtc /camera1-talk
                |
                | loopback HTTP/WebSocket
                v
       FastAPI authenticated proxy
                |
                | HTTPS via Tailscale Funnel :443
                v
             Browser

WebRTC media uses a second public Tailscale Funnel TCP endpoint:

    Internet TCP :10000
        -> Tailscale Funnel
        -> 127.0.0.1:8555
        -> go2rtc WebRTC TCP

go2rtc advertises the Funnel DNS name on port 10000 as its external ICE candidate.

## Authentication boundary

FastAPI owns the user session. Both the dashboard and go2rtc HTTP/WebSocket signaling cross the same authentication boundary.

- Dashboard: /
- Login: /login
- go2rtc proxy: /go2rtc/*
- go2rtc API itself: 127.0.0.1:1984 only

The application uses SQLite users, Argon2id password hashes, Secure/HttpOnly signed cookies, CSRF protection for login/logout and basic login rate limiting.

The public HTTPS Funnel exposes only FastAPI. There is no separate Funnel path for /go2rtc; FastAPI proxies it after authentication.

## Public family access

The verified public entry point is the Tailscale Funnel HTTPS hostname generated for the linuxrocks node.

Clients do not need Tailscale installed.

The public surfaces are:

- HTTPS 443 -> authenticated FastAPI application
- raw TCP 10000 -> go2rtc WebRTC transport

The signaling path remains authenticated. WebRTC media is DTLS-SRTP encrypted and negotiated through the authenticated signaling session.

## Talkback

Talkback is currently disabled in the stable configuration.

The iMX C RTSP/ONVIF endpoint advertises only recvonly media; no sendonly audio backchannel was found.

The earlier dvrip:// experiment was a protocol mismatch. See docs/talkback.md for the evidence and the future Dahua TCP/37777 path.

## Storage behavior

A finalized MediaMTX segment triggers camera-upload-segment.

rclone moveto uploads one file and removes the local source only after successful transfer. If transfer fails, the segment remains in the local buffer.

camera-retry-upload runs every five minutes and retries old files. It skips files that are still open.

camera-buffer-guard protects the server filesystem. If free space falls below MIN_FREE_GB, it deletes the oldest safe local segments first.

camera-drive-retention removes remote recordings older than RETENTION_DAYS.

## Ports

Camera LAN:
- 554/tcp: RTSP source
- 37777/tcp: proprietary Dahua/Intelbras protocol; not used by the stable stack today

Server:
- 8554/tcp: MediaMTX internal RTSP
- 1984/tcp: go2rtc API, loopback only
- 8090/tcp: authenticated FastAPI application, loopback only
- 8555/tcp: go2rtc WebRTC TCP listener

Public through Tailscale Funnel:
- 443/tcp: HTTPS application
- 10000/tcp: WebRTC TCP transport

No camera management endpoint is exposed directly to the internet.
