from __future__ import annotations

import asyncio
import os
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Annotated

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CAMERAS_USERS_DB", "/var/lib/cameras-cassa/users.sqlite3"))
SECRET_FILE = Path(
    os.environ.get("CAMERAS_SESSION_SECRET_FILE", "/etc/cameras-cassa/session-secret")
)
GO2RTC_BASE = os.environ.get("GO2RTC_BASE", "http://127.0.0.1:1984").rstrip("/")
GO2RTC_WS_BASE = GO2RTC_BASE.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
SESSION_MAX_AGE = int(os.environ.get("CAMERAS_SESSION_MAX_AGE", str(7 * 24 * 60 * 60)))

if not SECRET_FILE.is_file():
    raise RuntimeError(f"Session secret file not found: {SECRET_FILE}")

SESSION_SECRET = SECRET_FILE.read_text(encoding="utf-8").strip()
if len(SESSION_SECRET) < 32:
    raise RuntimeError("Session secret is unexpectedly short")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="cameras_session",
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=True,
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
password_hasher = PasswordHasher()
login_attempts: dict[str, deque[float]] = defaultdict(deque)
login_lock = asyncio.Lock()


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                auth_version INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        if "auth_version" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 1")


init_db()


def authenticated(request: Request) -> bool:
    username = request.session.get("user")
    version = request.session.get("auth_version")
    if not username or version is None:
        return False
    with db() as connection:
        row = connection.execute(
            "SELECT enabled, auth_version FROM users WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
    return bool(row and row["enabled"] and row["auth_version"] == version)


def websocket_authenticated(client: WebSocket) -> bool:
    username = client.session.get("user")
    version = client.session.get("auth_version")
    if not username or version is None:
        return False
    with db() as connection:
        row = connection.execute(
            "SELECT enabled, auth_version FROM users WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
    return bool(row and row["enabled"] and row["auth_version"] == version)


def client_key(request: Request, username: str) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",", 1)[0].strip() if forwarded else ""
    if not ip and request.client:
        ip = request.client.host
    return f"{ip}:{username.casefold()}"


async def rate_limited(key: str) -> bool:
    now = time.monotonic()
    window = 5 * 60
    limit = 8
    async with login_lock:
        attempts = login_attempts[key]
        while attempts and now - attempts[0] > window:
            attempts.popleft()
        if len(attempts) >= limit:
            return True
        attempts.append(now)
        return False


async def clear_attempts(key: str) -> None:
    async with login_lock:
        login_attempts.pop(key, None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "media-src 'self' blob:; "
        "connect-src 'self' ws: wss:; "
        "frame-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; form-action 'self'",
    )
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if authenticated(request):
        return RedirectResponse("/", status_code=303)
    request.session.setdefault("csrf", secrets.token_urlsafe(24))
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "csrf": request.session["csrf"]},
    )


@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
):
    if not secrets.compare_digest(csrf, str(request.session.get("csrf", ""))):
        return Response(status_code=400)

    username = username.strip()
    key = client_key(request, username)

    if await rate_limited(key):
        await asyncio.sleep(1.0)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Muitas tentativas. Aguarde alguns minutos.",
                "csrf": request.session["csrf"],
            },
            status_code=429,
        )

    with db() as connection:
        row = connection.execute(
            "SELECT username, password_hash, enabled, auth_version FROM users WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()

    valid = False
    if row and row["enabled"]:
        try:
            valid = password_hasher.verify(row["password_hash"], password)
        except (VerifyMismatchError, InvalidHashError):
            valid = False

    if not valid:
        await asyncio.sleep(0.45)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Usuário ou senha inválidos.", "csrf": request.session["csrf"]},
            status_code=401,
        )

    if password_hasher.check_needs_rehash(row["password_hash"]):
        with db() as connection:
            connection.execute(
                "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ? COLLATE NOCASE",
                (password_hasher.hash(password), row["username"]),
            )

    request.session.clear()
    request.session["user"] = row["username"]
    request.session["auth_version"] = row["auth_version"]
    request.session["csrf"] = secrets.token_urlsafe(24)
    await clear_attempts(key)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
async def logout(request: Request, csrf: Annotated[str, Form()]):
    if not secrets.compare_digest(csrf, str(request.session.get("csrf", ""))):
        return Response(status_code=400)
    request.session.clear()
    response = RedirectResponse("/login", status_code=303)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not authenticated(request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)
    response = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"username": request.session["user"], "csrf": request.session["csrf"]},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "content-encoding",
}


@app.api_route(
    "/go2rtc/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def go2rtc_http_proxy(request: Request, path: str):
    if not authenticated(request):
        return Response(status_code=401)

    target = f"{GO2RTC_BASE}/{path}"
    if request.url.query:
        target += f"?{request.url.query}"

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        upstream = await client.request(
            request.method,
            target,
            headers=headers,
            content=await request.body(),
        )

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in HOP_BY_HOP
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=None,
    )


@app.websocket("/go2rtc/api/ws")
async def go2rtc_websocket_proxy(client: WebSocket):
    if not websocket_authenticated(client):
        await client.close(code=4401)
        return

    await client.accept()
    target = f"{GO2RTC_WS_BASE}/api/ws"
    if client.url.query:
        target += f"?{client.url.query}"

    try:
        async with ws_connect(target, max_size=None) as upstream:

            async def client_to_upstream() -> None:
                try:
                    while True:
                        message = await client.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        if message.get("text") is not None:
                            await upstream.send(message["text"])
                        elif message.get("bytes") is not None:
                            await upstream.send(message["bytes"])
                except WebSocketDisconnect:
                    pass

            async def upstream_to_client() -> None:
                try:
                    async for message in upstream:
                        if isinstance(message, str):
                            await client.send_text(message)
                        else:
                            await client.send_bytes(message)
                except ConnectionClosed:
                    pass

            tasks = [
                asyncio.create_task(client_to_upstream()),
                asyncio.create_task(upstream_to_client()),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await asyncio.gather(*done, return_exceptions=True)
    finally:
        try:
            await client.close()
        except RuntimeError:
            pass
