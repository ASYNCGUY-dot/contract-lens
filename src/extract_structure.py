# -*- coding: utf-8 -*-
"""
조항 문장에서 **구조만** 뽑는다. 판정하지 않는다.

임베딩 단독 매칭이 방향성을 못 봐서 실패했다(같은 어휘면 정반대 조항도 붙는다).
그래서 LLM에게 "이 조항이 불공정한가"를 묻지 않고 **문장의 구조**만 묻는다.

    주어        이 조항의 문법적 주체
    행위유형    책임배제 / 권리제한 / 권리부여 / 의무부과 / 의무면제 / 기타
    줄어드는것  의무·책임 / 권리·이익 / 없음
    줄어드는쪽  위에서 줄어드는 것을 원래 갖고 있던 당사자
    근거문구    위 판단의 근거가 된 **원문 그대로의** 구절

법적 평가는 하지 않는다. 최종 대조는 규칙이 한다.

**근거문구는 원문에 실제로 있는지 문자열로 대조한다.** 없으면 환각이므로 버린다.
복습 실습 3에서 만든 검증과 같은 방식이다.

1차 프로브에서 '영향받는쪽'이 8/8 전부 "없음"이었다. "유·불리 판단은 하지 마라"고
해놓고 "불리해지는 쪽을 고르라"고 물어서 모순이었고, 모델이 안전하게 도망갔다.
유·불리를 묻지 말고 **누구의 무엇이 줄어드는가**를 기계적으로 물으니 갈렸다.

실행:  python src/extract_structure.py --probe   조항 20개로 되는지 재본다
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import openai
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(r"C:/WORK/WORK/.env")          # OPENAI_API_KEY는 공용 .env에 있다

MODEL = "gpt-4o-mini"
MAX_TOKENS = 400
TIMEOUT = 30

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=TIMEOUT)

ACTS = ["책임배제", "권리제한", "권리부여", "의무부과", "의무면제", "기타"]
PARTIES = ["사업자", "고객", "쌍방", "불명"]
REDUCED = ["의무·책임", "권리·이익", "없음"]

SCHEMA = {
    "name": "clause_structure",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "주어": {"type": "string", "enum": PARTIES},
            "행위유형": {"type": "string", "enum": ACTS},
            "줄어드는것": {"type": "string", "enum": REDUCED},
            "줄어드는쪽": {"type": "string", "enum": PARTIES + ["없음"]},
            "근거문구": {"type": "string"},
        },
        "required": ["주어", "행위유형", "줄어드는것", "줄어드는쪽", "근거문구"],
        "additionalProperties": False,
    },
}

SYSTEM = """너는 계약 조항의 문장 구조만 기계적으로 분석한다.
유리한지 불리한지, 공정한지 불공정한지는 **묻지 않았으니 판단하지 마라.**

- 주어: 이 조항의 문법적 주체
- 행위유형: 조항이 하는 일
    책임배제  책임·배상을 지우거나 줄인다
    권리제한  권리 행사를 막거나 요건을 무겁게 한다
    권리부여  권리·재량을 준다
    의무부과  의무를 지운다
    의무면제  의무를 면해 준다
    기타      위 어디에도 안 맞는다
- 줄어드는것: 이 조항으로 **줄어드는 대상이 무엇인지**
    의무·책임   누군가가 지던 의무나 책임이 줄어든다
    권리·이익   누군가가 갖던 권리나 이익이 줄어든다
    없음       줄어드는 것이 없다 (안내·정의·절차 등)
- 줄어드는쪽: 위에서 줄어드는 것을 원래 갖고 있던 당사자. 없으면 "없음"
- 근거문구: 위 판단의 근거가 된 구절을 **원문에서 그대로** 복사한다. 요약·수정 금지.

예시 (이 구분이 핵심이다):
  "사업자는 손해를 배상하지 아니한다"
      → 행위유형=책임배제, 줄어드는것=의무·책임, 줄어드는쪽=사업자
  "사업자는 위약금을 청구하지 않는다"
      → 행위유형=의무면제, 줄어드는것=권리·이익, 줄어드는쪽=사업자
  "고객은 이의를 제기할 수 없다"
      → 행위유형=권리제한, 줄어드는것=권리·이익, 줄어드는쪽=고객

