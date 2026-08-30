# -*- coding: utf-8 -*-
"""
후기 게시판 저장소. **작성자 본인과 운영자만 읽을 수 있다.**

지인에게 써보게 하고 후기를 받으려고 만들었다. 실제 계약서에서 어떻게 도는지
모르는 것이 이 프로젝트의 최대 숙제인데, 그것을 푸는 통로다.

## 왜 비밀글인가

후기에는 "내 전세계약서를 넣어 봤는데" 같은 개인 사정이 섞인다. 다른 사람이
읽을 수 있으면 솔직한 후기가 안 나온다. 그래서 **작성자는 자기 글만, 운영자는
전부** 보게 했다.

## 로그인 없이 본인을 어떻게 확인하나

이름과 비밀번호 네 자리를 받는다. 지인 몇 명이 쓰는 시험용이므로 계정 체계를
만들 이유가 없다. 다만 **비밀번호를 그대로 저장하지 않는다** — pbkdf2 로 해시해
둔다. 게시판이 털려도 비밀번호 자체는 나오지 않아야 한다.

운영자는 `.env` 의 `ADMIN_KEY` 로 확인한다. 코드에 넣지 않는다.

## 약관 입력과는 다르다

**대조에 넣은 약관 본문은 저장하지 않는다.** 저장하는 것은 여기 후기뿐이다.
화면에서도 그 구분을 밝힌다.
"""

from __future__ import annotations

import hashlib
import os
from contextlib import closing
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "feedback.db"          # gitignore 한다. 후기는 남의 글이다.
ITER = 120_000


def _hash(pw: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), ITER).hex()


def _conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        salt TEXT NOT NULL,
        pw   TEXT NOT NULL,
        body TEXT NOT NULL,
        created TEXT NOT NULL)""")
    return c


def add(name: str, pw: str, body: str) -> int:
    salt = secrets.token_hex(8)
    with closing(_conn()) as c, c:
        cur = c.execute(
            "INSERT INTO feedback (name, salt, pw, body, created) VALUES (?,?,?,?,?)",
            (name.strip(), salt, _hash(pw, salt), body.strip(),
             datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")))
        return cur.lastrowid


def mine(name: str, pw: str) -> list[dict]:
    """이름과 비밀번호가 맞는 글만 준다. 비밀번호가 틀리면 빈 목록이다."""
    with closing(_conn()) as c, c:
        rows = c.execute("SELECT * FROM feedback WHERE name = ? ORDER BY id DESC",
                         (name.strip(),)).fetchall()
    return [{"id": r["id"], "이름": r["name"], "내용": r["body"], "작성": r["created"]}
            for r in rows
            if secrets.compare_digest(_hash(pw, r["salt"]).encode(), r["pw"].encode())]


def all_of(key: str) -> list[dict] | None:
    """운영자만. 키가 없거나 틀리면 None 을 준다 — 빈 목록과 구분해야 한다."""
    admin = os.getenv("ADMIN_KEY", "")
    # compare_digest 는 비ASCII 문자열에서 예외를 낸다. 한글 키가 오면 터진다.
    # 바이트로 비교해야 한글 키도, 공격자가 보낸 한글도 안전하게 처리된다.
    if not admin or not secrets.compare_digest((key or "").encode(), admin.encode()):
        return None
    with closing(_conn()) as c, c:
        rows = c.execute("SELECT * FROM feedback ORDER BY id DESC").fetchall()
    return [{"id": r["id"], "이름": r["name"], "내용": r["body"], "작성": r["created"]}
            for r in rows]


def count() -> int:
    with closing(_conn()) as c, c:
        return c.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
