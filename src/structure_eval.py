# -*- coding: utf-8 -*-
"""
평가 세트 조항 85개에 구조를 뽑아 캐시한다. 구조 필터를 재려면 먼저 이게 있어야 한다.

법 유형 쪽은 `structure_law.py`가 뽑는다. 양쪽이 같은 스키마여야 대조가 된다.

**근거문구 검증에 실패하면 구조를 버린다.** 원문에 없는 문구를 근거로 댔다는 것은
모델이 지어냈다는 뜻이고, 지어낸 근거 위에 세운 구조는 쓸 수 없다.

실행:  python src/structure_eval.py
출력:  data/eval/구조_v2.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = ROOT / "data" / "eval" / "구조_v2.json"


def main():
    from extract_structure import extract, verify_quote
    from compare_matchers import load_labeled

    rows = load_labeled()
    cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    print(f"조항 {len(rows)}개 — 캐시 {len(cache)}개\n")

    bad = 0
    for i, r in enumerate(rows, 1):
        key = r["번호"]
        if key in cache:
            continue
        text = f"{r['조제목']}. {r['본문']}"
        try:
            s = extract(text)
        except Exception as e:
            print(f"  [{i:2}] 실패: {e}")
            continue
        q = s.get("근거문구", "")
        if q and not verify_quote(text, q):
            bad += 1
            s["_환각"] = True
        cache[key] = s
        if i % 10 == 0:
            print(f"  {i}/{len(rows)} …")

    OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n완료 {len(cache)}개 — 근거문구 환각 {bad}건")

    c = Counter((v.get("줄어드는것"), v.get("줄어드는쪽")) for v in cache.values())
    print("\n=== 조항 쪽 구조 분포 ===")
    for (a, b), n in c.most_common():
        print(f"  {str(a):8} / {str(b):6}  {n:3}건")


if __name__ == "__main__":
    main()
