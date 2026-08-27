# -*- coding: utf-8 -*-
"""
LLM 구조 추출로 매칭을 개선하려던 시도. **실패했다. 채택하지 않았다.**

지우지 않고 남기는 이유는, 왜 안 되는지가 이 프로젝트에서 가장 중요한 발견이기
때문이다. 같은 시도를 다시 하지 않기 위해서도 필요하다.

## 가설과 근거

임베딩이 제7조와 제11조를 헷갈렸다. 구조로 보면 갈려야 한다고 봤다.

    제 7조  사업자의 의무·책임이 줄어든다
    제11조  고객의 권리·이익이 줄어든다

법 유형 24개에 구조를 뽑아보니 실제로 갈렸다(`structure_law.py`). 그리고 Top-1
오답 16건 중 13건이 구조가 다른 조문끼리의 혼동이어서, **상한이 94.5%로 계산됐다.**

## 재보니 나빠졌다

    기준(2단계 매칭)      Top-1 39/55 = 70.9%
    구조 재정렬 적용       Top-1 38/55 = 69.1%

## 왜 실패했나 — 태스크가 달랐다

조항 85개에 구조를 뽑으니 **59개(69%)가 "줄어드는 것 없음"이었다.** 그래서
재정렬이 적용된 문항이 11개뿐이었고, 그중에서도 손해가 났다.

원인은 모델이 틀린 것이 아니다. **묻는 질문이 달랐다.**

    매칭이 푸는 문제    이 조항은 무엇에 관한 것인가       (주제 분류)
    구조가 답하는 것    이 조항으로 누가 무엇을 잃는가      (불이익 구조)

평가 세트는 표준약관(행정규칙)으로 만들었고, 표준약관은 심사를 거친 것이라
**대부분 중립적으로 쓰여 있다.** "줄어드는 것 없음"은 모델의 실패가 아니라
정확한 답이었다. 재판관할 조항은 중립적으로 쓰여도 여전히 제14조 주제다.

## 구조 유무 자체를 신호로 쓰는 것도 확인했지만 못 쓴다

전체로 보면 갈리는 것처럼 보인다.

    구조 잡힘  22/25 = 88% 가 실제 관련 있음
    구조 없음  33/60 = 55%

그런데 정작 판단이 필요한 '참고' 구간(0.43~0.50)에서는 **구조 잡힘이 5건뿐**이라
(3/5 대 8/18) 아무것도 말할 수 없다. 임베딩이 이미 잘 맞히는 곳에서만 신호가
강하면 보탤 것이 없다. 표본을 늘리기 전에는 채택하지 않는다.

## 그러면 구조 추출의 제자리는 어디인가

**조문을 찾는 일이 아니라, 찾은 뒤에 보여주는 일이다.** 매칭이 관련 조문을 대고,
구조가 "이 조항은 실제로 사업자의 책임이 줄어드는 형태다"를 덧붙이는 순서다.
근거를 보여주되 판정하지 않는다는 원칙과도 이 쪽이 맞는다.

실행:  python src/try_structure_filter.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
LAW_ST = ROOT / "data" / "laws" / "유형_구조.json"
EVAL_ST = ROOT / "data" / "eval" / "구조_v2.json"


def law_profile() -> dict:
    """조문별 구조 = 그 조 유형들의 다수결."""
    by = {}
    for v in json.loads(LAW_ST.read_text(encoding="utf-8")).values():
        by.setdefault(str(v["조"]), []).append((v.get("줄어드는것"), v.get("줄어드는쪽")))
    return {k: Counter(v).most_common(1)[0][0] for k, v in by.items()}


def main():
    from match_articles import ArticleMatcher
    from compare_matchers import load_labeled, NONE

    st = json.loads(EVAL_ST.read_text(encoding="utf-8"))
    prof = law_profile()
    rows = load_labeled()
    pos = [r for r in rows if r["_g"] != NONE]
    m = ArticleMatcher()

    def has(n):
        return st.get(n, {}).get("줄어드는것") not in (None, "없음")

    print("=== 조항 쪽 구조가 잡힌 비율 ===")
    print(f"  관련있음 {sum(1 for r in pos if has(r['번호']))}/{len(pos)}"
          f"   관련없음 {sum(1 for r in rows if r['_g'] == NONE and has(r['번호']))}/30")

    base = filt = applied = 0
    for r in pos:
        res = m.match(r["조제목"], r["본문"], floor=0.0)
        if not res:
            continue
        base += res[0]["조"] == r["_g"]
        if has(r["번호"]):
            s = st[r["번호"]]
            key = (s.get("줄어드는것"), s.get("줄어드는쪽"))
            ok = [c for c in res if prof.get(c["조"]) == key]
            if ok:
                applied += 1
                res = ok + [c for c in res if c not in ok]
        filt += res[0]["조"] == r["_g"]

    print(f"\n=== 구조 재정렬 — 적용된 문항 {applied}/{len(pos)} ===")
    print(f"  기준      Top-1 {base}/{len(pos)} = {base/len(pos)*100:.1f}%")
    print(f"  구조 적용  Top-1 {filt}/{len(pos)} = {filt/len(pos)*100:.1f}%")
    print("\n  → 나빠졌다. 채택하지 않는다. 이유는 이 파일 맨 위 설명을 볼 것.")


if __name__ == "__main__":
    main()
