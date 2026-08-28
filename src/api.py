# -*- coding: utf-8 -*-
"""
계약서 돋보기 API — 약관 텍스트를 받아 조항마다 관련 조문을 나란히 놓아 돌려준다.

**이 API는 불공정 여부를 판정하지 않는다.** 관련 조문과 확신도 등급을 대고
원문을 나란히 놓는 데서 멈춘다. 응답의 `고지` 필드에 그 내용을 함께 실어
보내므로, 화면을 만드는 쪽이 이를 지우지 말 것.

    POST /analyze   {"text": "제1조 (목적) ..."}   조항별 관련 조문
    GET  /health    모델 적재 상태
    GET  /          사용법

임베딩 모델은 적재가 무거우므로 **서버 시작 시 한 번만** 올린다. 요청마다 올리면
첫 응답이 수십 초 걸린다.

실행:  uvicorn src.api:app --reload --port 8000
문서:  http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

MAX_CHARS = 200_000        # A4 약 60장. 이보다 크면 거절한다.

고지 = ("이 결과는 관련 가능성이 있는 조문을 제시할 뿐 불공정 여부를 판정하지 않습니다. "
        "순서는 관련 가능성 추정이며 1순위가 정답이라는 뜻이 아닙니다"
        "(실측 정확도: 1순위 41.7%, 3개 안에 포함 75.0%). "
        "법률 자문이 아니며, 실제 판단은 변호사 등 전문가의 검토가 필요합니다.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from match_articles import ArticleMatcher   # 시작할 때 모델을 올려둔다
    import pipeline
    pipeline._matcher = ArticleMatcher()
    app.state.ready = True
    yield


app = FastAPI(
    title="계약서 돋보기 (Contract Lens)",
    description="약관 조항에 약관규제법 조문을 나란히 놓습니다. 판정하지 않습니다.",
    version="0.1.0",
    lifespan=lifespan,
)


class AnalyzeIn(BaseModel):
    text: str = Field(..., description="약관 전문. 조항이 줄바꿈으로 나뉘어 있어야 한다.")
    llm: bool = Field(False, description="구조 추출까지 할지. 켜면 느리고 비용이 든다.")


class Candidate(BaseModel):
    순위: int
    조: str
    인용: str
    제목: str
    넓은점수: float


class ClauseOut(BaseModel):
    조: str | None
    제목: str
    본문: str
    후보: list[Candidate]
    건너뜀: str | None = None
    구조: dict | None = None


class AnalyzeOut(BaseModel):
    조항수: int
    뚜렷함: int
    관련없음: int
    조항: list[ClauseOut]
    고지: str


@app.get("/")
def root():
    return {"이름": "계약서 돋보기 (Contract Lens)",
            "설명": "약관 조항에 약관규제법 조문을 나란히 놓습니다. 판정하지 않습니다.",
            "사용법": "POST /analyze 에 {\"text\": \"약관 전문\"} 을 보내세요.",
            "문서": "/docs", "고지": 고지}


@app.get("/health")
def health():
    return {"ok": getattr(app.state, "ready", False)}


@app.post("/analyze", response_model=AnalyzeOut)
def analyze(body: AnalyzeIn):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "text 가 비어 있습니다.")
    if len(text) > MAX_CHARS:
        raise HTTPException(413, f"{MAX_CHARS:,}자를 넘습니다 (현재 {len(text):,}자).")

    from pipeline import run
    paras = [x.strip() for x in text.split("\n") if x.strip()]
    r = run(paras, "업로드", llm=body.llm)

    return AnalyzeOut(
        조항수=r["조항"], 뚜렷함=r["뚜렷함"], 관련없음=r["관련없음"],
        조항=[ClauseOut(조=x["조"], 제목=x["제목"], 본문=x["본문"],
                       후보=[Candidate(**{k: c[k] for k in
                                         ("순위", "조", "인용", "제목", "넓은점수")})
                             for c in x["후보"]],
                       건너뜀=x.get("건너뜀"), 구조=x.get("구조"))
             for x in r["정렬"]],
        고지=고지,
    )
