# Talkback status

## Current verified state

The Intelbras iMX C Black video/audio stream works through:

- RTSP from camera -> MediaMTX
- H.264 video copied without re-encoding
- AAC audio transcoded to Opus for browser WebRTC
- go2rtc -> authenticated FastAPI proxy -> browser

Browser microphone capture was also verified: when opening a WebRTC session with microphone enabled, go2rtc receives an Opus/48000 audio track from the browser.

However, the camera does **not** expose an RTSP/ONVIF talkback track. Its SDP advertises only recvonly media:

- video recvonly H264
- audio recvonly MPEG4-GENERIC/AAC
- ONVIF metadata recvonly

No audio sendonly track is advertised.

## Incorrect experiment: dvrip://

The original configuration used:

    dvrip://...:37777?backchannel=1

That was a protocol-family mismatch.

go2rtc's DVR-IP source targets the XMEye/NetSurveillance/Sofia family. The Intelbras/Dahua-style TCP port 37777 talk channel is a different proprietary protocol.

The stable configuration therefore contains no dvrip backchannel.

## Likely future path: Dahua raw TCP/37777

go2rtc issue #2414 documents an experimental native Go implementation of Dahua's raw TCP/37777 talk protocol with a new dahua:// source:

https://github.com/AlexxIT/go2rtc/issues/2414

The reporter verified a backchannel exposed as:

    audio, sendonly, PCMA/8000

on a Dahua-based rebrand.

As of the current project state, this support is not part of the pinned upstream go2rtc 1.9.14 binary used by cameras-cassa.

## Policy

Until Dahua TCP/37777 support is integrated and tested against the iMX C Black:

- keep camera1-talk read-only;
- keep #backchannel=0 on the MediaMTX-derived stream;
- keep the dashboard Talk button disabled;
- do not reintroduce dvrip:// as a workaround.

Any experimental Dahua-enabled go2rtc build should be tested separately before replacing the production binary.
