# -*- coding: utf-8 -*-
"""
API가 실제로 도는지 재는 테스트. 서버를 띄우지 않고 TestClient 로 부른다.

**성능이 아니라 계약을 잰다.** 매칭 정확도는 평가 세트로 따로 재고(`score_eval_v2.py`),
여기서는 "요청을 넣으면 약속한 모양의 응답이 나오는가"만 본다.

실행:  python -m pytest tests/ -v
       python tests/test_api.py      (pytest 없이도 돈다)
"""

from __future__ import annotations

import os
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


def test_api_root_carries_disclaimer():
    """
    고지를 지우고 배포하는 사고를 막는다.

    `/` 는 화면(React 빌드)이 가져갔으므로 API 안내는 `/api` 다.
    터널·배포에서 화면과 API 가 같은 주소를 쓰기 위한 구조다.
    """
    with TestClient(app) as c:
        assert "판정하지 않습니다" in c.get("/api").json()["고지"]


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


def test_title_and_body_on_separate_lines():
    """
    실제 계약서는 조 제목과 본문이 **다른 줄**에 있다.

        제 1 조(목적)
        본 약관은 …

    줄 단위로 그냥 나누면 제목 줄은 본문이 0자가 되고 본문 줄은 버려져서
    조항이 하나도 안 잡힌다. 실제 약관 6,066자를 넣었을 때 조항 0개가
    나온 것이 이 때문이었다. 평가 세트(표준약관)는 한 줄에 다 들어 있어
    이 형식을 보지 못했다.
    """
    src = """서비스 이용약관
제 1장 총칙
제 1 조(목적)
본 약관은 회사가 제공하는 서비스의 이용조건을 정함을 목적으로 합니다.
제 2 조(면책조항)
회사는 회원에게 발생한 어떠한 손해에 대하여도 일체 책임을 지지 아니합니다."""
    with TestClient(app) as c:
        d = c.post("/analyze", json={"text": src}).json()
        assert d["조항수"] == 2, f"조항이 {d['조항수']}개만 잡혔다"
        by = {x["조"]: x for x in d["조항"]}
        assert "회사가 제공하는" in by["제1조"]["본문"]     # 본문이 붙었는가
        assert by["제1조"]["건너뜀"]                        # 목적 조항은 건너뛴다
        assert by["제2조"]["후보"], "면책 조항에 후보가 없다"


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


def test_plain_language_guide():
    """
    법 조문만 보여주면 일반인은 읽을 수 없다. 쉬운 안내와 용어 풀이가 함께 와야 한다.

    **안내는 주제만 말하고 유불리를 판단하지 않는다.** '무효' 설명도 마찬가지로,
    법이 그런 조항을 무효로 정한다는 뜻이지 지금 보는 계약서가 무효라는 뜻이
    아님을 밝혀야 한다. 이 문구가 빠지면 서비스가 판정하는 것처럼 읽힌다.
    """
    with TestClient(app) as c:
        d = c.get("/articles").json()
        a = d["12"]
        assert a["안내"] and len(a["안내"]) > 20
        assert "의사표시" in [t["말"] for t in a["용어"]]
        note = a["호"][0]["효력설명"]
        assert "무효라는 뜻이 아닙니다" in note
        assert "**" not in note              # 화면은 마크다운을 렌더링하지 않는다
        # 안내가 판정하지 않는지. 명사가 아니라 **단정형 서술**을 잡는다.
        # "위험"은 법 조문 자체의 표현이다(제7조 2호 "부담하여야 할 위험을
        # 고객에게 떠넘기는 조항"). 명사를 금지하면 조문을 옮길 수가 없다.
        for a2 in d.values():
            for bad in ("불공정합니다", "무효입니다", "위험합니다", "주의하세요",
                        "문제가 있습니다", "불리합니다"):
                assert bad not in a2["안내"], f"{bad} 가 안내에 있다"


def test_rejects_empty_and_oversize():
    with TestClient(app) as c:
        assert c.post("/analyze", json={"text": "   "}).status_code == 400
        assert c.post("/analyze", json={"text": "가" * (MAX_CHARS + 1)}).status_code == 413


def test_feedback_is_private():
    """
    후기 게시판의 전부는 **누가 무엇을 볼 수 있는가**다. 여기가 새면 기능 자체가
    의미를 잃는다. 지인이 자기 계약서 이야기를 적을 텐데 남이 읽으면 안 된다.

    비밀번호가 틀렸을 때 "틀렸다"고 알리지 않고 빈 목록을 주는 것도 확인한다.
    남의 이름으로 비밀번호를 맞혀 보는 일을 조금이라도 어렵게 하기 위해서다.
    """
    import feedback as fb
    old_db, old_key = fb.DB, os.environ.get("ADMIN_KEY")
    fb.DB = ROOT / "data" / "_test_fb.db"
    os.environ["ADMIN_KEY"] = "테스트-운영자-키"
    try:
        if fb.DB.exists():
            fb.DB.unlink()
        with TestClient(app) as c:
            c.post("/feedback", json={"이름": "민수", "비밀번호": "1234",
                                      "내용": "전세계약서를 넣어 봤습니다."})
            c.post("/feedback", json={"이름": "지영", "비밀번호": "9999",
                                      "내용": "결과가 엉뚱했어요."})

            mine = c.post("/feedback/mine",
                          json={"이름": "민수", "비밀번호": "1234"}).json()["목록"]
            assert len(mine) == 1 and "전세계약서" in mine[0]["내용"]

            # 비밀번호가 틀리면 빈 목록. 틀렸다고 알려 주지 않는다.
            assert c.post("/feedback/mine",
                          json={"이름": "민수", "비밀번호": "0000"}).json()["목록"] == []
            # 남의 이름 + 내 비밀번호로도 안 된다
            assert c.post("/feedback/mine",
                          json={"이름": "민수", "비밀번호": "9999"}).json()["목록"] == []

            # 운영자는 전부 본다
            all_ = c.post("/feedback/all", json={"키": "테스트-운영자-키"})
            assert all_.status_code == 200 and len(all_.json()["목록"]) == 2
            # 키가 틀리면 막는다 (한글 키에서 터지지 않아야 한다)
            assert c.post("/feedback/all", json={"키": "아무거나"}).status_code == 403
    finally:
        if fb.DB.exists():
            fb.DB.unlink()
        fb.DB = old_db
        if old_key is None:
            os.environ.pop("ADMIN_KEY", None)
        else:
            os.environ["ADMIN_KEY"] = old_key


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"  통과  {name}")
    print(f"\n{n}개 통과")
