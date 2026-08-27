# -*- coding: utf-8 -*-
"""
평가 세트 v2 채점. 태스크는 "이 조항이 어느 조문과 관련되는가"다.

**"정확도 몇 %"를 한 숫자로 말하지 않는다.** 세 가지를 따로 낸다.

    Top-1 / Top-3   기계가 고른 후보에 정답이 있는가
    혼동            어느 조문끼리 헷갈리는가. 여기서 다음에 뭘 고칠지가 나온다
    임계값별        관련없음을 걸러내는 선을 어디에 둘 것인가

실행:
    python src/apply_labels_v2.py "1:7,2:관련없음,..."
    python src/score_eval_v2.py
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "data" / "eval" / "eval_v2.csv"

NONE = "관련없음"
HOLD = {"보류", "hold", "?"}
TITLES = {"7": "면책조항", "8": "손배액예정", "9": "해제·해지", "10": "채무이행",
          "11": "권익보호", "12": "의사표시", "13": "대리인", "14": "소송·관할"}


def main():
    if not EVAL.exists():
        raise SystemExit("[!] data/eval/eval_v2.csv 가 없습니다.")

    rows = list(csv.DictReader(EVAL.open(encoding="utf-8-sig")))
    labeled, held, blank = [], 0, 0
    for r in rows:
        g = (r.get("정답") or "").strip()
        if not g:
            blank += 1
        elif g in HOLD:
            held += 1
        else:
            r["_g"] = g
            labeled.append(r)

    print(f"전체 {len(rows)}개 — 라벨 {len(labeled)} / 보류 {held} / 미기입 {blank}")
    if blank:
        print(f"\n[!] '정답' 칸이 빈 행이 {blank}개입니다.")
    if not labeled:
        return

    pos = [r for r in labeled if r["_g"] != NONE]
    neg = [r for r in labeled if r["_g"] == NONE]
    print(f"  관련 있음 {len(pos)} / 관련없음 {len(neg)}\n")

    if pos:
        top1 = sum(1 for r in pos if r["후보1"] == r["_g"])
        top3 = sum(1 for r in pos if r["_g"] in (r["후보1"], r["후보2"], r["후보3"]))
        print("=== 순위 정확도 (관련 있는 것 기준) ===")
        print(f"  Top-1 {top1}/{len(pos)} = {top1/len(pos)*100:.1f}%")
        print(f"  Top-3 {top3}/{len(pos)} = {top3/len(pos)*100:.1f}%")

        print("\n=== 조문별 (정답 기준) ===")
        by = defaultdict(lambda: [0, 0])
        for r in pos:
            by[r["_g"]][1] += 1
            if r["후보1"] == r["_g"]:
                by[r["_g"]][0] += 1
        for a in sorted(by, key=lambda x: int(x) if x.isdigit() else 99):
            hit, tot = by[a]
            print(f"  제{a:>2}조 {TITLES.get(a, ''):8} {hit}/{tot}")

        print("\n=== 혼동: 정답 → 기계가 고른 1위 (틀린 것만) ===")
        conf = Counter((r["_g"], r["후보1"]) for r in pos if r["후보1"] != r["_g"])
        for (g, p), n in conf.most_common(8):
            print(f"  제{g}조({TITLES.get(g,'')}) → 제{p}조({TITLES.get(p,'')})  {n}건")
        if not conf:
            print("  (없음)")

    print("\n=== 임계값별 (후보1 점수) ===")
    print(f"  {'임계값':>6} {'미탐':>5} {'오탐':>5} {'Top-1정답':>9}")
    for th in sorted({round(float(r["후보1_점수"]), 2) for r in labeled}):
        miss = sum(1 for r in pos if float(r["후보1_점수"]) < th)
        fp = sum(1 for r in neg if float(r["후보1_점수"]) >= th)
        hit = sum(1 for r in pos if float(r["후보1_점수"]) >= th and r["후보1"] == r["_g"])
        print(f"  {th:6.2f} {miss:5} {fp:5} {hit:9}")
    print("\n  미탐 = 관련 조문이 있는데 임계값에 걸려 안 보여준 것")
    print("  오탐 = 관련없음인데 임계값을 넘어 조문이 붙은 것")

    print("\n=== 층별 (제목 힌트가 맞았는가) ===")
    for stratum in sorted({r["층"] for r in labeled}):
        sub = [r for r in labeled if r["층"] == stratum]
        c = Counter(r["_g"] for r in sub)
        top = ", ".join(f"{k}:{v}" for k, v in c.most_common(3))
        print(f"  {stratum:12} {len(sub):3}개 → {top}")

    if len(pos) < 20:
        print(f"\n[!] 관련 있음 표본이 {len(pos)}개뿐입니다. 조문별 수치는 참고만 하세요.")


if __name__ == "__main__":
    main()
