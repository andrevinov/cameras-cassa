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
                                             v
                                           Caddy
                                      HTTPS / WebSocket
                                             |
                                             v
                                         Browser

## HTTPS

Caddy terminates HTTPS on port 8443 with an internal CA.

The dashboard backend listens only on 127.0.0.1:8090. go2rtc's HTTP/WebSocket API listens only on 127.0.0.1:1984. Caddy publishes both under a single HTTPS origin:

- / -> dashboard
- /go2rtc/* -> go2rtc

The go2rtc WebRTC media transport still uses port 8555.

Each client device must trust Caddy's local root CA once. This is required for browser microphone access because getUserMedia only works in a secure context.

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
- 8443/tcp: local HTTPS dashboard
- 8090/tcp: loopback-only dashboard backend
- 1984/tcp: loopback-only go2rtc API

No public internet exposure is required.
