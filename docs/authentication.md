# Authentication

The dashboard uses application-level authentication so the camera page and the proxied go2rtc endpoints share the same session boundary.

## Components

- FastAPI application on 127.0.0.1:8090.
- SQLite user database at /var/lib/cameras-cassa/users.sqlite3.
- Argon2id password hashes via argon2-cffi.
- Signed, Secure, HttpOnly session cookie.
- CSRF tokens on login/logout forms.
- go2rtc HTTP and WebSocket traffic proxied through the authenticated application under /go2rtc/.
- Simple login rate limiting: 8 attempts per 5 minutes per username/client key.

## User administration

Create a user:

    sudo -u andre camera-user add monalise

Change password:

    sudo -u andre camera-user passwd monalise

Disable/enable:

    sudo -u andre camera-user disable monalise
    sudo -u andre camera-user enable monalise

List accounts:

    sudo -u andre camera-user list

Passwords are never stored in plaintext. Password changes and account disable/enable actions increment an auth version, invalidating existing sessions.

## Security boundary

Do not expose go2rtc port 1984 publicly. The browser reaches go2rtc signaling only through /go2rtc/ on the authenticated application.

Public access is provided by Tailscale Funnel:

    sudo tailscale funnel --bg --https=443 http://127.0.0.1:8090

The separate raw TCP Funnel on port 10000 carries WebRTC media transport, not application HTTP or login traffic:

    sudo tailscale funnel --bg --tcp=10000 tcp://127.0.0.1:8555

Do not add a separate HTTP Funnel mapping for /go2rtc because that would bypass the application authentication boundary.
