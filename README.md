# cameras-cassa

Infraestrutura doméstica, auto-hospedada, para câmeras IP.

O projeto recebe streams RTSP de câmeras locais, redistribui vídeo e áudio, grava segmentos contínuos, envia gravações ao Google Drive e oferece um painel HTTPS autenticado para acesso da família dentro ou fora de casa.

## Arquitetura atual

- MediaMTX: ingestão RTSP e gravação segmentada.
- FFmpeg: converte apenas AAC -> Opus para o stream WebRTC; o vídeo H.264 é copiado sem recodificação.
- go2rtc: reprodução WebRTC. O HTTP API permanece em loopback.
- FastAPI: login, sessões e proxy autenticado do go2rtc.
- SQLite + Argon2id: usuários locais da família.
- Tailscale Funnel:
  - HTTPS 443 para o painel autenticado;
  - TCP 10000 para o transporte WebRTC.
- rclone: upload para Google Drive e retenção remota.
- systemd: mantém serviços, retry, buffer guard e retenção.
- index.html e privacy.html na raiz: páginas públicas usadas pelo OAuth do Google; não são o painel doméstico.

## Talkback

Por padrão, o botão de falar está desabilitado. No servidor testado, ele foi
ativado pela instalação opcional.

A iMX C Black não anunciou um backchannel de áudio pelo RTSP/ONVIF. O antigo experimento dvrip:// usava a família de protocolo errada.

O go2rtc fixado neste projeto ainda não oferece suporte Dahua raw TCP/37777.
A fala usa uma ponte opcional pela FastAPI e pelo NetSDK da Dahua.

Uma captura do Mibo Smart confirmou fala do celular até o alto-falante da
câmera por UDP/PTCP na LAN, com quadros DHAV de áudio PCMA/8000. Um teste
isolado com o NetSDK da Dahua também confirmou talkback local por TCP/37777:
a câmera aceitou 75 quadros de áudio PCMA/8000 e reproduziu o tom de teste.
Em 2026-10-25, a ponte opcional foi instalada no servidor e a voz enviada pelo
navegador foi ouvida no alto-falante da câmera. Em novas instalações, a fala
continua desligada até a instalação opcional.
O go2rtc continua responsável apenas pela reprodução.

Veja docs/talkback.md.

## Instalação rápida

Em um Ubuntu Server novo:

    git clone https://github.com/andrevinov/cameras-cassa.git
    cd cameras-cassa
    sudo ./install.sh

O instalador pede IP/usuário/senha da câmera, cria o primeiro usuário do site e conduz as autenticações de rclone/Tailscale quando necessário.

Veja docs/setup.md, docs/architecture.md, docs/authentication.md e docs/talkback.md.

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

O go2rtc HTTP API fica em loopback. O navegador só chega ao signaling através do proxy autenticado da aplicação.
