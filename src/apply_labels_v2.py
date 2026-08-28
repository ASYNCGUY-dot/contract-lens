# -*- coding: utf-8 -*-
"""
라벨링 도구가 뱉은 한 줄을 평가 세트 CSV의 '정답' 칸에 반영한다.

    python src/apply_labels_v2.py    "1:7,2:관련없음,..."     표준약관 세트(v2)
    python src/apply_labels_v2.py v3 "1:9,2:관련없음,..."     판례 인용 세트(v3)

실행:
    python src/apply_labels_v2.py "1:7,2:관련없음,3:보류,..."
    python src/apply_labels_v2.py --file labels.txt

붙여넣은 라벨을 그대로 믿지 않는다. 유형 id가 실제 목록에 있는지 대조하고,
없는 id가 나오면 반영하지 않고 알려준다. 오타 하나가 평가 전체를 오염시킨다.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 첫 인자가 v3 면 판례 인용 세트에 반영한다. 라벨을 엉뚱한 세트에 쓰면 조용히 망가지므로
# 버전을 명시적으로 받는다.
VER = "v3" if (len(sys.argv) > 1 and sys.argv[1] == "v3") else "v2"
if VER == "v3":
    sys.argv.pop(1)
EVAL = ROOT / "data" / "eval" / f"eval_{VER}.csv"
LAW_TYPES = ROOT / "data" / "laws" / "약관규제법_유형.json"

SPECIAL = {"관련없음", "보류"}


def parse(raw: str) -> dict[str, str]:
    out = {}
    for part in re.split(r"[,\s]+", raw.strip()):
        if not part:
            continue
        if ":" not in part:
            raise SystemExit(f"[!] 형식이 이상합니다: {part!r} (기대: 번호:라벨)")
        n, v = part.split(":", 1)
        out[n.strip()] = v.strip()
    return out


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == "--file":
        raw = Path(sys.argv[2]).read_text(encoding="utf-8")
    else:
        raw = " ".join(sys.argv[1:])

    labels = parse(raw)
    # v2는 조 단위 라벨이다 (제7~14조). 제6조는 일반원칙이라 뺐다.
    valid = {str(t["조"]) for t in json.loads(LAW_TYPES.read_text(encoding="utf-8"))["유형"]
             if t["조"] != 6}

    bad = {n: v for n, v in labels.items() if v not in valid and v not in SPECIAL}
    if bad:
        print(f"[!] 목록에 없는 유형 id가 {len(bad)}개 있습니다. 반영하지 않았습니다.")
        for n, v in list(bad.items())[:10]:
            print(f"    {n}번 → {v!r}")
        raise SystemExit(1)

    try:
        rows = list(csv.DictReader(EVAL.open(encoding="utf-8-sig")))
    except OSError as e:
        raise SystemExit(f"[!] CSV를 못 읽었습니다: {e}")

    hit = 0
    for r in rows:
        v = labels.get(r["번호"])
        if v:
            r["정답"] = v
            hit += 1

    try:
        with EVAL.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    except PermissionError:
        raise SystemExit("[!] CSV가 열려 있어 저장하지 못했습니다. 엑셀/LibreOffice를 닫고 다시 실행하세요.")

    counts: dict[str, int] = {}
    for r in rows:
        v = (r.get("정답") or "").strip()
        if v:
            k = v if v in SPECIAL else "조문지정"
            counts[k] = counts.get(k, 0) + 1

    print(f"{hit}개 반영 → {EVAL.relative_to(ROOT)}")
    print(f"  유형지정 {counts.get('유형지정', 0)} / 없음 {counts.get('없음', 0)} / 보류 {counts.get('보류', 0)}")
    print("\n다음: python src/score_eval_v2.py")


if __name__ == "__main__":
    main()
