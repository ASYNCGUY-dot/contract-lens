# -*- coding: utf-8 -*-
"""
약관규제법 제6~14조를 참조조문으로 하는 판례를 수집해 로컬에 저장한다.

한 번 받아두면 이후 개발과 채점이 API 없이 된다. 제출물의 '실행 재현성'에도 이게 필요하다.

실행:  python src/collect_cases.py
출력:
  data/cases/index.json     조문 → 판례일련번호[] 매핑 (JO 필터 조회 결과 그대로)
  data/cases/bodies.jsonl   판례 본문 한 줄에 하나

**조문 → 판례 매핑을 우리가 만들지 않는다.** 법제처가 참조조문으로 붙여둔 것을
`JO` 필터로 조회할 뿐이다. 그래서 이 부분은 우리가 틀릴 여지가 없다.

증분 수집이라 다시 돌리면 이미 받은 본문은 건너뛴다.
"""

from __future__ import annotations

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

LAW_NAME = "약관의 규제에 관한 법률"
ART_FROM, ART_TO = 6, 14

# 일일 호출 한도가 확인되지 않았다. 넉넉히 쉬면서 돈다.
SLEEP = 0.4

OUT_DIR = ROOT / "data" / "cases"
INDEX = OUT_DIR / "index.json"
BODIES = OUT_DIR / "bodies.jsonl"

# 판례 본문에서 어떤 조문이 걸렸는지 뽑는다. 참조조문 필드가 이런 형태로 온다:
#   "[1] 소액사건심판법 제3조 제2호 / [2] 상법 제638조의3 제1항, 약관의 규제에 관한 법률 제3조"
REF_RE = re.compile(rf"{re.escape(LAW_NAME)}\s*제(\d+)조(?:\s*제(\d+)항)?(?:\s*제(\d+)호)?")


def as_list(x) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def search_by_article(article_no: int) -> list[dict]:
    """JO 참조조문 필터로 한 조문의 판례 목록을 전부 받는다."""
    jo = f"{LAW_NAME} 제{article_no}조"
    out, page = [], 1
    while True:
        r = requests.get(f"{BASE}/lawSearch.do", timeout=30, headers=UA,
                         params={"OC": OC, "target": "prec", "type": "JSON",
                                 "JO": jo, "display": 100, "page": page})
        r.raise_for_status()
        rows = as_list(r.json()["PrecSearch"].get("prec"))
        out.extend(rows)
        time.sleep(SLEEP)
        if len(rows) < 100:
            return out
        page += 1


def fetch_body(case_id: str) -> dict | None:
    r = requests.get(f"{BASE}/lawService.do", timeout=30, headers=UA,
                     params={"OC": OC, "target": "prec", "ID": case_id, "type": "JSON"})
    time.sleep(SLEEP)
    if r.status_code != 200 or len(r.text) < 200:
        return None          # "일치하는 판례가 없습니다" 같은 짧은 응답
    try:
        return list(r.json().values())[0]
    except Exception:
        return None


def load_done() -> set[str]:
    """이미 받은 판례일련번호. 다시 돌려도 중복 호출하지 않는다."""
    if not BODIES.exists():
        return set()
    done = set()
    with BODIES.open(encoding="utf-8") as f:
        for line in f:
            try:
                done.add(str(json.loads(line)["판례정보일련번호"]))
            except Exception:
                continue
    return done


def main():
    if not OC:
        raise SystemExit("[!] .env의 LAW_OC가 비어 있습니다.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 조문별 목록 ────────────────────────────────────────
    by_article: dict[str, list[str]] = {}
    meta: dict[str, dict] = {}
    for art in range(ART_FROM, ART_TO + 1):
        rows = search_by_article(art)
        ids = []
        for row in rows:
            cid = str(row.get("판례일련번호"))
            ids.append(cid)
            meta.setdefault(cid, {
                "판례일련번호": cid,
                "사건번호": row.get("사건번호"),
                "법원명": row.get("법원명"),
                "사건명": row.get("사건명"),
                "선고일자": row.get("선고일자"),
                "데이터출처명": row.get("데이터출처명"),
            })
        by_article[str(art)] = ids
        print(f"  제{art:2}조 → {len(ids):4}건")

    unique = sorted(meta)
    INDEX.write_text(json.dumps({
        "법령명": LAW_NAME,
        "대상조문": f"제{ART_FROM}조~제{ART_TO}조",
        "수집시각": datetime.now(timezone.utc).astimezone().isoformat(),
        "조문별_판례수": {k: len(v) for k, v in by_article.items()},
        "유니크_판례수": len(unique),
        "조문별": by_article,
        "판례메타": meta,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n조문별 합계 {sum(len(v) for v in by_article.values())}건 / 유니크 {len(unique)}건")
    print(f"저장: {INDEX.relative_to(ROOT)}")

    # ── 2. 본문 (증분) ────────────────────────────────────────
    done = load_done()
    todo = [c for c in unique if c not in done]
    print(f"\n본문 수집: 이미 {len(done)}건 / 받을 것 {len(todo)}건")

    ok = fail = 0
    with BODIES.open("a", encoding="utf-8") as f:
        for i, cid in enumerate(todo, 1):
            body = fetch_body(cid)
            if body is None:
                fail += 1
            else:
                # 참조조문에서 이 법 조문을 뽑아 같이 저장한다. 나중에 대조할 때 쓴다.
                refs = sorted({
                    f"제{m[0]}조" + (f" 제{m[1]}항" if m[1] else "") + (f" 제{m[2]}호" if m[2] else "")
                    for m in REF_RE.findall(str(body.get("참조조문", "")))
                })
                body["_약관법_참조조문"] = refs
                f.write(json.dumps(body, ensure_ascii=False) + "\n")
                ok += 1
            if i % 50 == 0:
                print(f"    {i}/{len(todo)} (성공 {ok} / 실패 {fail})")

    print(f"\n본문 수집 완료 — 성공 {ok}건 / 실패 {fail}건")
    print(f"저장: {BODIES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
