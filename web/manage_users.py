from __future__ import annotations

import argparse
import getpass
import os
import re
import sqlite3
import sys
from pathlib import Path

from argon2 import PasswordHasher

DB_PATH = Path(os.environ.get("CAMERAS_USERS_DB", "/var/lib/cameras-cassa/users.sqlite3"))
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
ph = PasswordHasher()


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
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
    return connection


def require_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise SystemExit(
            "Username must be 1-64 characters: letters, digits, dot, underscore or hyphen."
        )
    return username


def read_password() -> str:
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match.")
    if len(first) < 10:
        raise SystemExit("Password must have at least 10 characters.")
    return first


def add_user(username: str) -> None:
    username = require_username(username)
    password_hash = ph.hash(read_password())
    try:
        with db() as connection:
            connection.execute(
                "INSERT INTO users (username, password_hash, enabled) VALUES (?, ?, 1)",
                (username, password_hash),
            )
    except sqlite3.IntegrityError as exc:
        raise SystemExit(f"User already exists: {username}") from exc
    print(f"Created user: {username}")


def set_password(username: str) -> None:
    username = require_username(username)
    password_hash = ph.hash(read_password())
    with db() as connection:
        cursor = connection.execute(
            "UPDATE users SET password_hash = ?, auth_version = auth_version + 1, updated_at = CURRENT_TIMESTAMP WHERE username = ? COLLATE NOCASE",
            (password_hash, username),
        )
        if cursor.rowcount == 0:
            raise SystemExit(f"Unknown user: {username}")
    print(f"Password updated: {username}")


def set_enabled(username: str, enabled: bool) -> None:
    username = require_username(username)
    with db() as connection:
        cursor = connection.execute(
            "UPDATE users SET enabled = ?, auth_version = auth_version + 1, updated_at = CURRENT_TIMESTAMP WHERE username = ? COLLATE NOCASE",
            (1 if enabled else 0, username),
        )
        if cursor.rowcount == 0:
            raise SystemExit(f"Unknown user: {username}")
    print(f"{'Enabled' if enabled else 'Disabled'} user: {username}")


def list_users() -> None:
    with db() as connection:
        rows = connection.execute(
            "SELECT username, enabled, created_at, updated_at FROM users ORDER BY username COLLATE NOCASE"
        ).fetchall()
    for row in rows:
        state = "enabled" if row["enabled"] else "disabled"
        print(
            f"{row['username']}\t{state}\tcreated={row['created_at']}\tupdated={row['updated_at']}"
        )


def has_users() -> int:
    with db() as connection:
        count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return 0 if count else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage cameras-cassa web users")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("username")

    p_passwd = sub.add_parser("passwd")
    p_passwd.add_argument("username")

    p_enable = sub.add_parser("enable")
    p_enable.add_argument("username")

    p_disable = sub.add_parser("disable")
    p_disable.add_argument("username")

    sub.add_parser("list")
    sub.add_parser("has-users")

    args = parser.parse_args()

    if args.command == "add":
        add_user(args.username)
    elif args.command == "passwd":
        set_password(args.username)
    elif args.command == "enable":
        set_enabled(args.username, True)
    elif args.command == "disable":
        set_enabled(args.username, False)
    elif args.command == "list":
        list_users()
    elif args.command == "has-users":
        sys.exit(has_users())


if __name__ == "__main__":
    main()
