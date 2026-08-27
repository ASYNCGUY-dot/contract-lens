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

## 임계값 — 자르지 않고 등급을 나눈다

**결정(2026-08-27): 놓치는 것을 최소화한다.** 이 서비스는 판정하지 않고 근거만 보여주므로
오탐은 사용자가 보고 넘기면 되지만 미탐은 아예 안 보인다.

그런데 선 하나로 0.43에서 자르면 관련없음 30개 중 20개에 조문이 붙어
"아무 조항에나 조문 붙이네"가 된다. 그래서 **자르는 대신 등급을 나눴다.**

    높음  0.50 이상    관련있음 42 / 관련없음  6     눈에 띄게 보여준다
    참고  0.43~0.50    관련있음 11 / 관련없음 12     약하게, 접어서 보여준다
    없음  0.43 미만    관련있음  2 / 관련없음 12     보여주지 않는다

눈에 띄게 보여주는 48건 중 42건이 실제 관련(87.5%)이고, 애매한 23건은 "참고"로
내려가며, 놓치는 것은 2건뿐이다. **선을 옮기는 대신 확신도를 드러내니 둘 다 얻었다.**

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
STRONG = 0.50              # 이 위는 '높음', 사이는 '참고'


def grade(score: float) -> str:
    return "높음" if score >= STRONG else "참고"


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

        q = encode([f"{title}. {body}"])[0]
        wide = self._wide @ q
        order = np.argsort(-wide)[:top_k]
        cands = [self.arts[k] for k in order]

        narrow = self._narrow_by_article(q)
        cands.sort(key=lambda a: -narrow[self.arts.index(a)])   # 2단계 재정렬

        f = DEFAULT_FLOOR if floor is None else floor
        out = []
        for a in cands:
            k = self.arts.index(a)
            if wide[k] < f:
                continue
            out.append({
                "조": a,
                "인용": f"약관의 규제에 관한 법률 제{a}조",
                "제목": self.titles[a],
                "등급": grade(float(wide[k])),
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
            print(f"   [{r['등급']}] 제{r['조']:>2}조 {r['제목']:12} "
                  f"넓은 {r['넓은점수']:.4f} / 좁은 {r['좁은점수']:.4f}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        cmd_demo()
    else:
        print(__doc__)
