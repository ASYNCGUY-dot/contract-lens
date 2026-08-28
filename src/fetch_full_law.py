# -*- coding: utf-8 -*-
"""
약관규제법 **전체 조문**을 받아둔다. 평가 세트에서 법 조문 인용을 걸러내는 데 쓴다.

`약관규제법_유형.json`은 제6~14조의 불공정 유형만 담는다. 그런데 판례는
제3조(설명의무), 제4조(개별 약정 우선), 제5조(해석) 조문도 그대로 인용한다.
유형 목록으로만 거르면 이것들이 평가 세트에 남아 **법 조문을 약관으로 오인**하게 된다.

실제로 v3 첫 채점에서 '관련없음' 상위 6개가 전부 법 조문이었다.

    0.6899  "합의사항은 약관에 우선한다"              제4조
    0.6652  "중요한 내용을 설명하여야 한다"            제3조
    0.6395  "고객에 따라 다르게 해석되어서는 안 된다"    제5조

실행:  python src/fetch_full_law.py
출력:  data/laws/약관규제법_전문.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

BASE = "https://www.law.go.kr/DRF"
UA = {"User-Agent": "Mozilla/5.0"}
OC = os.getenv("LAW_OC", "")
LAW_NAME = "약관의 규제에 관한 법률"
OUT = ROOT / "data" / "laws" / "약관규제법_전문.json"


def flatten(node) -> list[str]:
    """조문 구조가 dict/list/None 으로 섞여 온다. 문자열만 긁어모은다."""
    out = []
    if isinstance(node, str):
        t = node.strip()
        if t:
            out.append(t)
    elif isinstance(node, list):
        for x in node:
            out += flatten(x)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in ("조문내용", "항내용", "호내용", "목내용"):
                out += flatten(v)
    return out


def main():
    if not OC:
        raise SystemExit("[!] .env 에 LAW_OC 가 없습니다.")

    r = requests.get(f"{BASE}/lawSearch.do", timeout=30, headers=UA,
                     params={"OC": OC, "target": "law", "type": "JSON",
                             "query": LAW_NAME, "display": "20"})
    r.raise_for_status()
    rows = r.json()["LawSearch"]["law"]
    rows = rows if isinstance(rows, list) else [rows]
    mst = next(x["법령일련번호"] for x in rows if x["법령명한글"].strip() == LAW_NAME)

    r = requests.get(f"{BASE}/lawService.do", timeout=30, headers=UA,
                     params={"OC": OC, "target": "law", "MST": mst, "type": "JSON"})
    r.raise_for_status()
    arts = r.json()["법령"]["조문"]["조문단위"]
    arts = arts if isinstance(arts, list) else [arts]

    out = []
    for a in arts:
        if a.get("조문여부") == "전문":          # 장 제목이 조문번호를 달고 온다
            continue
        texts = flatten(a.get("조문내용")) + flatten(a.get("항"))
        for t in texts:
            t = " ".join(t.split())
            if len(t) >= 20:
                out.append({"조": a.get("조문번호"), "내용": t})

    OUT.write_text(json.dumps({"법령명": LAW_NAME, "법령일련번호": mst, "문장": out},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    arts_n = len({x["조"] for x in out})
    print(f"약관규제법 전문 — 조문 {arts_n}개 / 문장 {len(out)}개 → {OUT.relative_to(ROOT)}")
    for x in out[:4]:
        print(f"  제{x['조']}조  {x['내용'][:66]}")


if __name__ == "__main__":
    main()
