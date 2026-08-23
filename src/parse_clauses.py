# -*- coding: utf-8 -*-
"""
계약서·약관 텍스트를 조 → 항 → 호로 분리한다.

**분리에 실패하면 지어내지 않고 `unparseable`로 표시한다.** 이 프로젝트의 원칙이
"모르면 모른다고 한다"이므로, 조 구조가 없는 문서를 억지로 쪼개면 그 뒤 매칭이 전부 오염된다.

실측으로 확인한 형식 (약관 39건 / 조문내용 785개):

    제N조(제목) 본문          605개  가장 흔한 형태
    제N장 / 제N절             104개  구조 제목이라 조가 아니다. 걸러낸다
    제N조 (제목) 본문          65개  **제목 앞에 공백이 있다.** 놓치면 이만큼 통째로 샌다
    제N조의M(제목)              5개
    조 구조 자체가 없음          6개  'Ⅰ. 목적' 같은 지침·가이드라인 → unparseable

항은 `①②③`으로, 호는 `1. 2. 3.`으로 한 문자열 안에 구분자 없이 이어붙어 온다.
    제17조(대금지급 등에 관한 사항) ①수급인이 ... 하여야 합니다.②수급인이 ...

호 분리는 오탐이 쉽다(날짜 "2024. 1. 1." 등). **1부터 순차적일 때만** 호로 본다.
"""

from __future__ import annotations

import re

# 조: 번호 뒤 공백 허용, "제N조의M" 허용, 제목 괄호는 있을 수도 없을 수도
ART_RE = re.compile(r"^제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*(?:\(([^)]*)\))?\s*(.*)$", re.S)
# 장·절 제목 (조가 아니다)
STRUCT_RE = re.compile(r"^제\s*\d+\s*[장절편관]\b")
HANG_MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
HANG_RE = re.compile(f"([{HANG_MARKS}])")
# 마침표를 lookbehind에서 빼야 한다. 실측상 가장 흔한 형태가
#   "다음 각 호와 같습니다.1. \"공공조달..."
# 처럼 문장 마침표 뒤에 바로 호 번호가 붙는다. 마침표를 막으면 174개 중 20개만 잡힌다.
# 날짜("2024. 1. 15.") 오탐은 아래 순차 검사(1,2,3...)가 걸러낸다.
HO_RE = re.compile(r"(?<![0-9])(\d{1,2})\.\s*")


def split_ho(text: str) -> tuple[str, list[dict]]:
    """
    본문에서 호를 떼어낸다. 1부터 순차적으로 이어질 때만 호로 인정한다.
    그렇지 않으면 날짜·조문번호를 호로 잘못 읽는다.
    """
    marks = list(HO_RE.finditer(text))
    if not marks:
        return text, []

    # 1, 2, 3... 으로 이어지는 가장 긴 앞부분만 취한다
    run, expect = [], 1
    for m in marks:
        if int(m.group(1)) == expect:
            run.append(m)
            expect += 1
    if len(run) < 2:                       # 호가 하나뿐이면 신뢰하지 않는다
        return text, []

    head = text[: run[0].start()].strip()
    hos = []
    for i, m in enumerate(run):
        end = run[i + 1].start() if i + 1 < len(run) else len(text)
        body = text[m.end(): end].strip()
        # 원문에 "3. 4. \"이용기관\"..." 처럼 내용 없이 번호만 남은 호가 있다(삭제된 호).
        # 빈 껍데기를 결과에 넣으면 대조할 것이 없으므로 버린다.
        if body:
            hos.append({"번호": m.group(1), "본문": body})
    return head, hos


def split_hang(body: str) -> list[dict]:
    """본문을 항(①②③)으로 나눈다. 항 표시가 없으면 통째로 항 하나로 본다."""
    parts = HANG_RE.split(body)
    if len(parts) == 1:                    # 항 표시 없음
        head, hos = split_ho(body.strip())
        return [{"번호": None, "본문": head, "호": hos}] if (head or hos) else []

    out = []
    # split 결과는 [머리말, 마크, 내용, 마크, 내용, ...]
    lead = parts[0].strip()
    if lead:
        head, hos = split_ho(lead)
        out.append({"번호": None, "본문": head, "호": hos})
    for mark, chunk in zip(parts[1::2], parts[2::2]):
        head, hos = split_ho(chunk.strip())
        out.append({"번호": mark, "본문": head, "호": hos})
    return out


def parse_paragraph(text: str) -> dict | None:
    """조문내용 한 덩어리를 조 하나로 파싱한다. 조가 아니면 None."""
    text = text.strip()
    if not text or STRUCT_RE.match(text):
        return None
    m = ART_RE.match(text)
    if not m:
        return None
    art, sub, title, body = m.group(1), m.group(2), m.group(3), (m.group(4) or "").strip()
    return {
        "조": int(art),
        "조의": int(sub) if sub else None,
        "표시": f"제{art}조" + (f"의{sub}" if sub else ""),
        "제목": (title or "").strip() or None,
        "본문": body,
        "항": split_hang(body),
    }


def parse_document(paragraphs: list[str]) -> dict:
    """
    문서 전체를 파싱한다. 조를 하나도 못 찾으면 unparseable.
    억지로 쪼개지 않는다 — 잘못 쪼갠 조항으로 매칭하면 결과 전체가 오염된다.
    """
    clauses, skipped = [], []
    for p in paragraphs:
        parsed = parse_paragraph(p)
        if parsed is None:
            skipped.append(p)
        else:
            clauses.append(parsed)

    if not clauses:
        return {
            "status": "unparseable",
            "reason": "조(제N조) 구조를 찾지 못했습니다. 조항 단위 대조를 할 수 없습니다.",
            "clauses": [],
            "skipped": len(skipped),
        }
    return {
        "status": "ok",
        "clauses": clauses,
        "skipped": len(skipped),          # 장·절 제목 등
    }


if __name__ == "__main__":
    import json
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    src = ROOT / "data" / "terms" / "terms.jsonl"
    if not src.exists():
        raise SystemExit("[!] data/terms/terms.jsonl 이 없습니다. collect_terms.py 를 먼저 돌리세요.")

    out_path = ROOT / "data" / "terms" / "parsed.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fout = out_path.open("w", encoding="utf-8")

    ok = bad = 0
    n_cl = n_hang = n_ho = 0
    unparseable = []
    for line in src.open(encoding="utf-8"):
        d = json.loads(line)
        res = parse_document(d["조문내용"])
        fout.write(json.dumps({"id": d["id"], "이름": d["이름"], **res},
                              ensure_ascii=False) + "\n")
        if res["status"] != "ok":
            bad += 1
            unparseable.append(d["이름"])
            continue
        ok += 1
        n_cl += len(res["clauses"])
        for c in res["clauses"]:
            n_hang += len(c["항"])
            n_ho += sum(len(h["호"]) for h in c["항"])

    print(f"문서 {ok + bad}건 — 파싱 성공 {ok} / unparseable {bad}")
    print(f"조 {n_cl}개 / 항 {n_hang}개 / 호 {n_ho}개")
    print(f"저장: {out_path.relative_to(ROOT)}")
    if unparseable:
        print("\nunparseable 문서:")
        for nm in unparseable:
            print(f"  · {nm}")
