# -*- coding: utf-8 -*-
"""
매칭 방식을 바꿔가며 라벨된 평가 세트로 바로 잰다.

v2 채점에서 오답 19건 중 12건이 제11조와 얽혔다. 제11조는 유형이 항변권·기한이익·
제3자계약·비밀누설로 제각각인데, 현재 방식은 **한 조의 유형을 전부 이어붙여 하나로**
임베딩한다. 길고 뭉뚱그려진 벡터가 되어 뭐든 걸리는 것으로 보인다.

그래서 방식을 바꿔 재본다. 가설을 세웠으면 재고, 안 나아지면 버린다.

    A  현재: 조제목 + 그 조 유형 전부 이어붙이기 → 조당 벡터 1개
    B  유형별로 따로 임베딩 → 조 점수 = 그 조 유형들의 최대값
    C  B에 조제목을 각 유형 앞에 붙임
    D  B + 조항 입력에서 제목을 뺌 (제목이 도움이 되는지 확인)

실행:  python src/compare_matchers.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

EVAL = ROOT / "data" / "eval" / "eval_v2.csv"
LAW_TYPES = ROOT / "data" / "laws" / "약관규제법_유형.json"
NONE = "관련없음"
HOLD = {"보류"}


def load_labeled() -> list[dict]:
    rows = []
    for r in csv.DictReader(EVAL.open(encoding="utf-8-sig")):
        g = (r.get("정답") or "").strip()
        if g and g not in HOLD:
            r["_g"] = g
            rows.append(r)
    return rows


def build(mode: str, types: list[dict]) -> tuple[np.ndarray, list[str]]:
    """(벡터, 각 벡터가 속한 조) 를 준다. 조당 여러 벡터일 수 있다."""
    from match_clauses import encode

    arts = sorted({t["조"] for t in types if t["조"] != 6})
    titles = {t["조"]: t["조제목"] for t in types}

    if mode == "A":
        texts, owner = [], []
        for a in arts:
            body = " ".join(t["유형"] for t in types if t["조"] == a)
            texts.append(f"{titles[a]}. {body}")
            owner.append(str(a))
    elif mode in ("B", "D"):
        texts, owner = [], []
        for t in types:
            if t["조"] == 6:
                continue
            texts.append(t["유형"])
            owner.append(str(t["조"]))
    elif mode == "C":
        texts, owner = [], []
        for t in types:
            if t["조"] == 6:
                continue
            texts.append(f"{titles[t['조']]}. {t['유형']}")
            owner.append(str(t["조"]))
    else:
        raise ValueError(mode)
    return encode(texts), owner


def score(mode: str, rows: list[dict], types: list[dict]) -> dict:
    from match_clauses import encode

    idx, owner = build(mode, types)
    if mode == "D":
        queries = [r["본문"] for r in rows]              # 제목 제외
    else:
        queries = [f"{r['조제목']}. {r['본문']}" for r in rows]
    Q = encode(queries)
    sim = Q @ idx.T                                       # (문항, 벡터)

    arts = sorted({o for o in owner}, key=int)
    by_art = np.full((len(rows), len(arts)), -1.0)
    for j, o in enumerate(owner):
        k = arts.index(o)
        by_art[:, k] = np.maximum(by_art[:, k], sim[:, j])  # 조별 최대

    pos = [i for i, r in enumerate(rows) if r["_g"] != NONE]
    top1 = top3 = 0
    conf = Counter()
    for i in pos:
        order = np.argsort(-by_art[i])[:3]
        cands = [arts[k] for k in order]
        g = rows[i]["_g"]
        if cands[0] == g:
            top1 += 1
        else:
            conf[(g, cands[0])] += 1
        if g in cands:
            top3 += 1
    return {"mode": mode, "n": len(pos), "top1": top1, "top3": top3, "conf": conf,
            "best": by_art.max(axis=1), "rows": rows}


def main():
    types = json.loads(LAW_TYPES.read_text(encoding="utf-8"))["유형"]
    rows = load_labeled()
    print(f"라벨된 문항 {len(rows)}개 (관련있음 {sum(1 for r in rows if r['_g'] != NONE)})\n")

    results = []
    for mode, desc in [("A", "현재: 조별 유형 이어붙이기"),
                       ("B", "유형별 임베딩 + 조별 최대"),
                       ("C", "B + 각 유형 앞에 조제목"),
                       ("D", "B + 조항 입력에서 제목 제외")]:
        r = score(mode, rows, types)
        results.append(r)
        print(f"[{mode}] {desc}")
        print(f"     Top-1 {r['top1']:2}/{r['n']} = {r['top1']/r['n']*100:5.1f}%   "
              f"Top-3 {r['top3']:2}/{r['n']} = {r['top3']/r['n']*100:5.1f}%")

    best = max(results, key=lambda x: (x["top1"], x["top3"]))
    print(f"\n=== 최고: {best['mode']} — 혼동 상위 6개 ===")
    for (g, p), n in best["conf"].most_common(6):
        print(f"  제{g}조 → 제{p}조  {n}건")

    print(f"\n=== {best['mode']} 방식의 제11조 관련 오답 ===")
    n11 = sum(n for (g, p), n in best["conf"].items() if "11" in (g, p))
    tot = sum(best["conf"].values())
    print(f"  {n11}/{tot}건  (A 방식에서는 12/19건이었다)")


if __name__ == "__main__":
    main()
