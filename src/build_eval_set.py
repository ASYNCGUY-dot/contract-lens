# -*- coding: utf-8 -*-
"""
매칭 정확도를 재기 위한 평가 세트를 만든다. **정답 라벨은 사람이 붙인다.**

에이전트가 라벨을 붙이면 "AI가 만든 정답표로 AI를 채점"하는 순환이 된다.
여기서 하는 일은 두 가지뿐이다 — 표본을 잘 뽑는 것, 사람이 빠르게 판단하도록 차려 주는 것.

**무작위 표본은 쓸 수 없다.** 표준약관은 심의를 거친 것이라 대부분 '해당 없음'이고,
그러면 "전부 해당 없음"이라고만 해도 정확도가 높게 나와 지표가 죽는다. 층화로 뽑는다.

    A군  판례에 인용된 조항        양성 후보. 법원이 실제로 다툰 조항이다
    B군  표준약관 중 임베딩 상위     오탐 후보. 여기서 걸러야 정밀도가 올라간다
    C군  표준약관 무작위           음성. 바닥선을 잡는다

실행:  python src/build_eval_set.py
출력:  data/eval/eval_set.csv     ← 이 파일의 '정답' 칸을 사람이 채운다
"""

from __future__ import annotations

import csv
import json
import random
import re
import html
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BODIES = ROOT / "data" / "cases" / "bodies.jsonl"
PARSED = ROOT / "data" / "terms" / "parsed.jsonl"
LAW_TYPES = ROOT / "data" / "laws" / "약관규제법_유형.json"
OUT = ROOT / "data" / "eval" / "eval_set.csv"

N_A, N_B, N_C = 35, 35, 30
SEED = 20260823


def clean(s) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(s or "")))).strip()


# 판결문 서술이 중간에 잘린 파편은 조사·어미로 시작한다
FRAGMENT_HEAD = re.compile(r"^(에|을|를|이|가|은|는|의|와|과|로|으로|고|며|서|해|한|된|및)\b")


def fetch_law_pieces(oc: str) -> list[str]:
    """약관규제법 조문 조각. 판례가 법을 인용한 것을 걸러내는 데 쓴다."""
    import requests
    r = requests.get("https://www.law.go.kr/DRF/lawService.do", timeout=30,
                     headers={"User-Agent": "Mozilla/5.0"},
                     params={"OC": oc, "target": "law", "MST": "260021", "type": "JSON"})
    r.raise_for_status()
    out = []
    for j in r.json()["법령"]["조문"]["조문단위"]:
        if j.get("조문여부") != "조문":
            continue
        out.append(clean(j.get("조문내용")))
        hs = j.get("항") or []
        hs = [hs] if isinstance(hs, dict) else hs
        for h in hs:
            if clean(h.get("항내용")):
                out.append(clean(h.get("항내용")))
            hos = h.get("호") or []
            hos = [hos] if isinstance(hos, dict) else hos
            for x in hos:
                if clean(x.get("호내용")):
                    out.append(clean(x.get("호내용")))
    return [t for t in out if t]


def group_a() -> list[dict]:
    """
    판례 본문에서 '약관 제N조'에 이어 따옴표로 인용된 구절을 뽑고, 노이즈를 걸러낸다.

    실측: 거르기 전 214개 중 법 조문 인용이 49개(23%)였다.
    """
    import os
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    pat = re.compile(r"약관[^.]{0,40}?제\s*\d+\s*조[^.]{0,30}?[‘“\"\']([^’”\"\']{25,220})[’”\"\']")
    raw, seen = [], set()
    for line in BODIES.open(encoding="utf-8"):
        b = json.loads(line)
        body = clean(b.get("판례내용", ""))
        for m in pat.finditer(body):
            t = m.group(1).strip()
            if len(t) < 25 or t in seen:
                continue
            if FRAGMENT_HEAD.match(t):          # 잘린 파편
                continue
            seen.add(t)
            raw.append({"군": "A", "출처": f"판례 {b.get('사건번호')}", "조항": t})

    # 법 조문 인용 제거
    from match_clauses import encode
    pieces = fetch_law_pieces(os.getenv("LAW_OC"))
    L = encode(pieces)
    A = encode([x["조항"] for x in raw])
    sim = (A @ L.T).max(axis=1)
    kept = [r for r, sc in zip(raw, sim) if sc < 0.85]
    print(f"  A군 후보 {len(raw)} → 법 조문 인용 {len(raw) - len(kept)}개 제외 → {len(kept)}개")
    return kept


def load_term_clauses() -> list[dict]:
    out = []
    for line in PARSED.open(encoding="utf-8"):
        d = json.loads(line)
        if d["status"] != "ok":
            continue
        for c in d["clauses"]:
            for h in c["항"]:
                t = h["본문"].strip()
                if 25 <= len(t) <= 400:
                    out.append({"출처": f"{d['이름'][:20]} {c['표시']}{h['번호'] or ''}",
                                "조항": t})
    return out


def main():
    random.seed(SEED)
    from match_clauses import Matcher, encode           # 임베딩은 여기서만 쓴다

    types = json.loads(LAW_TYPES.read_text(encoding="utf-8"))["유형"]
    m = Matcher()

    a_all = group_a()
    random.shuffle(a_all)
    a = a_all[:N_A]

    terms = load_term_clauses()
    idx = encode([t["조항"] for t in terms])
    best = (idx @ m._index.T).max(axis=1)
    order = np.argsort(-best)

    b = [{**terms[i], "군": "B"} for i in order[:N_B]]
    rest = [i for i in order[N_B:]]
    random.shuffle(rest)
    c = [{**terms[i], "군": "C"} for i in rest[:N_C]]

    rows = a + b + c
    random.shuffle(rows)                                 # 군을 섞어야 라벨러가 편향되지 않는다

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "군", "출처", "조항",
                    "후보1", "후보1_유형", "후보1_점수",
                    "후보2", "후보2_유형", "후보3", "후보3_유형",
                    "정답", "메모"])
        for i, r in enumerate(rows, 1):
            cand = m.match(r["조항"], top_k=3)
            w.writerow([
                i, r["군"], r["출처"], r["조항"],
                cand[0]["id"], cand[0]["유형"][:40], f"{cand[0]['점수']:.4f}",
                cand[1]["id"], cand[1]["유형"][:40],
                cand[2]["id"], cand[2]["유형"][:40],
                "", "",
            ])

    print(f"평가 세트 {len(rows)}개 → {OUT.relative_to(ROOT)}")
    print(f"  A군 판례 인용 조항  {len(a)}개  (양성 후보, 전체 {len(a_all)}개 중 표본)")
    print(f"  B군 임베딩 상위     {len(b)}개  (오탐 후보)")
    print(f"  C군 무작위          {len(c)}개  (음성)")
    print()
    print("다음: '정답' 칸을 직접 채운다.")
    print("  · 해당하는 유형이 있으면 그 id를 적는다 (예: 7-1, 14-1, 6-②-1)")
    print("  · 해당 없으면  없음")
    print("  · 판단이 안 서면  보류   ← 억지로 고르지 말 것. 보류는 채점에서 제외한다")
    print()
    print("유형 id 목록:")
    for t in types:
        print(f"  {t['id']:8} {t['인용'][14:]:22} {t['유형'][:44]}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
