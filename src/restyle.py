# -*- coding: utf-8 -*-
"""
평가 세트 조항의 **문체만** 실제 계약서투로 바꾼 대조군을 만든다.

10번에서 임베딩이 내용이 아니라 문체를 재고 있음을 확인했다. 그런데 평가 세트는
표준약관(행정규칙)이라 이미 법조문 문체다. **그래서 평가 세트로는 이 문제를
잴 수가 없다.** 재려면 같은 조항의 문체만 다른 짝이 있어야 한다.

    원본    표준약관 문체 (법조문투)     이미 갖고 있다
    변환    실제 사설 계약서 문체        여기서 만든다

라벨은 그대로 쓴다. 조항의 **내용이 안 바뀌었으므로 관련 조문도 안 바뀐다.**
이렇게 하면 라벨링 비용 없이 문체 효과만 분리해서 잴 수 있다.

**이건 LLM이 만든 데이터이지 실제 수집 데이터가 아니다.** 실제 사설 약관을
구해 재는 것을 대신하지 못한다. 문체가 원인인지 아닌지를 가리는 용도로만 쓴다.

실행:  python src/restyle.py --probe   5개만 재본다
       python src/restyle.py           관련있음 55개 전부
출력:  data/eval/restyled.json
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

OUT = ROOT / "data" / "eval" / "restyled.json"
MODEL = "gpt-4o-mini"

SYS = """너는 법령 문체를 실제 사설 계약서 문체로 바꾸는 일만 한다.

바꾸는 것: 문체와 어투만.
  - "~하는 조항", "~하여야 한다" 같은 법령투를 "회사는 ~합니다", "~하지 아니한다" 같은
    실제 이용약관 문장으로 바꾼다.
  - 주어를 '회사', '회원', '이용자' 등 계약서에서 실제 쓰는 말로 쓴다.

절대 바꾸지 않는 것: 내용, 의미, 누가 무엇을 하는지, 유리·불리 관계.
  - 의무를 권리로 바꾸지 마라. 주체를 뒤집지 마라. 조건을 빼거나 더하지 마라.
  - 법률 용어(해지권, 항변권, 담보책임 등)는 그대로 둔다.

한 문장 또는 두 문장으로. 설명 없이 바뀐 문장만 출력한다."""


def restyle(client: OpenAI, title: str, body: str) -> str:
    r = client.chat.completions.create(
        model=MODEL, max_tokens=400, temperature=0,
        messages=[{"role": "system", "content": SYS},
                  {"role": "user", "content": f"[{title}] {body}"}],
    )
    if r.choices[0].finish_reason == "length":
        raise RuntimeError("출력이 잘렸다")
    return (r.choices[0].message.content or "").strip()


def main():
    from compare_matchers import load_labeled, NONE

    probe = "--probe" in sys.argv
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    rows = [r for r in load_labeled() if r["_g"] != NONE]
    if probe:
        rows = rows[:5]
    cache = json.loads(OUT.read_text(encoding="utf-8")) if (OUT.exists() and not probe) else {}
    print(f"조항 {len(rows)}개 — 캐시 {len(cache)}개\n")

    for i, r in enumerate(rows, 1):
        if r["번호"] in cache:
            continue
        try:
            new = restyle(client, r["조제목"], r["본문"])
        except Exception as e:
            print(f"  [{i}] 실패: {e}")
            continue
        cache[r["번호"]] = new
        if probe:
            print(f"  [{i}] 정답 제{r['_g']}조")
            print(f"      원본: {r['본문'][:88]}")
            print(f"      변환: {new[:88]}\n")
        elif i % 10 == 0:
            print(f"  {i}/{len(rows)} …")

    if not probe:
        OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n완료 {len(cache)}개 → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
