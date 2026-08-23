# -*- coding: utf-8 -*-
"""
약관의 규제에 관한 법률에서 '불공정 조항 유형 목록'을 뽑아 JSON으로 저장한다.

이 목록이 매칭 대상이다. 계약서 조항을 여기에 맞춰보고, 맞으면 조문 원문을 그대로 보여준다.
**우리가 유형을 만들지 않는다.** 법률이 열거한 것을 옮길 뿐이다.

실행:  python src/build_law_index.py
출력:  data/laws/약관규제법_유형.json

원본 구조가 네 가지로 섞여 있어 그대로 파싱하면 깨진다:
  1. 조문여부='전문'  — 장 제목이 조문번호를 달고 들어온다 (제6조 자리에 "제2장 불공정약관조항")
  2. 항=list        — 제6조처럼 ①②로 나뉘고, 항마다 호가 있을 수도 없을 수도
  3. 항=dict        — 제7·9조처럼 항 개념 없이 바로 호만 있다 (항번호가 None)
  4. 항=None        — 제8조처럼 조문내용 한 줄이 전부다
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OC = os.getenv("LAW_OC")
BASE = "https://www.law.go.kr/DRF"
UA = {"User-Agent": "Mozilla/5.0"}

# 약관의 규제에 관한 법률. 제2장(제6~14조)이 불공정 조항 유형을 열거한다.
LAW_NAME = "약관의 규제에 관한 법률"
ART_FROM, ART_TO = 6, 14

OUT = ROOT / "data" / "laws" / "약관규제법_유형.json"


def clean(s) -> str:
    """태그와 엔티티를 걷어내고 공백을 정리한다."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(str(s or "")))).strip()


def as_list(x) -> list:
    """API가 항목 1개일 때 list가 아니라 dict를 준다. 항상 list로 맞춘다."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def find_mst() -> tuple[str, str]:
    """법령명으로 검색해 법령일련번호(MST)와 시행일자를 가져온다."""
    r = requests.get(f"{BASE}/lawSearch.do", timeout=30, headers=UA,
                     params={"OC": OC, "target": "law", "type": "JSON",
                             "query": LAW_NAME, "display": 5})
    r.raise_for_status()
    for row in as_list(r.json()["LawSearch"].get("law")):
        # "약관의 규제에 관한 법률 시행령"이 아니라 법률 본체여야 한다
        if clean(row.get("법령명한글")) == LAW_NAME:
            return row["법령일련번호"], str(row.get("시행일자", ""))
    raise SystemExit(f"[!] '{LAW_NAME}'을 찾지 못했습니다.")


def fetch_articles(mst: str) -> list[dict]:
    r = requests.get(f"{BASE}/lawService.do", timeout=30, headers=UA,
                     params={"OC": OC, "target": "law", "MST": mst, "type": "JSON"})
    r.raise_for_status()
    return as_list(r.json()["법령"]["조문"]["조문단위"])


def effect_of(text: str) -> str:
    """
    조문이 정하는 효력. 이걸 뭉뚱그리면 부정확해진다 —
    제6조 2항은 '무효'가 아니라 '공정성을 잃은 것으로 추정'이다.
    """
    if "무효로 한다" in text or "무효이다" in text:
        return "무효"
    if "추정" in text:
        return "추정"
    return "기타"


def extract_types(articles: list[dict]) -> list[dict]:
    types: list[dict] = []
    for art in articles:
        # 장 제목이 조문번호를 달고 들어오는 것을 여기서 버린다
        if art.get("조문여부") != "조문":
            continue
        num = str(art.get("조문번호", ""))
        if not num.isdigit() or not (ART_FROM <= int(num) <= ART_TO):
            continue

        art_no = int(num)
        art_title = clean(art.get("조문제목"))
        art_body = clean(art.get("조문내용"))
        hangs = as_list(art.get("항"))

        if not hangs:
            # 형태 4 — 조문내용 한 줄이 전부
            types.append(_row(art_no, art_title, art_body, None, None, art_body))
            continue

        for hang in hangs:
            hang_no = clean(hang.get("항번호")) or None
            hang_body = clean(hang.get("항내용"))
            hos = as_list(hang.get("호"))

            if not hos:
                # 항은 있는데 호가 없다 (제6조 1항)
                if hang_body:
                    # "① 신의성실의 원칙을..." → 앞의 항번호를 뗀다 (호와 동일하게 맞춘다)
                    hang_text = re.sub(r"^[①-⑳]\s*", "", hang_body)
                    types.append(_row(art_no, art_title, art_body, hang_no, None, hang_text))
                continue

            for ho in hos:
                ho_no = clean(ho.get("호번호")).rstrip(".") or None
                ho_body = clean(ho.get("호내용"))
                # "1. 고객에게 부당하게 불리한 조항" → 앞의 번호를 뗀다
                ho_text = re.sub(r"^\d+\.\s*", "", ho_body)
                # 효력은 호가 아니라 그 호를 거느린 항/조가 정한다
                scope = hang_body or art_body
                types.append(_row(art_no, art_title, art_body, hang_no, ho_no, ho_text, scope))
    return types


def _row(art_no, art_title, art_body, hang_no, ho_no, text, scope=None) -> dict:
    ref = f"{LAW_NAME} 제{art_no}조"
    if hang_no:
        ref += f" {hang_no}"
    if ho_no:
        ref += f" 제{ho_no}호"
    return {
        "id": "-".join(x for x in [str(art_no), hang_no, ho_no] if x),
        "조": art_no,
        "조제목": art_title,
        "항": hang_no,
        "호": ho_no,
        "인용": ref,
        "유형": text,
        "효력": effect_of(scope or text),
        "조문내용": art_body,
    }


def main():
    if not OC:
        raise SystemExit("[!] .env의 LAW_OC가 비어 있습니다.")

    mst, eff_date = find_mst()
    articles = fetch_articles(mst)
    types = extract_types(articles)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "법령명": LAW_NAME,
        "법령일련번호": mst,
        "시행일자": eff_date,
        "대상조문": f"제{ART_FROM}조~제{ART_TO}조",
        "수집시각": datetime.now(timezone.utc).astimezone().isoformat(),
        "유형수": len(types),
        "유형": types,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"법령 {LAW_NAME} (MST={mst}, 시행 {eff_date})")
    print(f"조문단위 {len(articles)}개 → 제{ART_FROM}~{ART_TO}조에서 유형 {len(types)}개 추출")
    print(f"저장: {OUT.relative_to(ROOT)}\n")

    by_art: dict[int, int] = {}
    for t in types:
        by_art[t["조"]] = by_art.get(t["조"], 0) + 1
    for art_no in sorted(by_art):
        title = next(t["조제목"] for t in types if t["조"] == art_no)
        print(f"  제{art_no}조 ({title}) — {by_art[art_no]}개")


if __name__ == "__main__":
    main()
