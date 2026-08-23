# -*- coding: utf-8 -*-
"""
수집한 판례 본문의 '참조조문'을 직접 파싱해 조문 → 판례 색인을 만든다.

**왜 JO 필터를 안 쓰는가 (2026-08-23 교차검증 결과)**

처음에는 API의 `JO` 참조조문 필터가 조문 단위로 작동한다고 보고 그걸 신뢰했다.
463건을 받아 본문의 참조조문과 대조해보니 맞지 않았다.

    JO=제7조로 받은 229건 중, 본문 참조조문에 제7조가 있는 것은 거의 없다.
    실제로 제7조를 참조하는 판례는 전체 463건 중 24건뿐이다.
    JO=제7조 샘플의 참조조문은 제5조·제3조·제6조뿐이었다.

`JO`는 법령명만 맞으면 걸리는 것으로 보인다. 조문 번호는 신뢰할 수 없다.
그래서 **수집은 JO로 넓게 하되, 색인은 본문 참조조문을 직접 파싱해서 만든다.**

참조조문 표기가 두 가지로 섞여 있는 것도 확인했다. 띄어쓰기를 지우고 매칭해야 한다.

    '약관의 규제에 관한 법률'   384건
    '약관의규제에관한법률'      304건
    '약관의규제에관한 법률'       2건
    '약관규제에관한법률'          1건

실행:  python src/build_case_index.py
출력:  data/cases/article_index.json
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODIES = ROOT / "data" / "cases" / "bodies.jsonl"
OUT = ROOT / "data" / "cases" / "article_index.json"

# 띄어쓰기를 모두 지운 뒤 매칭한다. 표기 흔들림이 실측으로 4종 확인됐다.
LAW_PAT = re.compile(r"약관(?:의)?규제에관한법률제(\d+)조((?:제\d+항)?(?:제\d+호)?)")


def squash(s) -> str:
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", " ", str(s or "")))


def parse_refs(ref_text: str) -> list[dict]:
    """참조조문에서 약관규제법 조문을 뽑는다. 항·호까지 있으면 같이 담는다."""
    out, seen = [], set()
    for art, tail in LAW_PAT.findall(squash(ref_text)):
        hang = re.search(r"제(\d+)항", tail)
        ho = re.search(r"제(\d+)호", tail)
        key = (art, hang.group(1) if hang else None, ho.group(1) if ho else None)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "조": int(art),
            "항": key[1],
            "호": key[2],
            "인용": f"약관의 규제에 관한 법률 제{art}조"
                    + (f" 제{key[1]}항" if key[1] else "")
                    + (f" 제{key[2]}호" if key[2] else ""),
        })
    return out


def main():
    if not BODIES.exists():
        raise SystemExit("[!] data/cases/bodies.jsonl 이 없습니다. collect_cases.py 를 먼저 돌리세요.")

    by_article: dict[int, list[str]] = defaultdict(list)
    meta: dict[str, dict] = {}
    total = with_ref = 0

    with BODIES.open(encoding="utf-8") as f:
        for line in f:
            b = json.loads(line)
            total += 1
            cid = str(b["판례정보일련번호"])
            refs = parse_refs(b.get("참조조문", ""))
            if not refs:
                continue
            with_ref += 1
            meta[cid] = {
                "판례정보일련번호": cid,
                "사건번호": b.get("사건번호"),
                "법원명": b.get("법원명"),
                "사건명": b.get("사건명"),
                "선고일자": b.get("선고일자"),
                "참조조문_약관법": [r["인용"] for r in refs],
            }
            for art in {r["조"] for r in refs}:
                by_article[art].append(cid)

    payload = {
        "출처": "판례 본문의 참조조문 필드를 직접 파싱 (JO 필터를 신뢰하지 않는다)",
        "생성시각": datetime.now(timezone.utc).astimezone().isoformat(),
        "전체_판례수": total,
        "약관법_참조_판례수": with_ref,
        "조문별_판례수": {str(k): len(v) for k, v in sorted(by_article.items())},
        "조문별": {str(k): sorted(v) for k, v in sorted(by_article.items())},
        "판례메타": meta,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"본문 {total}건 중 약관규제법 조문을 참조하는 판례 {with_ref}건\n")
    print("조문별 판례 수 (본문 참조조문 기준)")
    for art in sorted(by_article):
        print(f"  제{art:2}조 — {len(by_article[art]):4}건")
    print(f"\n저장: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
