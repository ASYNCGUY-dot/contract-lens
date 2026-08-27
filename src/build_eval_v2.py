# -*- coding: utf-8 -*-
"""
평가 세트 v2 — 태스크를 바꾼다.

v1은 "이 조항이 불공정한가"를 물었고 실패했다. 양성 표본이 0개였다(→ NOTES.md 6번).
근본 문제는 **이 서비스가 애초에 불공정 판정을 하지 않는다**는 것이다.
하는 일은 관련 조문을 나란히 놓는 것이므로, 재야 할 것도 그것이어야 한다.

    v1  "이 조항이 제7조 1호 유형에 해당하는가"   판정. 양성 표본을 못 구했다
    v2  "이 조항이 어느 조문과 관련되는가"        주제 분류. 표준약관으로도 라벨링된다

바뀌는 것 셋:

  1. **조 단위**로만 본다. 호까지 가면 라벨링이 못 견딘다.
  2. **제6조를 뺀다.** 일반원칙이라 거의 모든 조항에 걸려 라벨이 무의미해진다.
     남는 것은 제7~14조 8개 + "관련없음" = 9지선다.
  3. **조 제목을 매칭 입력에 넣는다.** 실제 계약서에도 제목이 있고,
     라벨러와 기계가 같은 정보를 봐야 공정한 비교다.

표본은 조 제목으로 층화한다. 실측상 표준약관에 면책 61 / 권익보호 28 / 채무이행 24 /
소송관할 19 / 해지 14개 조가 있어 양성이 확보된다.

실행:  python src/build_eval_v2.py
출력:  data/eval/eval_v2.csv, data/eval/_items_v2.json
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

PARSED = ROOT / "data" / "terms" / "parsed.jsonl"
LAW_TYPES = ROOT / "data" / "laws" / "약관규제법_유형.json"
OUT_CSV = ROOT / "data" / "eval" / "eval_v2.csv"
OUT_JSON = ROOT / "data" / "eval" / "_items_v2.json"

SEED = 20260827
N_PER_TOPIC = 10          # 주제별 목표 개수
N_NONE = 30               # 관련없음 표본

# 조 제목에 이 말이 들어가면 그 조문 주제일 가능성이 높다. **힌트일 뿐 정답이 아니다.**
TITLE_HINT = {
    7:  ["면책", "책임", "손해배상", "배상책임"],
    8:  ["위약", "지연", "손해배상액", "배상액"],
    9:  ["해지", "해제"],
    10: ["변경", "중단", "중지", "서비스의 제공"],
    11: ["의무", "권리", "양도"],
    12: ["통지", "동의", "공지", "의사표시"],
    13: ["대리"],
    14: ["관할", "분쟁", "재판", "준거법"],
}
# 명백히 무관한 제목
NONE_HINT = ["목적", "정의", "용어", "재검토기한", "시행", "적용범위", "이용시간", "유효기간"]


def article_labels() -> list[dict]:
    """조 단위 라벨 목록. 제6조는 뺀다 — 일반원칙이라 모든 것에 걸린다."""
    types = json.loads(LAW_TYPES.read_text(encoding="utf-8"))["유형"]
    out, seen = [], set()
    for t in types:
        a = t["조"]
        if a == 6 or a in seen:
            continue
        seen.add(a)
        out.append({"id": str(a), "ref": f"제{a}조", "title": t["조제목"]})
    return sorted(out, key=lambda x: int(x["id"]))


def load_articles() -> list[dict]:
    """조 단위로 읽는다. 제목과 본문을 함께 쓴다."""
    out = []
    for line in PARSED.open(encoding="utf-8"):
        d = json.loads(line)
        if d["status"] != "ok":
            continue
        for c in d["clauses"]:
            body = c["본문"].strip()
            if not (30 <= len(body) <= 600) or not c["제목"]:
                continue
            out.append({"문서": d["이름"], "조": c["표시"], "제목": c["제목"], "본문": body})
    return out


def main():
    random.seed(SEED)
    from match_clauses import encode

    labels = article_labels()
    arts = load_articles()
    print(f"조 단위 후보 {len(arts)}개 / 라벨 {len(labels)}개 + 관련없음")

    # 조 제목으로 층화
    picked, used = [], set()
    for a, words in TITLE_HINT.items():
        pool = [x for i, x in enumerate(arts)
                if i not in used and any(w in x["제목"] for w in words)]
        random.shuffle(pool)
        take = pool[:N_PER_TOPIC]
        for x in take:
            used.add(arts.index(x))
            picked.append({**x, "층": f"제{a}조계열"})
        print(f"  제{a:2}조 계열 후보 {len(pool):3} → {len(take)}개")

    pool_none = [x for i, x in enumerate(arts)
                 if i not in used and any(w in x["제목"] for w in NONE_HINT)]
    random.shuffle(pool_none)
    for x in pool_none[:N_NONE]:
        picked.append({**x, "층": "무관계열"})
    print(f"  무관 계열 후보 {len(pool_none):3} → {min(len(pool_none), N_NONE)}개")

    random.shuffle(picked)

    # 매칭: 조 단위 대표 문장은 '조문제목 + 유형들'로 만든다
    types = json.loads(LAW_TYPES.read_text(encoding="utf-8"))["유형"]
    art_text = {}
    for t in types:
        if t["조"] == 6:
            continue
        art_text.setdefault(t["조"], []).append(t["유형"])
    keys = sorted(art_text)
    idx = encode([f"{next(l['title'] for l in labels if l['id'] == str(k))}. "
                  + " ".join(art_text[k]) for k in keys])

    queries = encode([f"{x['제목']}. {x['본문']}" for x in picked])
    scores = queries @ idx.T

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    items = []
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "층", "출처", "조제목", "본문",
                    "후보1", "후보1_점수", "후보2", "후보3", "정답", "메모"])
        for i, (x, sc) in enumerate(zip(picked, scores), 1):
            order = np.argsort(-sc)[:3]
            cands = [str(keys[j]) for j in order]
            w.writerow([i, x["층"], f"{x['문서'][:20]} {x['조']}", x["제목"], x["본문"],
                        cands[0], f"{sc[order[0]]:.4f}", cands[1], cands[2], "", ""])
            items.append({"n": i, "g": x["층"], "src": f"{x['문서'][:20]} {x['조']}",
                          "title": x["제목"], "t": x["본문"], "c": cands})

    OUT_JSON.write_text(json.dumps({"items": items, "labels": labels},
                                   ensure_ascii=False), encoding="utf-8")
    print(f"\n평가 세트 v2 {len(picked)}개 → {OUT_CSV.relative_to(ROOT)}")
    print("\n라벨: 제7~14조 중 하나, 또는 관련없음")
    for l in labels:
        print(f"  {l['id']:>2}  {l['ref']} {l['title']}")


if __name__ == "__main__":
    main()
