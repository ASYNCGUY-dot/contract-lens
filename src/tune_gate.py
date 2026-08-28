# -*- coding: utf-8 -*-
"""
관련성 게이트 프롬프트를 여러 개 재서 고른다.

첫 판(A)은 정확도를 31%→50%로 올렸지만 **관련 조항 10개 중 8개를 버렸다.**
"애매하면 false"가 너무 셌다. 무관을 걸러내되 관련 있는 것을 살리는 지점을 찾는다.

**표본이 작다.** '높음'이 붙은 관련 조항이 8개뿐이라 재현율의 신뢰구간이 매우 넓다.
여기서 고른 프롬프트는 "이 방향이 되는가"의 근거이지 최종 성능 보장이 아니다.

실행:  python src/tune_gate.py
"""

from __future__ import annotations

import csv
import hashlib
from concurrent.futures import ThreadPoolExecutor
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
CACHE = ROOT / "data" / "eval" / "gate_tune_cache.json"

COMMON = """조항이 다루는 사안이 유형이 말하는 사안과 같은지만 본다.
불공정한지, 무효인지, 누구에게 유리한지는 판단하지 않는다."""

PROMPTS = {
    "A 엄격(첫 판)": COMMON + """
같은 사안이면 true, 다른 사안이면 false.
애매하면 false. 어휘가 겹친다는 이유만으로 true 하지 마라.""",

    "B 균형": COMMON + """
그 유형을 다루는 조항이라면 true. 전혀 다른 사안이면 false.

  유형: 사업자의 손해배상 범위를 제한하는 조항
  "회사는 간접손해에 책임지지 않습니다"      → true   배상범위를 다룬다
  "보험금 청구 시 사고증명서를 제출한다"      → false  청구 절차이지 배상범위가 아니다

**그 유형에 해당할 여지가 있으면 true 로 둔다.** 최종 판단은 사람이 한다.
다만 사안이 분명히 다르면 false 다 — 어휘가 겹친다는 이유만으로 true 하지 마라.""",

    "C 사안대조": COMMON + """
두 단계로 본다.
  1) 이 유형이 규율하는 사안이 무엇인가 (예: 해지권 제한, 배상범위 축소, 관할 합의)
  2) 이 조항이 그 사안을 다루는가

1과 2가 맞으면 true. 조항이 절차·정의·일반 규정이면 false.""",
}


def key(p: str, clause: str, t: str) -> str:
    return hashlib.md5(f"{p}|{clause}|{t}".encode()).hexdigest()


def ask(client, sys_prompt: str, clause: str, t: str) -> bool:
    r = client.chat.completions.create(
        model=MODEL, max_tokens=8, temperature=0,
        response_format={"type": "json_schema", "json_schema": {
            "name": "rel", "strict": True,
            "schema": {"type": "object", "additionalProperties": False,
                       "required": ["해당"],
                       "properties": {"해당": {"type": "boolean"}}}}},
        messages=[{"role": "system", "content": sys_prompt},
                  {"role": "user", "content": f"유형: {t}\n조항: {clause}"}])
    return json.loads(r.choices[0].message.content)["해당"]


def main():
    from match_articles import ArticleMatcher

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    m = ArticleMatcher()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    rows = [r for r in csv.DictReader(
        (ROOT / "data" / "eval" / "eval_v3.csv").open(encoding="utf-8-sig"))
        if r["정답"] and r["정답"] not in ("제외", "보류")]

    # '높음'이 붙은 것만 대상. 게이트는 걸러내는 장치이므로 여기만 본다.
    targets = []
    for r in rows:
        hi = [c for c in m.match("", r["본문"]) if c["등급"] == "높음"]
        if hi:
            targets.append((r, hi, r["정답"] != "관련없음"))
    bp = sum(1 for _, _, p in targets if p)
    bn = len(targets) - bp
    print(f"'높음'이 붙은 것 {len(targets)}개 — 관련있음 {bp} / 무관 {bn}"
          f"  정확도 {bp/len(targets)*100:.1f}%\n")

    # 조문 하나에 유형이 여러 개라 호출 수가 많다. 캐시에 없는 것만 병렬로 채운다.
    def fill(name, sp):
        todo = []
        for r, hi, _ in targets:
            for c in hi:
                for t in [x["유형"] for x in m.types if str(x["조"]) == c["조"]]:
                    k = key(name, r["본문"], t)
                    if k not in cache:
                        todo.append((k, r["본문"], t))
        if not todo:
            return
        with ThreadPoolExecutor(max_workers=8) as ex:
            for k, v in zip([x[0] for x in todo],
                            ex.map(lambda x: ask(client, sp, x[1], x[2]), todo)):
                cache[k] = v
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    print(f"  {'프롬프트':16}{'관련 유지':>10}{'무관 제거':>10}{'정확도':>9}")
    for name, sp in PROMPTS.items():
        fill(name, sp)
        kp = kn = 0
        for r, hi, pos in targets:
            keep = False
            for c in hi:
                for t in [x["유형"] for x in m.types if str(x["조"]) == c["조"]]:
                    k = key(name, r["본문"], t)
                    if k not in cache:
                        cache[k] = ask(client, sp, r["본문"], t)
                    if cache[k]:
                        keep = True
                        break
                if keep:
                    break
            if keep:
                if pos:
                    kp += 1
                else:
                    kn += 1
        acc = kp / (kp + kn) * 100 if (kp + kn) else 0
        print(f"  {name:16}{kp:>4}/{bp:<5}{bn-kn:>5}/{bn:<4}{acc:8.1f}%")
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
