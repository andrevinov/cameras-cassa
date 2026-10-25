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

## Verified camera path: Dahua raw TCP/37777

go2rtc issue #2414 documents an experimental native Go implementation of Dahua's raw TCP/37777 talk protocol with a new dahua:// source:

https://github.com/AlexxIT/go2rtc/issues/2414

The reporter verified a backchannel exposed as:

    audio, sendonly, PCMA/8000

on a Dahua-based rebrand.

As of the current project state, this support is not part of the pinned upstream go2rtc 1.9.14 binary used by cameras-cassa. The isolated NetSDK probe below independently confirms that this camera accepts talk audio over TCP/37777.

## Step 1: verify the camera's actual talk traffic

On 2026-10-25, a computer on the home LAN established a TCP connection to
the camera's port 37777. This proves only that the port is reachable. It does
**not** prove that the iMX C accepts talk audio, which codec it uses, or that
the official app talks directly to this port.

The capture procedure below needs working talkback in the Mibo Smart app.
If the app is no longer installed, reinstall it and sign in with the account
previously used for this camera. Check whether the camera appears and Talk
still works before starting a capture. Reinstalling the app is a separate
step from resetting or pairing the camera again. If the app asks for camera
reset, new Wi-Fi provisioning or credential changes, pause and check the
impact on the current RTSP setup first.

Once the app works, capture two short sessions from the phone:

1. **Idle:** connect the phone to the home Wi-Fi, open the camera's live view,
   leave the Talk control off for about 15 seconds, then stop the capture.
2. **Talk:** start a fresh capture, open the same view, press Talk, speak for
   about 10 seconds, release Talk, and stop the capture. Listen at the camera
   to confirm whether it actually played the voice.

