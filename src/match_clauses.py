# -*- coding: utf-8 -*-
"""
계약서 조항을 약관규제법 불공정 유형 28개와 대조한다.

**여기가 이 프로젝트에서 AI가 관여하는 유일한 지점이다.** 나머지는 전부 조회다.
그래서 정확도를 재야 하는 곳도 여기뿐이다.

판정하지 않는다. "이 조항이 제7조 1호 유형과 형태가 비슷하다"까지만 말하고,
법적 효력은 조문 원문을 그대로 보여준다.

임계값은 **이 데이터로 직접 재서** 정한다. 남의 숫자를 가져오면 안 된다 —
같은 코사인 유사도라도 모델과 코퍼스가 바뀌면 뜻이 완전히 달라진다.

실행:
    python src/match_clauses.py --calibrate   임계값을 정하기 위한 분포 측정
    python src/match_clauses.py --demo        표준약관 조항 몇 개를 실제로 대조
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LAW_TYPES = ROOT / "data" / "laws" / "약관규제법_유형.json"
PARSED = ROOT / "data" / "terms" / "parsed.jsonl"

# 모델 선택은 실측으로 정했다. 같은 샘플 4개(면책·관할·의사표시의제·무관)에서:
#   e5-small        1위 정답 1/3, 관련최저 0.8556 / 무관 0.8370 → 간격 +0.0186
#   ko-sroberta     1위 정답 3/3, 관련최저 0.4607 / 무관 0.1994 → 간격 +0.2613
#   paraphrase-mml  1위 정답 1/3, 간격 +0.2582
# 한국어 법률 문장에는 한국어 특화 모델이 맞다. e5는 무관한 조항도 0.83이 나와
# 임계값을 걸 자리가 없다.
MODEL_ID = "jhgan/ko-sroberta-multitask"
_model = None


def get_model():
    """모듈 전역 캐시. 호출마다 로드하면 매번 수 초씩 잡아먹는다."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_ID)
    return _model


def encode(texts: list[str], is_query: bool = False) -> np.ndarray:
    # e5 계열만 query:/passage: 접두어를 쓴다. ko-sroberta는 접두어 없이 학습돼서
    # 붙이면 오히려 방해가 된다. 모델을 바꾸면 전처리도 같이 바꿔야 한다.
    if "e5" in MODEL_ID.lower():
        prefix = "query: " if is_query else "passage: "
        texts = [prefix + t for t in texts]
    return get_model().encode(texts, normalize_embeddings=True)


def load_types() -> list[dict]:
    return json.loads(LAW_TYPES.read_text(encoding="utf-8"))["유형"]


def load_clauses() -> list[dict]:
    """파싱된 약관에서 조항을 평평하게 편다. 항 단위로 본다 — 조는 너무 길다."""
    out = []
    for line in PARSED.open(encoding="utf-8"):
        d = json.loads(line)
        if d["status"] != "ok":
            continue
        for c in d["clauses"]:
            for h in c["항"]:
                body = h["본문"].strip()
                if len(body) < 15:          # 너무 짧으면 대조할 내용이 없다
                    continue
                out.append({
                    "문서": d["이름"],
                    "조": c["표시"],
                    "조제목": c["제목"],
                    "항": h["번호"],
                    "본문": body,
                })
    return out


class Matcher:
    def __init__(self):
        self.types = load_types()
        self._index = encode([t["유형"] for t in self.types], is_query=False)

    def match(self, clause_text: str, top_k: int = 3) -> list[dict]:
        """유사도 상위 top_k를 후보로 준다. **게이팅은 하지 않는다** — 임계값을 아직 안 쟀다."""
        q = encode([clause_text], is_query=True)[0]
        scores = self._index @ q
        order = np.argsort(-scores)[:top_k]
        return [{**self.types[i], "점수": float(scores[i])} for i in order]


def cmd_calibrate():
    """
    임계값을 정하기 위한 분포 측정.
    표준약관 조항은 심의를 거친 것이라 대부분 불공정 유형에 해당하지 않는다.
    즉 여기 점수 분포가 곧 '해당 없음'의 분포다.
    """
    m = Matcher()
    clauses = load_clauses()
    print(f"대조 대상 조항(항 단위) {len(clauses)}개 / 유형 {len(m.types)}개\n")

    tops = []
    texts = [c["본문"] for c in clauses]
    q = encode(texts, is_query=True)
    scores = q @ m._index.T                      # (조항수, 유형수)
    best = scores.max(axis=1)
    tops = sorted(zip(best, clauses, scores.argmax(axis=1)), key=lambda x: -x[0])

    arr = np.array(best)
    print("=== 최고 유사도 분포 (표준약관 = 대부분 '해당 없음') ===")
    for p in [50, 75, 90, 95, 99, 100]:
        print(f"  {p:3}분위: {np.percentile(arr, p):.4f}")
    print(f"  평균 {arr.mean():.4f} / 최소 {arr.min():.4f}\n")

    print("=== 점수 상위 10개 — 사람이 봐야 할 것들 ===")
    for s, c, ti in tops[:10]:
        t = m.types[ti]
        print(f"  {s:.4f}  [{c['문서'][:16]}] {c['조']} {c['항'] or ''}")
        print(f"          조항: {c['본문'][:76]}")
        print(f"          유형: {t['인용']} — {t['유형'][:58]}")

    print("\n" + "=" * 70)
    print("이 분포만으로는 임계값을 정할 수 없다. 양성 샘플이 없기 때문이다.")
    print("표준약관은 심의를 거친 것이라 대부분 '해당 없음'이고,")
    print("여기 최고점이 곧 '무관한 조항도 이만큼은 나온다'는 바닥선이다.")


def cmd_demo():
    m = Matcher()
    samples = [
        "회사는 회원에게 발생한 어떠한 손해에 대하여도 일체 책임을 지지 않습니다.",
        "이 계약에 관한 소송의 관할법원은 회사의 본점 소재지 법원으로 한다.",
        "회원이 30일간 로그인하지 않으면 서비스 이용에 동의한 것으로 봅니다.",
        "본 서비스는 매일 오전 9시부터 오후 6시까지 운영합니다.",
    ]
    for s in samples:
        print(f"\n조항: {s}")
        for r in m.match(s, top_k=2):
            print(f"   {r['점수']:.4f}  {r['인용']} ({r['효력']})")
            print(f"           {r['유형'][:66]}")


if __name__ == "__main__":
    if "--calibrate" in sys.argv:
        cmd_calibrate()
    elif "--demo" in sys.argv:
        cmd_demo()
    else:
        print(__doc__)
