# -*- coding: utf-8 -*-
"""
관련성 게이트 — 임베딩이 뽑은 후보를 LLM이 **관련 있는지만** 확인한다.

## 왜 필요한가

v3(실제 사설 약관)에서 '높음' 정확도가 31.2%였다. 관련없음 27개 중 22개에
'높음'이 붙는다. 점수·격차·표준편차 무엇으로도 안 갈렸다(13번, 14번).
**임베딩은 "계약 문장끼리 비슷하다"까지만 보고, 특정 불공정 유형에 해당하는지는
보지 못한다.** 그래서 다른 종류의 신호가 필요하다.

## 판정이 아니다

묻는 것은 "이 조항이 이 유형이 말하는 상황에 해당하는가"이지
"이 조항이 불공정한가 / 무효인가"가 아니다. 후자는 법원이 하는 일이고
이 서비스가 하지 않기로 한 일이다. 출력도 관련 있음/없음뿐이다.

## 9번(구조 추출)과 무엇이 다른가

9번은 구조를 뽑아 **후보를 고르는 데** 쓰려다 실패했다. 여기서는 후보를 고르지
않는다. 임베딩이 고른 것을 **걸러내기만** 한다. 순위는 이미 쓸 만하고
(Top-3 85.7%) 못 하는 것은 판별뿐이므로, 판별만 맡긴다.

실행:  python src/relevance_gate.py --eval    v3 라벨로 효과를 잰다
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")
load_dotenv(r"C:/WORK/WORK/.env")

MODEL = "gpt-4o-mini"
CACHE = ROOT / "data" / "eval" / "gate_cache.json"

SYS = """너는 계약 조항이 주어진 '약관 유형'이 말하는 상황에 해당하는지만 본다.

판단하지 않는 것: 그 조항이 불공정한지, 무효인지, 누구에게 유리한지.
판단하는 것: 조항이 다루는 사안이 유형이 말하는 사안과 같은가.

같은 사안이면 true, 다른 사안이면 false.

예시
  유형: 사업자의 손해배상 범위를 제한하는 조항
  조항: "회사는 간접손해에 대하여 책임지지 않습니다"        → true (둘 다 배상범위 제한)
  조항: "보험금 청구 시 사고증명서를 제출하여야 합니다"      → false (청구 절차이지 배상범위가 아니다)

애매하면 false. 어휘가 겹친다는 이유만으로 true 하지 마라."""


def ask(client: OpenAI, clause: str, type_text: str) -> bool:
    r = client.chat.completions.create(
        model=MODEL, max_tokens=8, temperature=0,
        response_format={"type": "json_schema", "json_schema": {
            "name": "rel", "strict": True,
            "schema": {"type": "object", "additionalProperties": False,
                       "required": ["해당"],
                       "properties": {"해당": {"type": "boolean"}}}}},
        messages=[{"role": "system", "content": SYS},
                  {"role": "user", "content": f"유형: {type_text}\n조항: {clause}"}],
    )
    if r.choices[0].finish_reason == "length":
        raise RuntimeError("출력이 잘렸다")
    return json.loads(r.choices[0].message.content)["해당"]


def gate(client: OpenAI, matcher, clause: str, art: str, cache: dict | None = None) -> bool:
    """조문 하나에 대해, 그 조의 유형 중 하나라도 해당하면 통과."""
    types = [t["유형"] for t in matcher.types if str(t["조"]) == art]
    for t in types:
        key = f"{hash(clause)}|{hash(t)}"
        if cache is not None and key in cache:
            hit = cache[key]
        else:
            hit = ask(client, clause, t)
            if cache is not None:
                cache[key] = hit
        if hit:
            return True
    return False


def main():
    import csv
    from match_articles import ArticleMatcher

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    m = ArticleMatcher()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    rows = [r for r in csv.DictReader(
        (ROOT / "data" / "eval" / "eval_v3.csv").open(encoding="utf-8-sig"))
        if r["정답"] and r["정답"] not in ("제외", "보류")]

    before_p = before_n = after_p = after_n = 0
    for i, r in enumerate(rows, 1):
        gold = set(r["정답"].split("|"))
        pos = r["정답"] != "관련없음"
        hi = [c for c in m.match("", r["본문"]) if c["등급"] == "높음"]
        if hi:
            (before_p if pos else before_n).__class__      # noqa - 가독용
        if hi:
            if pos:
                before_p += 1
            else:
                before_n += 1
        kept = [c for c in hi if gate(client, m, r["본문"], c["조"], cache)]
        if kept:
            if pos:
                after_p += 1
            else:
                after_n += 1
        if i % 10 == 0:
            print(f"  {i}/{len(rows)} …")

    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"\n  {'':12}{'관련있음':>10}{'무관':>8}{'정확도':>9}")
    print(f"  {'게이트 전':12}{before_p:10}{before_n:8}"
          f"{before_p/(before_p+before_n)*100:8.1f}%")
    if after_p + after_n:
        print(f"  {'게이트 후':12}{after_p:10}{after_n:8}"
              f"{after_p/(after_p+after_n)*100:8.1f}%")
    print(f"\n  관련 조항 14개 중 '높음'이 남은 것: {after_p}개 (게이트 전 {before_p}개)")


if __name__ == "__main__":
    main()
