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
                                         Browser

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
- 8888/tcp: MediaMTX HLS
- 8889/tcp + 8189/udp: MediaMTX WebRTC
- 1984/tcp + 8555 tcp/udp: go2rtc
- 8090/tcp: local dashboard

No public internet exposure is required.

## Microphone caveat

Browser microphone access requires a secure context. localhost works as an exception; ordinary HTTP on a LAN IP does not. The current stack therefore supports talkback through localhost/SSH tunneling. Trusted local HTTPS is a future infrastructure step.