애매하면 "불명"과 "기타"를 쓴다. 억지로 고르지 않는다."""


class ExtractError(Exception):
    """추출 실패. 호출부는 이 조항을 '구조 확인 불가'로 처리한다."""


def extract(clause: str) -> dict:
    try:
        r = client.chat.completions.create(
            model=MODEL, max_tokens=MAX_TOKENS,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": clause}],
            response_format={"type": "json_schema", "json_schema": SCHEMA},
        )
    except openai.OpenAIError as e:
        raise ExtractError(f"{type(e).__name__}: {e}") from e

    choice = r.choices[0]
    # 스키마를 강제해도 잘림은 못 막는다. 잘린 JSON은 성공이 아니다.
    if choice.finish_reason == "length":
        raise ExtractError(f"응답이 max_tokens({MAX_TOKENS})에서 잘렸다")
    if getattr(choice.message, "refusal", None):
        raise ExtractError(f"모델이 거부했다: {choice.message.refusal}")

    try:
        out = json.loads(choice.message.content)
    except json.JSONDecodeError as e:
        raise ExtractError(f"JSON 파싱 실패: {e}") from e
    if not isinstance(out, dict) or "행위유형" not in out:
        raise ExtractError("응답 스키마 불일치")

    out["_usage"] = {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens}
    return out


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def verify_quote(clause: str, quote: str) -> bool:
    """근거문구가 원문에 실제로 있는가. 공백 차이는 무시한다."""
    q = squash(quote)
    return bool(q) and q in squash(clause)


def cmd_probe():
    """조항 20개로 이 방식이 되는지 재본다. 안 되면 여기서 접는다."""
    # 임베딩이 오탐한 것(적법) + 명백한 불공정 + 표준약관 무작위
    labeled = [
        # (조항, 사람이 본 방향, 비고)
        ("회사는 회원에게 발생한 어떠한 손해에 대하여도 일체 책임을 지지 않습니다.", "불공정", "면책"),
        ("사업자는 천재지변 등 어떠한 경우에도 회원의 손해를 배상하지 아니합니다.", "불공정", "면책"),
        ("이 계약에 관한 소송의 관할법원은 회사의 본점 소재지 법원으로 한다.", "불공정", "관할"),
        ("회원이 30일간 로그인하지 않으면 서비스 이용에 동의한 것으로 봅니다.", "불공정", "의사표시 의제"),
        ("소비자는 계약기간 중 언제든지 그 계약을 해지할 수 있습니다.", "적법", "고객에게 권리 부여"),
        ("이용자는 사업자가 「개인정보 보호법」을 위반한 행위로 손해를 입으면 사업자에게 "
         "손해배상을 청구할 수 있습니다.", "적법", "고객에게 권리 부여"),
        ("사업자는 이용자에게 청약철회등을 이유로 위약금이나 손해배상을 청구하지 않습니다.",
         "적법", "사업자 청구 포기 — 규칙이 헷갈렸던 반례"),
        ("본 서비스는 매일 오전 9시부터 오후 6시까지 운영합니다.", "무관", "운영 안내"),
    ]

    ok = fail = 0
    halluc = 0
    cost = 0.0
    print(f"{'사람':5} {'주어':5} {'행위유형':7} {'줄어드는것':8} {'줄어드는쪽':7} {'인용':4}  조항")
    print("-" * 104)
    for clause, human, note in labeled:
        try:
            r = extract(clause)
        except ExtractError as e:
            fail += 1
            print(f"{human:5} {'추출 실패':>22}  {str(e)[:40]}")
            continue
        ok += 1
        good = verify_quote(clause, r["근거문구"])
        if not good:
            halluc += 1
        u = r["_usage"]
        cost += u["in"] / 1e6 * 0.15 + u["out"] / 1e6 * 0.60
        print(f"{human:5} {r['주어']:5} {r['행위유형']:7} {r['줄어드는것']:8} "
              f"{r['줄어드는쪽']:7} {'O' if good else 'X':4}  {clause[:40]}")
        if not good:
            print(f"{'':28}근거문구가 원문에 없다: {r['근거문구'][:50]!r}")

    print("-" * 104)
    print(f"추출 성공 {ok} / 실패 {fail} / 근거문구 환각 {halluc}")
    print(f"비용 약 ${cost:.5f}")


if __name__ == "__main__":
    if "--probe" in sys.argv:
        cmd_probe()
    else:
        print(__doc__)
