# cameras-cassa

Infraestrutura doméstica, auto-hospedada, para câmeras IP.

O projeto recebe streams RTSP de câmeras locais, redistribui vídeo e áudio, oferece talkback quando a câmera suporta backchannel, grava segmentos contínuos e envia as gravações ao Google Drive com retenção configurável.

## Arquitetura atual

- MediaMTX: ingestão RTSP e gravação segmentada.
- FFmpeg: converte apenas AAC -> Opus para o stream WebRTC; o vídeo H.264 é copiado sem recodificação.
- go2rtc: camada interativa e talkback via DVRIP/porta 37777.
- FastAPI: login, sessões e proxy autenticado do go2rtc.
- SQLite + Argon2id: usuários locais da família.
- Tailscale Serve: HTTPS privado durante a fase atual; futuramente a mesma aplicação pode ficar atrás de um domínio público/reverse proxy.
- rclone: upload para Google Drive e retenção remota.
- systemd: mantém serviços, retry, buffer guard e retenção.
- index.html e privacy.html na raiz: páginas públicas usadas pelo OAuth do Google; não são o painel doméstico.

## Instalação rápida

Em um Ubuntu Server novo:

    git clone https://github.com/andrevinov/cameras-cassa.git
    cd cameras-cassa
    sudo ./install.sh

O instalador pede IP/usuário/senha da câmera, cria o primeiro usuário do site e conduz as autenticações de rclone/Tailscale quando necessário.

Veja docs/setup.md, docs/architecture.md e docs/authentication.md.

## Usuários do site

    sudo -u andre camera-user add monalise
    sudo -u andre camera-user passwd monalise
    sudo -u andre camera-user disable monalise
    sudo -u andre camera-user enable monalise
    sudo -u andre camera-user list

## Segurança

Este repositório é público por causa do GitHub Pages.

Nunca commite:
- senhas de câmeras;
- senhas de usuários do site;
- client_secret OAuth;
- access_token ou refresh_token;
- rclone.conf;
- banco users.sqlite3;
- session-secret;
- arquivos /etc/mediamtx.env ou /etc/go2rtc.yaml gerados.

O go2rtc HTTP API fica em loopback. O navegador só chega nele através do proxy autenticado da aplicação.
