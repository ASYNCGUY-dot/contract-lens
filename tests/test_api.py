# -*- coding: utf-8 -*-
"""
API가 실제로 도는지 재는 테스트. 서버를 띄우지 않고 TestClient 로 부른다.

**성능이 아니라 계약을 잰다.** 매칭 정확도는 평가 세트로 따로 재고(`score_eval_v2.py`),
여기서는 "요청을 넣으면 약속한 모양의 응답이 나오는가"만 본다.

실행:  python -m pytest tests/ -v
       python tests/test_api.py      (pytest 없이도 돈다)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient          # noqa: E402
from src.api import app, MAX_CHARS                 # noqa: E402

SAMPLE = """제1조 (목적) 이 약관은 회사가 제공하는 서비스의 이용조건을 정함을 목적으로 한다.
제2조 (면책) 회사는 회원에게 발생한 어떠한 손해에 대하여도 일체 책임을 지지 아니한다.
제3조 (관할법원) 이 약관에 관한 소송의 관할법원은 회사의 본점 소재지 법원으로 한다."""


def test_health():
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200 and r.json()["ok"] is True


def test_root_carries_disclaimer():
    """고지를 지우고 배포하는 사고를 막는다."""
    with TestClient(app) as c:
        assert "판정하지 않습니다" in c.get("/").json()["고지"]


def test_analyze_shape():
    with TestClient(app) as c:
        r = c.post("/analyze", json={"text": SAMPLE})
        assert r.status_code == 200
        d = r.json()
        assert d["조항수"] == 3
        assert "판정하지" in d["고지"]
        for x in d["조항"]:
            for i, c2 in enumerate(x["후보"], 1):
                assert c2["순위"] == i          # 순위가 1부터 순서대로여야 한다
                assert c2["인용"].startswith("약관의 규제에 관한 법률 제")


def test_meta_clause_is_skipped_with_reason():
    """목적 조항은 대조하지 않고, 그 사실을 밝혀야 한다(16번)."""
    with TestClient(app) as c:
        d = c.post("/analyze", json={"text": SAMPLE}).json()
        purpose = next(x for x in d["조항"] if "목적" in x["제목"])
        assert purpose["후보"] == []
        assert purpose["건너뜀"]


def test_no_confidence_label_leaks():
    """확신도 표시를 없앤 결정(16번)이 되돌아가지 않게 막는다."""
    with TestClient(app) as c:
        d = c.post("/analyze", json={"text": SAMPLE}).json()
        for x in d["조항"]:
            for c2 in x["후보"]:
                assert "등급" not in c2
        assert "1순위가 정답이라는 뜻이 아닙니다" in d["고지"]


def test_articles_have_body_and_items():
    """
    조문 원문은 조 본문과 각 호가 **다른 파일에 있어** 합쳐야 완전해진다.
    한쪽만 나오면 사용자가 판단할 수 없으므로 둘 다 있는지 잰다.
    """
    with TestClient(app) as c:
        d = c.get("/articles").json()
        assert set(d) == {"7", "8", "9", "10", "11", "12", "13", "14"}
        a = d["7"]
        assert a["제목"] == "면책조항의 금지"
        assert "무효로 한다" in a["본문"]          # 조 본문
        assert len(a["호"]) == 4                    # 각 호
        assert a["호"][0]["번호"] == 1
        assert all(h["효력"] for h in a["호"])      # 무효/추정 구분이 살아 있어야 한다


def test_rejects_empty_and_oversize():
    with TestClient(app) as c:
        assert c.post("/analyze", json={"text": "   "}).status_code == 400
        assert c.post("/analyze", json={"text": "가" * (MAX_CHARS + 1)}).status_code == 413


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"  통과  {name}")
    print(f"\n{n}개 통과")
