# -*- coding: utf-8 -*-
"""
평가 세트 v3 채점 — **실제 사설 약관**에서도 v2와 같은 성능이 나오는지 잰다.

## 이 세트로 무엇을 말할 수 있고 무엇을 말할 수 없나

**말할 수 있는 것**: 표준약관에서 보이지 않던 약점이 있는가.
**말할 수 없는 것**: 정확한 성능 수치. 관련있음이 16개뿐이라 신뢰구간이 매우 넓다.

v3는 성능을 재는 자가 아니라 **약점을 찾는 그물**이다.

## 복수 정답을 인정한다

한 조항이 두 조문에 걸치는 경우가 있다. 예를 들어 "해제 시 계약보증금을 위약금으로
몰수한다"는 해제(제9조)이면서 위약금(제8조)이다. 강제로 하나만 고르게 하면 왜곡이므로
**정답 집합 중 하나라도 맞으면 맞은 것으로 센다.**

## 제목이 없다는 것을 감안해야 한다

판례 인용에는 조 제목이 없다. 그런데 제목은 성능에 크게 기여한다 — v2도 제목을 빼면
Top-1 70.9%→56.4%, '높음' 정확도 97.9%→83.3%로 떨어진다. **v3를 v2의 원래 수치와
직접 비교하면 안 된다.** 비교 기준은 '제목 없는 v2'다.

실행:  python src/score_eval_v3.py
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
EVAL = ROOT / "data" / "eval" / "eval_v3.csv"
NONE = "관련없음"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main():
    from match_articles import ArticleMatcher

    rows = [r for r in csv.DictReader(EVAL.open(encoding="utf-8-sig"))
            if r["정답"] and r["정답"] not in ("제외", "보류")]
    m = ArticleMatcher()
    pos = [r for r in rows if r["정답"] != NONE]
    neg = [r for r in rows if r["정답"] == NONE]
    print(f"라벨 {len(rows)}개 — 관련있음 {len(pos)} / 관련없음 {len(neg)}\n")

    t1 = t3 = 0
    miss = []
    for r in pos:
        gold = set(r["정답"].split("|"))
        res = m.match("", r["본문"], floor=0.0)
        cands = [x["조"] for x in res]
        if cands and cands[0] in gold:
            t1 += 1
        if gold & set(cands):
            t3 += 1
        else:
            miss.append((r["번호"], sorted(gold), cands, r["본문"][:52]))

    lo1, hi1 = wilson(t1, len(pos))
    lo3, hi3 = wilson(t3, len(pos))
    print("=== 순위 (관련있음 기준) ===")
    print(f"  Top-1 {t1}/{len(pos)} = {t1/len(pos)*100:.1f}%   95% 구간 {lo1*100:.0f}~{hi1*100:.0f}%")
    print(f"  Top-3 {t3}/{len(pos)} = {t3/len(pos)*100:.1f}%   95% 구간 {lo3*100:.0f}~{hi3*100:.0f}%")

    hp = sum(1 for r in pos if any(x["등급"] == "높음" for x in m.match("", r["본문"])))
    hn = sum(1 for r in neg if any(x["등급"] == "높음" for x in m.match("", r["본문"])))
    if hp + hn:
        lo, hi = wilson(hp, hp + hn)
        print(f"\n=== '높음' 정확도 ===")
        print(f"  {hp}관련 / {hn}무관 = {hp/(hp+hn)*100:.1f}%   95% 구간 {lo*100:.0f}~{hi*100:.0f}%")
    shown = sum(1 for r in pos if m.match("", r["본문"]))
    print(f"  아무것도 안 보여준 관련 조항: {len(pos)-shown}/{len(pos)}")

    if miss:
        print(f"\n=== Top-3에도 못 든 것 {len(miss)}건 ===")
        for n, g, c, t in miss:
            print(f"  [{n}] 정답 {'·'.join(g)} / 후보 {'·'.join(c) or '없음'}  {t}")


if __name__ == "__main__":
    main()
