# cameras-cassa

Infraestrutura doméstica, auto-hospedada, para câmeras IP.

O projeto recebe streams RTSP de câmeras locais, redistribui vídeo e áudio na rede doméstica, oferece talkback quando a câmera suporta backchannel, grava segmentos contínuos e envia as gravações ao Google Drive com retenção configurável.

## Arquitetura atual

- MediaMTX: ingestão RTSP, HLS/WebRTC e gravação segmentada.
- FFmpeg: converte apenas AAC -> Opus para o stream WebRTC; o vídeo H.264 é copiado sem recodificação.
- go2rtc: camada interativa e talkback via DVRIP/porta 37777.
- rclone: upload para Google Drive e retenção remota.
- systemd: mantém serviços, retry, buffer guard e retenção.
- web/: painel local da casa.
- index.html e privacy.html na raiz: páginas públicas usadas pelo OAuth do Google; não são o painel doméstico.

## Instalação rápida

Em um Ubuntu Server novo:

    git clone https://github.com/andrevinov/cameras-cassa.git
    cd cameras-cassa
    sudo ./install.sh

O instalador pede IP/usuário/senha da câmera e parâmetros locais. Segredos nunca devem ser commitados.

A autenticação OAuth do Google Drive continua sendo uma etapa interativa do rclone.

Veja docs/setup.md e docs/architecture.md.

## Segurança

Este repositório é público por causa do GitHub Pages.

Nunca commite:
- senhas de câmeras;
- client_secret OAuth;
- access_token ou refresh_token;
- rclone.conf;
- arquivos /etc/mediamtx.env ou /etc/go2rtc.yaml gerados;
- certificados/chaves privadas.

A configuração real fica somente no servidor em /etc e no ~/.config/rclone do usuário de serviço.
