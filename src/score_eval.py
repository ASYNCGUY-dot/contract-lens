# -*- coding: utf-8 -*-
"""
사람이 라벨링한 평가 세트로 매칭 정확도를 잰다.

**"정확도 몇 %"를 한 숫자로 말하지 않는다.** 이 태스크는 두 방향의 오류가 성격이 다르다.

    미탐(놓침)   불공정 조항인데 아무것도 안 보여줬다 → 사용자가 모르고 넘어간다
    오탐(헛경보) 멀쩡한 조항에 경고를 붙였다        → 사용자가 서비스를 못 믿는다

이 서비스는 판정을 안 하고 근거만 보여주므로 미탐이 더 아프다. 그래도 둘 다 따로 낸다.

임계값도 여기서 정한다. 남의 숫자를 가져오지 않고 이 라벨로 곡선을 그려 고른다.

실행:  python src/score_eval.py
입력:  data/eval/eval_set.csv   ('정답' 칸이 채워져 있어야 한다)
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "data" / "eval" / "eval_set.csv"

NONE_LABELS = {"없음", "none", "-", "x", "X"}
HOLD_LABELS = {"보류", "hold", "?"}


def load() -> list[dict]:
    with EVAL.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    if not EVAL.exists():
        raise SystemExit("[!] data/eval/eval_set.csv 가 없습니다. build_eval_set.py 를 먼저 돌리세요.")

    rows = load()
    labeled, held, blank = [], 0, 0
    for r in rows:
        g = (r.get("정답") or "").strip()
        if not g:
            blank += 1
        elif g in HOLD_LABELS:
            held += 1
        else:
            r["_정답"] = "없음" if g in NONE_LABELS else g
            labeled.append(r)

    print(f"전체 {len(rows)}개 — 라벨 {len(labeled)} / 보류 {held} / 미기입 {blank}")
    if blank:
        print(f"\n[!] '정답' 칸이 빈 행이 {blank}개입니다. 채운 뒤 다시 돌리세요.")
    if not labeled:
        return

    pos = [r for r in labeled if r["_정답"] != "없음"]
    neg = [r for r in labeled if r["_정답"] == "없음"]
    print(f"  그중 해당 있음 {len(pos)} / 해당 없음 {len(neg)}\n")

    # ── 순위 정확도 (해당 있는 것만) ─────────────────────────
    if pos:
        top1 = sum(1 for r in pos if r["후보1"] == r["_정답"])
        top3 = sum(1 for r in pos if r["_정답"] in (r["후보1"], r["후보2"], r["후보3"]))
        print("=== 순위 정확도 (정답이 있는 것 기준) ===")
        print(f"  Top-1 {top1}/{len(pos)} = {top1/len(pos)*100:.1f}%")
        print(f"  Top-3 {top3}/{len(pos)} = {top3/len(pos)*100:.1f}%")

    # ── 임계값별 미탐·오탐 ──────────────────────────────────
    print("\n=== 임계값별 (후보1 점수로 게이팅) ===")
    print(f"  {'임계값':>6} {'미탐':>6} {'오탐':>6} {'Top-1정답':>9}  설명")
    scores = sorted({round(float(r["후보1_점수"]), 2) for r in labeled})
    for th in scores:
        miss = sum(1 for r in pos if float(r["후보1_점수"]) < th)
        fp = sum(1 for r in neg if float(r["후보1_점수"]) >= th)
        hit = sum(1 for r in pos
                  if float(r["후보1_점수"]) >= th and r["후보1"] == r["_정답"])
        print(f"  {th:6.2f} {miss:6} {fp:6} {hit:9}")
    print("\n  미탐 = 불공정인데 임계값에 걸려 안 보여준 것")
    print("  오탐 = 해당 없는데 임계값을 넘어 경고가 붙은 것")

    # ── 군별 ────────────────────────────────────────────────
    print("\n=== 군별 라벨 분포 ===")
    by = Counter((r["군"], "해당있음" if r["_정답"] != "없음" else "해당없음") for r in labeled)
    for g in ["A", "B", "C"]:
        y, n = by[(g, "해당있음")], by[(g, "해당없음")]
        print(f"  {g}군: 해당있음 {y:3} / 해당없음 {n:3}")
    print("\n  A군(판례 인용)에 해당있음이 적으면 양성 표본 확보가 실패한 것이다.")
    print("  B군(임베딩 상위)에 해당없음이 많으면 그게 곧 오탐이다.")

    if len(labeled) < 30:
        print(f"\n[!] 라벨이 {len(labeled)}개뿐입니다. 이 숫자로 정확도를 주장하면 안 됩니다.")
        print("    100개에서 오류 0이어도 3/n 법칙상 95% 상한은 3%입니다.")


if __name__ == "__main__":
    main()