On Android, [PCAPdroid](https://emanuele-f.github.io/PCAPdroid/dump_modes.html)
can save each capture as a classic PCAP file without root. Select **PCAP File**
as its dump mode and capture only the camera app if possible. Its local VPN
capture can conflict with another active VPN. A capture made on this computer
will not see a direct phone-to-camera connection unless that traffic actually
passes through this computer. For an iPhone, capture on the phone or on a
router/access point with traffic mirroring.

Keep the raw captures private: they can contain camera credentials or session
tokens. `*.pcap` and `*.pcapng` are ignored by Git. Do not paste raw packet
contents into an issue or commit a capture. The report tool supports **classic
PCAP**, including Ethernet, raw IPv4 and Linux cooked link types; if an export
is PCAPNG, convert it locally with a packet-capture tool before running it.

    python3 tools/dahua-capture-report \
      --camera-ip CAMERA_LAN_IP idle.pcap talk.pcap

The report prints aggregate TCP/37777 and UDP traffic to the camera, plus
complete DHAV audio frames and their codec from the DHAV header. It does not
print packet contents or addresses. In PCAPdroid's no-root mode, return packet
headers can be synthetic, so TCP return traffic is matched by the phone's
connection endpoint rather than assuming the camera's source IP/port. Compare
the two sessions, then record separately:

- whether the official app opened a connection to the camera on TCP/37777;
- whether traffic from phone to camera increased during Talk;
- whether the camera speaker played the test voice;
- the codec and framing, **only if** these can be verified from the capture or
  device configuration.

If no direct LAN traffic appears over either TCP or UDP, the app may use a
cloud relay or the capture may have missed the connection. That result is
inconclusive for the camera's local talk protocol.

### Captured Mibo Smart result (2026-10-25)

Two PCAPdroid captures from Mibo Smart were analyzed locally. The first had
live view only (47 seconds); the second included a Talk interval (41 seconds).
Both captures had **zero** direct TCP/37777 packets. They did have direct UDP
traffic to the camera's LAN IP on dynamically assigned ports:

| Capture | UDP payload sent to camera | PTCP packets | Complete DHAV audio frames |
| --- | ---: | ---: | ---: |
| Idle | 44,977 bytes | 1,743 | 0 |
| Talk | 276,965 bytes | 1,957 | 535 |

In the Talk capture, the DHAV audio frames run from approximately second 10
through second 31. Their header says mono `PCMA/8000`; each complete frame is
400 bytes, with 320 bytes of encoded audio. This decoding follows the
[FFmpeg DHAV parser](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/dhav.c).
An independent `ffprobe` check of the extracted complete frames reported
`pcm_alaw`, 8,000 Hz and one channel.
The packets carry the `PTCP` marker, consistent with the
[Dahua P2P transport](https://github.com/ludufre/dahua-p2p).
The operator confirmed hearing the spoken test phrase from the camera speaker
during the Talk capture. This closes the end-to-end Mibo Smart talkback check:
phone microphone -> UDP/PTCP -> DHAV PCMA/8000 -> camera speaker.

This establishes the **Mibo Smart LAN talk path** as UDP/PTCP carrying DHAV
audio. It does not show that the camera rejects a separate TCP/37777 talk
protocol; the app simply did not use that path in these captures. A future
implementation must choose and test its transport explicitly. The stable
go2rtc configuration remains read-only.

## Step 2: isolated TCP/37777 probe

`tools/dahua-talk-probe` builds a short-lived native client against a locally
extracted **official Dahua NetSDK Linux64** package. It logs in over
TCP/37777, asks the camera which talk formats it accepts, and, only if
`PCMA/8000` is listed, can send a three-second 750 Hz tone. It does not change
MediaMTX, go2rtc, FastAPI, systemd, or camera settings. The password is read
from the terminal without echo; it is never supplied as a command argument.

1. On a Linux x86_64 machine on the same LAN as the camera, download
   `General_NetSDK_Eng_Linux64_IS_V3.060.0000003.0.R.251127.tar.gz` from the
   [Dahua Partner SDK download page](https://previous-depp.dahuasecurity.com/integration/guide/download/sdk).
   The vendor site may require a browser login. Keep this vendor archive out of
   the repository.
2. Extract it to a new temporary directory owned by your user. Do not create
   the directory with `sudo`, or a normal `tar` command will not be able to
   write into it:

       SDK_DIR="$(mktemp -d /tmp/dahua-sdk.XXXXXX)"
       tar -xf "$HOME/Downloads/General_NetSDK_Eng_Linux64_IS_V3.060.0000003.0.R.251127.tar.gz" -C "$SDK_DIR"

3. From this repository, query support first. Use the camera's local device
   username and password (the RTSP credentials), **not** the Mibo Smart account:

       python3 tools/dahua-talk-probe --sdk "$SDK_DIR" --camera-ip 192.168.0.9 --user CAMERA_USER --query-only

4. If the output reports `TCP/37777 login OK` and `Selected format ...
   (PCMA/8000)`, stand near the camera and run the audible test:

       python3 tools/dahua-talk-probe --sdk "$SDK_DIR" --camera-ip 192.168.0.9 --user CAMERA_USER

   This second command needs `g++` and `ffmpeg` on the test computer. Both
   commands prompt for the camera password. The probe prints the step and the
   NetSDK error code if a request fails. Note whether the speaker played the
   tone; a successful send call alone does not prove playback. Share the text
   output and the listening result, never the password or raw SDK logs.

The [NetSDK programming guide](https://manuals.plus/m/1e5703103114372088a343ca8f6a8caac19486d8775c8bb44f9a2f94d16cc26f)
specifies the Linux server-mode talk sequence and eight-byte G.711A frame
header used here. This probe does not affect the stable system.

### TCP probe result (2026-10-25)

The probe compiled against the official Linux64 NetSDK and logged in to the
iMX C Black on TCP/37777. The camera reported six talk formats, including
G.711A (`codec=2`) at 8,000 Hz. The probe selected that format, opened a talk
channel, and `CLIENT_TalkSendData` accepted 75 frames of 40 ms each (three
seconds total). The operator confirmed hearing the tone from the camera
speaker. This establishes working local TCP/37777 talkback using NetSDK and
PCMA/8000.

## Browser integration verified

The dashboard now has a press-and-hold Talk button, controlled by
`CAMERAS_TALK_ENABLED`. Browser microphone samples go through an authenticated,
same-origin FastAPI WebSocket to a short-lived NetSDK bridge. The bridge
converts PCM16/8000 to PCMA/8000 and sends 40 ms frames over TCP/37777.
go2rtc continues to handle playback only. The browser route has a session and
CSRF check, accepts one talker at a time, rejects malformed frames, and closes
the bridge on release, disconnect or timeout. A talk session lasts at most 60
seconds. The camera password is stored in a service-readable file and passed
to the bridge through stdin, never through process arguments or browser code.

The feature is disabled on fresh installations until the separate installer in
`install/dahua-talkback.sh` runs on the server with the official SDK archive.
On 2026-10-25, the operator installed the bridge on the Ubuntu server and
confirmed that speech from the authenticated HTTPS dashboard played through
the camera speaker. The first deployment exposed an incomplete Starlette
installation that prevented the web service from starting; reinstalling the
pinned package restored the site. The installer now checks the Python import
and local web health before reporting success. Re-running the main installer
preserves the talkback environment file and native bridge when its source repo
contains these web changes.

## Policy

- keep camera1-talk read-only;
- keep #backchannel=0 on the MediaMTX-derived stream;
- keep the dashboard Talk button disabled by default on fresh installations;
  enable it only with the separate installer;
- do not reintroduce dvrip:// as a workaround.

Any experimental Dahua-enabled go2rtc build should be tested separately before replacing the production binary.
