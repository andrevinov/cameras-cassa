// One-shot stdin -> Dahua NetSDK talk channel. Run only behind the web app.
#include <arpa/inet.h>
#include <errno.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "dhnetsdk.h"

static volatile sig_atomic_t stopping = 0;
static void stop_on_signal(int) { stopping = 1; }
static void audio_callback(LLONG, char *, DWORD, BYTE, LDWORD) {}

static bool read_full(void *buffer, size_t size) {
    auto *bytes = static_cast<unsigned char *>(buffer);
    while (size > 0 && !stopping) {
        ssize_t n = read(STDIN_FILENO, bytes, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return false;
        bytes += n;
        size -= static_cast<size_t>(n);
    }
    return size == 0;
}

static int fail(const char *step) {
    printf("ERROR %s 0x%08x\n", step,
           static_cast<unsigned>(CLIENT_GetLastError()));
    fflush(stdout);
    return 1;
}

static unsigned char linear_to_alaw(int16_t sample) {
    // ITU G.711 A-law, using the 13-bit companding input convention.
    int value = sample >> 3;
    const int mask = value >= 0 ? 0xd5 : 0x55;
    if (value < 0) value = -value - 1;
    static const int segment_end[] = {0x1f, 0x3f, 0x7f, 0xff,
                                      0x1ff, 0x3ff, 0x7ff, 0xfff};
    int segment = 0;
    while (segment < 8 && value > segment_end[segment]) ++segment;
    if (segment >= 8) return static_cast<unsigned char>(0x7f ^ mask);
    int code = segment << 4;
    code |= segment < 2 ? (value >> 1) & 0x0f : (value >> segment) & 0x0f;
    return static_cast<unsigned char>(code ^ mask);
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    in_addr camera_ip;
    if (inet_pton(AF_INET, argv[1], &camera_ip) != 1) return 2;
    signal(SIGINT, stop_on_signal);
    signal(SIGTERM, stop_on_signal);
    signal(SIGPIPE, SIG_IGN);

    // Input starts with a little-endian password length, then the password.
    // Remaining input is 640-byte frames: 320 little-endian PCM16 samples.
    unsigned char length_bytes[2];
    if (!read_full(length_bytes, sizeof(length_bytes))) return 2;
    const size_t password_length = length_bytes[0] | (length_bytes[1] << 8);
    if (password_length == 0 || password_length > 256) return 2;
    char password[257] = {};
    if (!read_full(password, password_length)) return 2;

    if (!CLIENT_Init(nullptr, 0)) return fail("init");
    int result = 1;
    LLONG login = 0;
    LLONG talk = 0;
    NET_DEVICEINFO_Ex device = {};
    int login_error = 0;
    login = CLIENT_LoginEx2(argv[1], 37777, argv[2], password,
                            EM_LOGIN_SPEC_CAP_TCP, nullptr, &device,
                            &login_error);
    for (volatile char *p = password; *p; ++p) *p = '\0';
    if (!login) {
        printf("ERROR login %d 0x%08x\n", login_error,
               static_cast<unsigned>(CLIENT_GetLastError()));
        fflush(stdout);
        goto done;
    }
    if (!CLIENT_SetDeviceMode(login, DH_TALK_SERVER_MODE, nullptr)) {
        fail("server_mode");
        goto done;
    }
    {
        DHDEV_TALKFORMAT_LIST formats = {};
        int returned = 0;
        if (!CLIENT_QueryDevState(login, DH_DEVSTATE_TALK_ECTYPE,
                                  reinterpret_cast<char *>(&formats),
                                  sizeof(formats), &returned, 3000)) {
            fail("formats");
            goto done;
        }
        if (formats.nSupportNum < 0 || formats.nSupportNum > 64 ||
            returned < static_cast<int>(offsetof(DHDEV_TALKFORMAT_LIST, type) +
                                        formats.nSupportNum * sizeof(formats.type[0]))) {
            puts("ERROR invalid_formats");
            fflush(stdout);
            goto done;
        }
        int selected = -1;
        for (int i = 0; i < formats.nSupportNum; ++i) {
            const auto &format = formats.type[i];
            if (format.encodeType == DH_TALK_G711a &&
                format.dwSampleRate == 8000 &&
                (format.nPacketPeriod == 0 || format.nPacketPeriod == 40)) {
                selected = i;
                break;
            }
        }
        if (selected < 0) {
            puts("ERROR no_pcma_8000_40ms");
            fflush(stdout);
            goto done;
        }
        DHDEV_TALKDECODE_INFO chosen = formats.type[selected];
        if (!CLIENT_SetDeviceMode(login, DH_TALK_ENCODE_TYPE, &chosen)) {
            fail("encoding");
            goto done;
        }
        NET_SPEAK_PARAM speak = {};
        speak.dwSize = sizeof(speak);
        speak.nMode = 0;
        speak.nSpeakerChannel = 0;
        if (!CLIENT_SetDeviceMode(login, DH_TALK_SPEAK_PARAM, &speak)) {
            fail("speaker");
            goto done;
        }
        NET_TALK_TRANSFER_PARAM transfer = {};
        transfer.dwSize = sizeof(transfer);
        transfer.bTransfer = FALSE;
        if (!CLIENT_SetDeviceMode(login, DH_TALK_TRANSFER_MODE, &transfer)) {
            fail("transfer");
            goto done;
        }
        talk = CLIENT_StartTalkEx(login, audio_callback, 0);
        if (!talk) {
            fail("start");
            goto done;
        }
        puts("READY");
        fflush(stdout);

        unsigned char packet[328] = {0, 0, 1, 0xf0, 0x0e, 2, 0x40, 1};
        unsigned char pcm[640];
        while (!stopping && read_full(pcm, sizeof(pcm))) {
            for (int i = 0; i < 320; ++i) {
                const int16_t sample = static_cast<int16_t>(
                    static_cast<uint16_t>(pcm[i * 2]) |
                    (static_cast<uint16_t>(pcm[i * 2 + 1]) << 8));
                packet[8 + i] = linear_to_alaw(sample);
            }
            if (CLIENT_TalkSendData(talk, reinterpret_cast<char *>(packet),
                                    sizeof(packet)) != sizeof(packet)) {
                fail("send");
                goto done;
            }
        }
        result = 0;
    }

done:
    if (talk) CLIENT_StopTalkEx(talk);
    if (login) CLIENT_Logout(login);
    CLIENT_Cleanup();
    return result;
}
