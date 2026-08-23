# -*- coding: utf-8 -*-
"""
행정규칙에서 '약관'을 수집해 조항 분리기의 테스트 코퍼스로 쓴다.

왜 이걸 쓰는가: 파서를 검증하려면 **실제 약관 형식**이 필요하다. 직접 만든 샘플은
형식의 다양성을 반영하지 못해 "잘 되는 것처럼 보이는" 파서가 나온다.

실행:  python src/collect_terms.py
출력:  data/terms/terms.jsonl

주의: 이건 법제처가 정제해 준 데이터다. 실제 사용자가 올릴 계약서(PDF·이미지·워드)는
훨씬 험하다. 여기서 잘 된다고 실서비스에서 된다는 뜻이 아니다.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OC = os.getenv("LAW_OC")
BASE = "https://www.law.go.kr/DRF"
UA = {"User-Agent": "Mozilla/5.0"}
SLEEP = 0.4

OUT = ROOT / "data" / "terms" / "terms.jsonl"


def clean(s) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(s or "")))).strip()


def as_list(x) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def search_terms() -> list[dict]:
    """행정규칙에서 '약관'으로 검색. 이용약관·표준약관이 여기 들어 있다."""
    out, page = [], 1
    while True:
        r = requests.get(f"{BASE}/lawSearch.do", timeout=30, headers=UA,
                         params={"OC": OC, "target": "admrul", "type": "JSON",
                                 "query": "약관", "display": 100, "page": page})
        r.raise_for_status()
        rows = as_list(r.json()["AdmRulSearch"].get("admrul"))
        out.extend(rows)
        time.sleep(SLEEP)
        if len(rows) < 100:
            return out
        page += 1


def fetch_body(rule_id: str) -> dict | None:
    r = requests.get(f"{BASE}/lawService.do", timeout=30, headers=UA,
                     params={"OC": OC, "target": "admrul", "ID": rule_id, "type": "JSON"})
    time.sleep(SLEEP)
    if r.status_code != 200 or len(r.text) < 300:
        return None
    try:
        return list(r.json().values())[0]
    except Exception:
        return None


def main():
    if not OC:
        raise SystemExit("[!] .env의 LAW_OC가 비어 있습니다.")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    rows = search_terms()
    print(f"행정규칙 '약관' 검색 → {len(rows)}건")

    saved = skipped = 0
    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            rid = str(row.get("행정규칙일련번호"))
            name = clean(row.get("행정규칙명"))
            body = fetch_body(rid)
            if body is None:
                skipped += 1
                continue
            paras = [clean(x) for x in as_list(body.get("조문내용")) if clean(x)]
            if not paras:
                skipped += 1
                continue
            info = body.get("행정규칙기본정보", {})
            f.write(json.dumps({
                "id": rid,
                "이름": name,
                "발령일자": info.get("발령일자"),
                "담당부서": info.get("담당부서기관명"),
                "조문내용": paras,
            }, ensure_ascii=False) + "\n")
            saved += 1

    print(f"저장 {saved}건 / 건너뜀 {skipped}건")
    print(f"→ {OUT.relative_to(ROOT)}")
    print(f"수집시각 {datetime.now(timezone.utc).astimezone().isoformat()}")


if __name__ == "__main__":
    main()
