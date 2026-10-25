// Isolated NetSDK experiment. Never install or run this as a service.
#include <arpa/inet.h>
#include <stddef.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "dhnetsdk.h"

static volatile sig_atomic_t interrupted = 0;

static void stop_on_signal(int) { interrupted = 1; }

static void audio_callback(LLONG, char *, DWORD, BYTE, LDWORD) {}

static void report_error(const char *step) {
    fprintf(stderr, "%s failed: NetSDK error 0x%08x\n", step,
            static_cast<unsigned>(CLIENT_GetLastError()));
}

int main(int argc, char **argv) {
    if (argc != 5) {
        fprintf(stderr, "usage: dahua-talk-probe CAMERA_IP USER PCMA_FILE query|play\n");
        return 2;
    }
    in_addr camera_address;
    if (inet_pton(AF_INET, argv[1], &camera_address) != 1) {
        fprintf(stderr, "CAMERA_IP must be an IPv4 address\n");
        return 2;
    }
    const bool play = strcmp(argv[4], "play") == 0;
    if (!play && strcmp(argv[4], "query") != 0) {
        fprintf(stderr, "mode must be query or play\n");
        return 2;
    }

    // getpass reads /dev/tty without echo. The password never enters argv.
    char *password = getpass("Camera password: ");
    if (password == nullptr || *password == '\0') {
        fprintf(stderr, "No password supplied\n");
        return 2;
    }
    signal(SIGINT, stop_on_signal);
    signal(SIGTERM, stop_on_signal);

    if (!CLIENT_Init(nullptr, 0)) {
        report_error("CLIENT_Init");
        return 1;
    }

    int result = 1;
    LLONG login = 0;
    LLONG talk = 0;
    FILE *audio = nullptr;
    NET_DEVICEINFO_Ex device = {};
    int login_error = 0;
    login = CLIENT_LoginEx2(argv[1], 37777, argv[2], password,
                            EM_LOGIN_SPEC_CAP_TCP, nullptr, &device,
                            &login_error);
    for (volatile char *p = password; *p; ++p) *p = '\0';
    if (!login) {
        fprintf(stderr, "CLIENT_LoginEx2 failed: login error %d, NetSDK error 0x%08x\n",
                login_error, static_cast<unsigned>(CLIENT_GetLastError()));
        goto done;
    }
    puts("TCP/37777 login OK");

    if (!CLIENT_SetDeviceMode(login, DH_TALK_SERVER_MODE, nullptr)) {
        report_error("Set server talk mode");
        goto done;
    }

    {
        DHDEV_TALKFORMAT_LIST formats = {};
        int returned = 0;
        if (!CLIENT_QueryDevState(login, DH_DEVSTATE_TALK_ECTYPE,
                                  reinterpret_cast<char *>(&formats),
                                  sizeof(formats), &returned, 3000)) {
            report_error("Query talk formats");
            goto done;
        }
        if (formats.nSupportNum < 0 || formats.nSupportNum > 64 ||
            returned < static_cast<int>(offsetof(DHDEV_TALKFORMAT_LIST, type) +
                                        formats.nSupportNum * sizeof(formats.type[0]))) {
            fprintf(stderr, "Invalid talk format response: count=%d, bytes=%d\n",
                    formats.nSupportNum, returned);
            goto done;
        }
        printf("Talk formats (%d):\n", formats.nSupportNum);
        int selected = -1;
        for (int i = 0; i < formats.nSupportNum; ++i) {
            const DHDEV_TALKDECODE_INFO &format = formats.type[i];
            printf("  %d: codec=%d rate=%u bits=%d period=%d ms\n", i,
                   static_cast<int>(format.encodeType),
                   static_cast<unsigned>(format.dwSampleRate), format.nAudioBit,
                   format.nPacketPeriod);
            if (selected < 0 && format.encodeType == DH_TALK_G711a &&
                format.dwSampleRate == 8000 &&
                (format.nPacketPeriod == 0 ||
                 (format.nPacketPeriod >= 10 && format.nPacketPeriod <= 200 &&
                  format.nPacketPeriod % 10 == 0))) {
                selected = i;
            }
        }
        if (selected < 0) {
            puts("No supported PCMA/8000 talk format; no audio sent");
            goto done;
        }
        DHDEV_TALKDECODE_INFO chosen = formats.type[selected];
        printf("Selected format %d (PCMA/8000)\n", selected);
        if (!play) {
            puts("Query complete; no audio sent");
            result = 0;
            goto done;
        }

        if (!CLIENT_SetDeviceMode(login, DH_TALK_ENCODE_TYPE, &chosen)) {
            report_error("Set talk encoding");
            goto done;
        }
        NET_SPEAK_PARAM speak = {};
        speak.dwSize = sizeof(speak);
        speak.nMode = 0;
        speak.nSpeakerChannel = 0;
        if (!CLIENT_SetDeviceMode(login, DH_TALK_SPEAK_PARAM, &speak)) {
            report_error("Set speaker mode");
            goto done;
        }
        NET_TALK_TRANSFER_PARAM transfer = {};
        transfer.dwSize = sizeof(transfer);
        transfer.bTransfer = FALSE;
        if (!CLIENT_SetDeviceMode(login, DH_TALK_TRANSFER_MODE, &transfer)) {
            report_error("Set direct talk mode");
            goto done;
        }

        audio = fopen(argv[3], "rb");
        if (!audio) {
            perror("Open test audio");
            goto done;
        }
        talk = CLIENT_StartTalkEx(login, audio_callback, 0);
        if (!talk) {
            report_error("CLIENT_StartTalkEx");
            goto done;
        }
        puts("Talk channel opened; sending 3-second test tone");
        fflush(stdout);

        const int period = chosen.nPacketPeriod ? chosen.nPacketPeriod : 40;
        const size_t samples = static_cast<size_t>(period) * 8;
        unsigned char packet[8 + 1600] = {0, 0, 1, 0xf0, 0x0e, 2, 0, 0};
        packet[6] = static_cast<unsigned char>(samples & 0xff);
        packet[7] = static_cast<unsigned char>((samples >> 8) & 0xff);
        int sent = 0;
        while (!interrupted && fread(packet + 8, 1, samples, audio) == samples) {
            const int length = static_cast<int>(samples + 8);
            const int accepted = CLIENT_TalkSendData(
                talk, reinterpret_cast<char *>(packet), length);
            if (accepted != length) {
                fprintf(stderr, "CLIENT_TalkSendData accepted %d/%d bytes; NetSDK error 0x%08x\n",
                        accepted, length,
                        static_cast<unsigned>(CLIENT_GetLastError()));
                goto done;
            }
            ++sent;
            timespec delay = {period / 1000, (period % 1000) * 1000000L};
            while (!interrupted && nanosleep(&delay, &delay) != 0) {}
        }
        if (ferror(audio)) {
            perror("Read test audio");
            goto done;
        }
        printf("Sent %d audio frames (%d ms each)\n", sent, period);
        result = interrupted || sent == 0 ? 1 : 0;
    }

done:
    if (talk) CLIENT_StopTalkEx(talk);
    if (audio) fclose(audio);
    if (login) CLIENT_Logout(login);
    CLIENT_Cleanup();
    return result;
}
