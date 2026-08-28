# -*- coding: utf-8 -*-
"""
조항대조 파이프라인 — 약관 텍스트를 넣으면 조항마다 관련 조문을 나란히 놓는다.

지금까지 만든 조각(파서·매칭·구조 추출)이 따로 놀았다. 여기서 잇는다.
**판정하지 않는다.** 관련 조문과 등급을 대고, 원문을 나란히 놓는 데서 멈춘다.

    parse      텍스트 → 조 단위 조항          (parse_clauses)
    match      조항마다 관련 조문 후보         (match_articles, 조항별 fan-out)
    describe   상위 후보가 뚜렷할 때만 구조 덧붙임  (extract_structure, 선택)
    collect    결과 조립

## 왜 fan-out 인가

조항 25개를 순서대로 돌리면 앞 조항이 끝나야 뒤가 시작한다. 조항끼리는 서로
의존하지 않으므로 갈라서 처리하고 리듀서로 합치는 편이 맞다. 복습 실습에서
쓴 `Annotated[list, operator.add]`가 이 자리에 쓰인다.

## 왜 구조 추출을 일부에만 부르는가

LLM 호출은 조항당 한 번씩 돈과 시간을 쓴다. 그런데 9번 모듈에서 확인했듯이
구조는 **조문을 찾는 데는 도움이 안 되고, 찾은 뒤 보여주는 데만 쓸모가 있다.**
관련 조문이 약하게 걸린 조항에까지 부를 이유가 없어 1순위 점수가 0.50 이상일
때만 부른다.

실행:
    python src/pipeline.py --demo            내장 예시 약관으로
    python src/pipeline.py --file 파일.txt   실제 파일로
    python src/pipeline.py --demo --llm      구조 추출까지 (API 호출 발생)
"""

from __future__ import annotations

import operator
import sys
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

_matcher = None


def matcher():
    """모델 적재가 무거우므로 한 번만 만든다."""
    global _matcher
    if _matcher is None:
        from match_articles import ArticleMatcher
        _matcher = ArticleMatcher()
    return _matcher


class State(TypedDict, total=False):
    문서명: str
    문단: list[str]
    조항: list[dict]
    llm: bool
    결과: Annotated[list, operator.add]
    요약: dict


class ClauseTask(TypedDict):
    조항: dict
    llm: bool


def n_parse(s: State) -> dict:
    from parse_clauses import parse_document

    d = parse_document(s["문단"])
    return {"조항": d.get("clauses", []), "요약": {"status": d.get("status")}}


def fan_out(s: State):
    """조항마다 갈라 보낸다. 조항이 없으면 곧장 조립으로."""
    if not s.get("조항"):
        return "collect"
    return [Send("match", {"조항": c, "llm": s.get("llm", False)})
            for c in s["조항"]]


def n_match(t: ClauseTask) -> dict:
    c = t["조항"]
    title = c.get("제목") or ""
    body = (c.get("본문") or "").strip()
    if not body:
        return {"결과": []}

    from match_articles import is_meta
    cands = matcher().match(title, body)
    item = {"조": c.get("표시"), "제목": title, "본문": body, "후보": cands}
    if is_meta(title):
        # 조용히 버리지 않는다. 왜 후보가 없는지 사용자가 알아야 한다.
        item["건너뜀"] = "문서 자체를 설명하는 조항(목적·정의 등)이라 대조하지 않았습니다."

    # 근거를 보여주는 용도지 찾는 용도가 아니다(9번 모듈).
    if t["llm"] and cands and cands[0]["넓은점수"] >= 0.50:
        try:
            from extract_structure import extract, verify_quote
            st = extract(f"{title}. {body}")
            q = st.get("근거문구", "")
            st["_검증"] = bool(q) and verify_quote(f"{title}. {body}", q)
            item["구조"] = st
        except Exception as e:
            item["구조_실패"] = str(e)[:80]
    return {"결과": [item]}


def n_collect(s: State) -> dict:
    res = sorted(s.get("결과", []), key=lambda x: x.get("조") or "")
    hi = sum(1 for r in res if r["후보"] and r["후보"][0]["넓은점수"] >= 0.50)
    none = sum(1 for r in res if not r["후보"])
    return {"결과": [], "요약": {**s.get("요약", {}), "조항": len(res),
                              "뚜렷함": hi, "관련없음": none, "정렬": res}}


def build():
    g = StateGraph(State)
    g.add_node("parse", n_parse)
    g.add_node("match", n_match)
    g.add_node("collect", n_collect)
    g.add_edge(START, "parse")
    g.add_conditional_edges("parse", fan_out, ["match", "collect"])
    g.add_edge("match", "collect")
    g.add_edge("collect", END)
    return g.compile()


def run(paragraphs: list[str], name: str = "", llm: bool = False) -> dict:
    out = build().invoke({"문서명": name, "문단": paragraphs, "llm": llm, "결과": []})
    return out["요약"]


DEMO = [
    "제1조 (목적) 이 약관은 회사가 제공하는 서비스의 이용조건을 정함을 목적으로 한다.",
    "제2조 (서비스 이용시간) 서비스는 연중무휴 1일 24시간 제공함을 원칙으로 한다.",
    "제3조 (면책) 회사는 회원에게 발생한 어떠한 손해에 대하여도 일체 책임을 지지 아니한다.",
    "제4조 (회원 통지) 회원이 30일간 접속하지 아니하면 서비스 이용에 동의한 것으로 본다.",
    "제5조 (관할법원) 이 약관에 관한 소송의 관할법원은 회사의 본점 소재지 법원으로 한다.",
]


def main():
    llm = "--llm" in sys.argv
    if "--file" in sys.argv:
        p = Path(sys.argv[sys.argv.index("--file") + 1])
        paras = [x.strip() for x in p.read_text(encoding="utf-8").split("\n") if x.strip()]
        name = p.name
    else:
        paras, name = DEMO, "예시 약관"

    r = run(paras, name, llm)
    print("")
    print(f"{name} — 조항 {r['조항']}개 / 상위 후보가 뚜렷한 것 {r['뚜렷함']}개 / "
          f"관련 조문 없음 {r['관련없음']}개")
    print("  ※ 순서는 관련 가능성 추정이다. 1순위가 정답일 확률은 실측 41.7%다.")
    print("")
    for x in r["정렬"]:
        print(f"  {x['조']} {x['제목']}")
        if x.get("건너뜀"):
            print(f"      건너뜀 — {x['건너뜀']}")
        elif not x["후보"]:
            print("      관련 조문 없음")
        for c in x["후보"]:
            print(f"      {c['순위']}순위  {c['인용']} ({c['제목']})  {c['넓은점수']:.4f}")
        if "구조" in x:
            s = x["구조"]
            print(f"      구조: {s.get('줄어드는쪽')}의 {s.get('줄어드는것')}가 줄어든다"
                  f"  근거검증 {'통과' if s.get('_검증') else '실패'}")
        print()


if __name__ == "__main__":
    main()
