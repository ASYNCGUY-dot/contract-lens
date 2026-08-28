# -*- coding: utf-8 -*-
"""
조 단위 매칭 — 2단계. 계약서 조항이 약관규제법 어느 조문과 관련되는지 후보를 낸다.

**판정하지 않는다.** "이 조항이 제9조와 관련돼 보인다"까지만 말하고 조문 원문을 나란히 놓는다.

## 왜 2단계인가 (라벨 55개로 실측)

    A  조별로 유형을 이어붙여 벡터 1개      Top-1 65.5%  Top-3 94.5%
    B  유형별 벡터 + 조별 최대              Top-1 70.9%  Top-3 87.3%
    A로 후보 3개 → B로 재정렬              Top-1 70.9%  Top-3 94.5%   ← 채택

A는 넓게 잘 잡고(Top-3 94.5%) B는 좁게 잘 고른다(Top-1 70.9%). 순서대로 쓰면 둘 다 얻는다.

가중합 `0.7A + 0.3B`가 Top-1 72.7%로 1건 더 맞혔지만 **채택하지 않았다.**
그 0.7은 표본 55개에서 고른 값이라 과적합 위험이 있고, 1건 차이는 통계적으로 같다.
**자유 파라미터가 없는 쪽이 견고하다.**

## 확인된 것

- **조 제목을 조항 입력에 넣어야 한다.** 빼면 Top-1이 70.9% → 58.2%로 떨어진다.
- **조 제목을 유형 쪽에 붙이면 오히려 나빠진다** (61.8%). 입력에만 넣는다.
- 제11조 흡수가 12/19 → 5/16으로 줄었다. 유형을 이어붙이지 않은 효과다.

## 확신도를 표시하지 않는다 — 순위만 준다 (2026-08-28 결정)

한동안 '높음/참고' 두 등급을 썼다. 표준약관에서는 '높음' 정확도가 90%에 가까웠다.
그런데 **실제 사설 약관(v3)에서 재보니 25%였다.** 판별력을 만들려고 네 갈래를
시도했고 전부 실패했다(13~16번 모듈).

    법 조문 오염 제거    26.3% → 31.2%   필요했지만 원인이 아니었다
    점수 분포의 모양      갈리지 않음      임베딩에서 나올 신호가 없다
    LLM 관련성 게이트     50%지만 관련 8개 중 6개를 잃는다
    조문별 신뢰도        v3에서 악화      도메인이 바뀌면 순위가 뒤집힌다

**'높음'이라 써놓고 실제로 맞을 확률이 25%면 그 표시는 사용자를 속이는 것이다.**
확신도를 표시하려면 그 확신에 근거가 있어야 하는데 지금은 없다. 그래서 없앴다.

대신 **관련도 순으로 최대 3개**를 준다. Top-3가 75%이므로 "이 셋 중에 있을
가능성이 높다"까지는 말할 수 있다. 다만 **1순위가 맞을 확률은 41.7%로 절반이
안 된다.** 순서를 정답 순서로 읽으면 안 되고, 그 점을 사용자에게 알려야 한다.

이건 후퇴가 아니라 "판정하지 않는다"는 원칙을 확신도 표시에까지 적용한 것이다.

## 문서 메타 조항은 건너뛴다

목적·정의처럼 계약 내용이 아니라 문서 자체를 설명하는 조항은 어느 약관에나 있고
늘 비슷하게 쓰여서, 내용과 무관하게 점수가 뜬다(목적 0.5743). 문턱을 올리는 것으로는
부족하다 — 목적 조항이 0.57이라 0.50 문턱을 넘는다.

**실측 근거**: 표준약관에서 메타 제목 조항 30개 중 실제로 관련 있던 것은 1개(3.3%)다.
그래서 후보를 내지 않고 건너뛴다. 다만 **제목이 메타 단어만으로 되어 있을 때만**이다.
그 1개가 "이용시간 및 서비스 중단"이었는데, 복합 제목은 다른 사안을 함께 담기 때문이다.

건너뛴 사실은 `건너뜀` 필드로 알린다. **조용히 버리지 않는다.**

## 문턱

미탐과 오탐이 0.50 부근에서 교차한다. 판정하지 않고 근거만 보여주는 서비스라
**안 보이는 쪽이 더 아프다**고 보아 0.43으로 둔다.

실행:  python src/match_articles.py --demo
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
LAW_TYPES = ROOT / "data" / "laws" / "약관규제법_유형.json"

# 미탐을 오탐보다 무겁게 본다. 근거는 위 임계값 설명.
DEFAULT_FLOOR = 0.43       # 이 아래는 보여주지 않는다
META_FLOOR = 0.50          # 메타 제목 조항은 이 위에서만 보여준다

# 계약 내용이 아니라 문서 자체를 설명하는 조항. 목적·정의 조항은 어느 약관에나
# 있고 늘 비슷하게 쓰여서, 실제 내용과 무관하게 점수가 뜬다(목적 0.57 대 정의 0.46).
# 이 목록은 새로 만든 것이 아니라 build_eval_v2.py 가 무관계열 표본을 뽑을 때
# 쓴 것과 같다. 실측: '높음'에 섞인 오탐 6건 → 1건, 대신 1건이 높음에서 참고로 내려갔다.
# **지우지 않고 한 단계 낮추기만 한다.** 판정하지 않는다는 원칙이 여기에도 적용된다.
META_TITLE = ["목적", "정의", "용어", "재검토기한", "시행", "적용범위", "이용시간", "유효기간"]


def is_meta(title: str) -> bool:
    """제목이 메타 단어'만'으로 되어 있는가. 복합 제목은 아니다."""
    t = (title or "").strip()
    if not t:
        return False
    rest = t
    for w in META_TITLE:
        rest = rest.replace(w, "")
    # 남는 것이 조사·기호뿐이면 순수 메타 제목이다
    return not rest.strip(" ·및,()/등의ㆍ-")


class ArticleMatcher:
    def __init__(self):
        from match_clauses import encode

        types = json.loads(LAW_TYPES.read_text(encoding="utf-8"))["유형"]
        # 제6조(일반원칙)는 뺀다 — 거의 모든 조항에 걸려 후보로서 의미가 없다
        self.types = [t for t in types if t["조"] != 6]
        self.arts = sorted({str(t["조"]) for t in self.types}, key=int)
        self.titles = {str(t["조"]): t["조제목"] for t in self.types}

        # 1단계: 조별로 유형을 이어붙인 벡터 (넓게 잡는다)
        wide = []
        for a in self.arts:
            body = " ".join(t["유형"] for t in self.types if str(t["조"]) == a)
            wide.append(f"{self.titles[a]}. {body}")
        self._wide = encode(wide)

        # 2단계: 유형별 벡터 (좁게 고른다)
        self._narrow = encode([t["유형"] for t in self.types])
        self._owner = [str(t["조"]) for t in self.types]

    def _narrow_by_article(self, q: np.ndarray) -> np.ndarray:
        sim = self._narrow @ q
        out = np.full(len(self.arts), -1.0)
        for j, o in enumerate(self._owner):
            k = self.arts.index(o)
            out[k] = max(out[k], sim[j])
        return out

    def match(self, title: str, body: str, top_k: int = 3,
              floor: float | None = None) -> list[dict]:
        """
        (조제목, 본문)을 받아 관련 조문 후보를 준다.
        floor 미만이면 후보를 내지 않는다 — '관련 조문 없음'이 정직한 답이다.
        """
        from match_clauses import encode

        meta = is_meta(title)
        q = encode([f"{title}. {body}"])[0]
        wide = self._wide @ q
        order = np.argsort(-wide)[:top_k]
        cands = [self.arts[k] for k in order]

        narrow = self._narrow_by_article(q)
        cands.sort(key=lambda a: -narrow[self.arts.index(a)])   # 2단계 재정렬

        # 메타 조항은 후보를 내지 않는다 (실측 30개 중 관련 있던 것 1개)
        if meta and floor is None:
            return []
        f = DEFAULT_FLOOR if floor is None else floor
        out = []
        rank = 0
        for a in cands:
            k = self.arts.index(a)
            if wide[k] < f:
                continue
            rank += 1
            out.append({
                "순위": rank,
                "조": a,
                "인용": f"약관의 규제에 관한 법률 제{a}조",
                "제목": self.titles[a],
                "넓은점수": round(float(wide[k]), 4),
                "좁은점수": round(float(narrow[k]), 4),
                "유형": [t["유형"] for t in self.types if str(t["조"]) == a],
            })
        return out


def cmd_demo():
    m = ArticleMatcher()
    samples = [
        ("손해배상", "회사는 회원에게 발생한 어떠한 손해에 대하여도 일체 책임을 지지 않습니다."),
        ("재판관할", "이 계약에 관한 소송의 관할법원은 회사의 본점 소재지 법원으로 한다."),
        ("회원에 대한 통지", "회원이 30일간 로그인하지 않으면 서비스 이용에 동의한 것으로 봅니다."),
        ("이용시간", "본 서비스는 매일 오전 9시부터 오후 6시까지 운영합니다."),
    ]
    for title, body in samples:
        print(f"\n[{title}] {body[:56]}")
        res = m.match(title, body)
        if not res:
            print(f"   관련 조문 없음 (임계값 {DEFAULT_FLOOR} 미만)")
        for r in res:
            print(f"   {r['순위']}순위  제{r['조']:>2}조 {r['제목']:12} "
                  f"넓은 {r['넓은점수']:.4f} / 좁은 {r['좁은점수']:.4f}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        cmd_demo()
    else:
        print(__doc__)
