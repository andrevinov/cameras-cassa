# AGENTS.md

## Objetivo

Este repositório contém a infraestrutura de câmeras domésticas de André. Priorize simplicidade, auditabilidade, baixo consumo de recursos e ausência de vendor lock-in.

## Regras invariáveis

1. Nunca adicionar segredos ao Git.
2. A raiz index.html/privacy.html pertence ao GitHub Pages usado no OAuth do Google. Não substituir pela interface doméstica.
3. A interface doméstica vive em web/.
4. O servidor alvo é Ubuntu Server x86_64.
5. Serviços rodam como usuário não-root sempre que possível.
6. Câmeras devem ser tratadas como dispositivos da LAN; não expor RTSP, go2rtc ou MediaMTX à internet.
7. Upload só pode apagar o arquivo local depois de transferência confirmada.
8. Alterações destrutivas no Drive devem ter modo de teste ou documentação clara.
9. O instalador deve permanecer idempotente: executá-lo novamente não deve quebrar uma instalação existente.

## Stack

- MediaMTX 1.21.2
- go2rtc 1.9.14
- FFmpeg
- rclone
- systemd
- Python http.server para o painel local

## Fluxo

camera1 -> RTSP H264/AAC -> MediaMTX path camera1
MediaMTX camera1 -> gravação fMP4 em segmentos de 10 minutos
MediaMTX camera1 -> FFmpeg (video copy, AAC->Opus) -> MediaMTX camera1-web
camera1-web + DVRIP backchannel -> go2rtc camera1-talk
go2rtc -> browser
segmento finalizado -> rclone moveto -> Google Drive

## Segredos

Arquivos reais:
- /etc/cameras-cassa/secrets.env
- /etc/mediamtx.env
- /etc/go2rtc.yaml
- ~/.config/rclone/rclone.conf

O repo contém apenas exemplos com placeholders.

## Verificações mínimas antes de commit

- bash -n install.sh scripts/*
- conferir que grep não encontra senhas/tokens reais
- evitar hardcode do usuário andre e do IP 192.168.0.10 em scripts de infraestrutura
