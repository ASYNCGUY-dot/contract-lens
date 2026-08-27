# -*- coding: utf-8 -*-
"""
약관규제법 유형 24개에도 조항과 **같은 방식으로** 구조를 뽑는다.

매칭에 구조를 쓰려면 양쪽이 같은 언어로 표현돼야 한다. 조항만 구조화하고
법 쪽은 임베딩 벡터로 두면 대조할 수가 없다. 그래서 법 유형에도 돌린다.

기대하는 것은 이것이다. 임베딩이 제7조와 제11조를 헷갈렸는데(둘 다 "책임·권리"
어휘를 쓴다), 구조로 보면 갈려야 한다.

    제 7조  사업자의 **의무·책임**이 줄어든다
    제11조  고객의 **권리·이익**이 줄어든다

갈리지 않으면(전부 같은 구조가 나오면) 이 방향은 무용하므로 버린다.

결과는 캐시한다. 실험할 때마다 API를 부르면 낭비다.

실행:  python src/structure_law.py
출력:  data/laws/유형_구조.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

LAW_TYPES = ROOT / "data" / "laws" / "약관규제법_유형.json"
OUT = ROOT / "data" / "laws" / "유형_구조.json"


def main():
    from extract_structure import extract

    types = [t for t in json.loads(LAW_TYPES.read_text(encoding="utf-8"))["유형"]
             if t["조"] != 6]
    cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    print(f"법 유형 {len(types)}개 (제6조 제외) — 캐시 {len(cache)}개\n")

    for i, t in enumerate(types, 1):
        key = f"{t['조']}|{t['유형'][:40]}"
        if key in cache:
            continue
        try:
            r = extract(t["유형"])
        except Exception as e:
            print(f"  [{i:2}] 제{t['조']}조 실패: {e}")
            continue
        cache[key] = {"조": t["조"], "유형": t["유형"], **r}
        s = cache[key]
        print(f"  [{i:2}] 제{t['조']:>2}조  {s.get('줄어드는것','?'):6} / "
              f"{s.get('줄어드는쪽','?'):4}  {t['유형'][:34]}")

    OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n=== 조문별 구조 프로필 — 갈리는가 ===")
    by = {}
    for v in cache.values():
        by.setdefault(v["조"], []).append((v.get("줄어드는것"), v.get("줄어드는쪽")))
    for a in sorted(by):
        c = Counter(by[a])
        top = " / ".join(f"{k[0]}·{k[1]}×{n}" for k, n in c.most_common())
        print(f"  제{a:>2}조  {top}")


if __name__ == "__main__":
    main()
