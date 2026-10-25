# AGENTS.md

## Objetivo

Este repositório contém a infraestrutura de câmeras domésticas de André. Priorize simplicidade, auditabilidade, baixo consumo de recursos e ausência de vendor lock-in.

## Regras invariáveis

1. Nunca adicionar segredos ao Git.
2. A raiz index.html/privacy.html pertence ao GitHub Pages usado no OAuth do Google. Não substituir pela interface doméstica.
3. A interface doméstica vive em web/ e requer autenticação.
4. O servidor alvo é Ubuntu Server x86_64.
5. Serviços rodam como usuário não-root sempre que possível.
6. Câmeras devem ser tratadas como dispositivos da LAN; não expor RTSP, go2rtc HTTP API ou MediaMTX diretamente à internet.
7. go2rtc:1984 deve permanecer em loopback. A aplicação web autentica e faz proxy de HTTP/WebSocket em /go2rtc/.
8. O acesso público atual usa Tailscale Funnel: HTTPS 443 para FastAPI e TCP 10000 para transporte WebRTC.
9. Talkback está desabilitado na configuração estável. Não reintroduzir dvrip:// para a iMX C. Consulte docs/talkback.md.
10. Upload só pode apagar o arquivo local depois de transferência confirmada.
11. Alterações destrutivas no Drive devem ter modo de teste ou documentação clara.
12. O instalador deve permanecer idempotente: executá-lo novamente não deve quebrar uma instalação existente.

## Stack

- MediaMTX 1.21.2
- go2rtc 1.9.14
- FFmpeg
- FastAPI / Uvicorn
- SQLite / Argon2id
- Tailscale Funnel
- rclone
- systemd

## Fluxo

camera1 -> RTSP H264/AAC -> MediaMTX path camera1
MediaMTX camera1 -> gravação fMP4 em segmentos de 10 minutos
MediaMTX camera1 -> FFmpeg (video copy, AAC->Opus) -> MediaMTX camera1-web
MediaMTX camera1-web -> go2rtc camera1-talk (read-only)
browser -> HTTPS Funnel -> FastAPI session -> /go2rtc proxy -> go2rtc signaling
browser WebRTC media -> TCP Funnel :10000 -> go2rtc :8555/tcp
segmento finalizado -> rclone moveto -> Google Drive

## Talkback

Estado comprovado:
- microfone do navegador chega ao go2rtc;
- RTSP/ONVIF da iMX C anuncia apenas recvonly;
- dvrip:// foi uma hipótese incorreta para a porta Dahua/Intelbras 37777;
- suporte futuro deve seguir o protocolo Dahua raw TCP/37777, testado separadamente antes de produção.

Veja docs/talkback.md.

## Autenticação

- Banco: /var/lib/cameras-cassa/users.sqlite3
- Hash: Argon2id
- Sessão: cookie Secure/HttpOnly, assinado
- CSRF: login/logout
- O stream não pode ser acessível por uma rota externa que contorne FastAPI.

## Segredos

Arquivos reais:
- /etc/cameras-cassa/secrets.env
- /etc/cameras-cassa/session-secret
- /etc/mediamtx.env
- /etc/go2rtc.yaml
- ~/.config/rclone/rclone.conf

O repo contém apenas exemplos com placeholders.

## Verificações mínimas antes de commit

- bash -n install.sh install/*.sh scripts/*
- python -m py_compile web/app.py web/manage_users.py
- conferir que grep não encontra senhas/tokens reais
- evitar hardcode do usuário andre e do IP 192.168.0.10 em scripts de infraestrutura
