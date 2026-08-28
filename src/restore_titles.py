# -*- coding: utf-8 -*-
"""
v3 조항에 조 제목을 붙여, **제목이 있는 실제 계약서** 조건으로 다시 잰다.

## 왜

v3는 판례 인용이라 조 제목이 없다. 그런데 제목은 성능에 크게 기여한다
(v2도 제목을 빼면 Top-1 70.9%→56.4%). 실제 계약서에는 제목이 있으므로,
**제목 없는 v3 수치는 실사용보다 비관적**일 수 있다.

    v2  표준약관 + 제목        보여준 것 중 관련 93.1%   ← 낙관 쪽 끝
    v3  사설 약관 + 제목 없음   보여준 것 중 관련 27.0%   ← 비관 쪽 끝
    ?   사설 약관 + 제목        실사용은 여기 어딘가다

## 한계를 먼저 밝힌다

**LLM이 만든 제목은 실제 계약서 제목보다 정확할 수 있다.** 조항 전문을 읽고
요약한 것이기 때문이다. 실제 계약서 제목은 "제7조(면책)"처럼 짧거나 때로는
내용과 어긋나기도 한다. **따라서 여기서 나온 수치는 상한에 가깝다.**

그래도 재는 값어치가 있다. 제목이 얼마나 기여하는지를 알면, 실사용 성능이
27%와 93% 중 어느 쪽에 가까운지 가늠할 수 있다.

**정답을 흘리지 않도록** 제목은 조항이 무엇에 관한 것인지만 쓰게 하고,
법 조문 이름("면책조항의 금지" 등)을 그대로 쓰지 못하게 막았다.

실행:  python src/restore_titles.py
출력:  data/eval/titles_v3.json
"""

from __future__ import annotations

import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")
load_dotenv(r"C:/WORK/WORK/.env")

MODEL = "gpt-4o-mini"
EVAL = ROOT / "data" / "eval" / "eval_v3.csv"
OUT = ROOT / "data" / "eval" / "titles_v3.json"

SYS = """계약서 조항에 붙일 조 제목을 짓는다. 실제 계약서에 쓰이는 짧은 제목이어야 한다.

  "회사는 어떠한 손해에도 책임지지 않습니다"        → 면책
  "소송의 관할법원은 회사 소재지로 한다"            → 관할법원
  "회원이 30일간 접속하지 않으면 동의한 것으로 본다" → 회원 통지

규칙
  - 2~10자. 명사구.
  - 약관규제법 조문 제목(면책조항의 금지, 손해배상액의 예정, 의사표시의 의제 등)을
    **그대로 쓰지 마라.** 계약서 작성자가 붙일 법한 평범한 말로 써라.
  - 조항이 유리한지 불리한지 드러내지 마라.

제목만 출력한다."""


def main():
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    rows = [r for r in csv.DictReader(EVAL.open(encoding="utf-8-sig"))
            if r["정답"] and r["정답"] not in ("제외", "보류")]
    cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = [r for r in rows if r["번호"] not in cache]
    print(f"조항 {len(rows)}개 — 제목 생성 필요 {len(todo)}개")

    def make(r):
        c = client.chat.completions.create(
            model=MODEL, max_tokens=30, temperature=0,
            messages=[{"role": "system", "content": SYS},
                      {"role": "user", "content": r["본문"]}])
        return (c.choices[0].message.content or "").strip().strip('"')

    if todo:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for r, t in zip(todo, ex.map(make, todo)):
                cache[r["번호"]] = t
        OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n=== 생성된 제목 예시 ===")
    for r in rows[:8]:
        print(f"  [{cache[r['번호']]:<10}] {r['본문'][:60]}")


if __name__ == "__main__":
    main()
