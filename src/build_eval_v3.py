# -*- coding: utf-8 -*-
"""
평가 세트 v3 — **실제 사설 약관** 조항으로 만든다. 판례에 인용된 것을 쓴다.

## 왜 필요한가

v2(85개)는 전부 표준약관(행정규칙)이다. 그래서 실제 사설 계약서에서 어떻게
동작하는지 모른다. **표본 개수가 아니라 종류가 편중된 것이 문제다.**
표준약관을 1000개 더 넣어도 이 약점은 안 보인다.

판례에 인용된 조항은 실제로 분쟁이 된 사설 약관이라 성격이 정반대다.
수집 비용도 없다 — 판례 463건은 이미 갖고 있다.

## v1이 같은 시도를 했다가 실패했다

그때 태스크가 "이 조항이 불공정한가"였는데, 인용 문구가 조항 전체가 아니라
쟁점 파편이라 맥락 없이는 판단이 안 됐다(보류 21개가 전부 여기서 나왔다).
**지금 태스크는 "어느 조문과 관련되는가"다.** 파편이어도 주제는 알 수 있다.

## 걸러내는 것 — 법 조문 인용이 가장 큰 오염원

판례는 약관 조항만 인용하는 게 아니라 **약관규제법 조문도 그대로 인용한다.**
그걸 남기면 "법 조문으로 법 조문을 맞히는" 자기참조 평가가 되어 점수가 부풀려진다.
문자열 규칙만으로는 다 못 걸러서(형태가 제각각) **법 유형 28개와의 유사도**로도 거른다.

실행:  python src/build_eval_v3.py
출력:  data/eval/eval_v3.csv, data/eval/_items_v3.json
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

CASES = ROOT / "data" / "cases" / "bodies.jsonl"
LAW_TYPES = ROOT / "data" / "laws" / "약관규제법_유형.json"
OUT_CSV = ROOT / "data" / "eval" / "eval_v3.csv"
OUT_JSON = ROOT / "data" / "eval" / "_items_v3.json"

QUOTE = re.compile(r"약관[^.]{0,40}?제\s*\d+\s*조[^.]{0,30}?"
                   r"['\u2018\u201c\"]([^'\u2019\u201d\"]{25,220})['\u2019\u201d\"]")
LAW_WORD = re.compile(r"(약관의 규제에 관한 법률|약관규제법|신의성실의 원칙|이 법은)")
# 실제 약관은 자기 조항을 무효라고 쓰지 않는다. 이렇게 끝나면 법 조문 인용이다.
# 유형 목록에는 각 호만 있고 조 본문("...조항은 무효로 한다")이 없어서 유사도로는 안 걸린다.
LAW_TAIL = re.compile(r"(무효로 한다|무효이다|무효로 본다|추정한다)\s*[.]?$")
END = re.compile(r"(한다|아니한다|아니하다|없다|있다|본다|진다|된다)\s*[.]?$")

LAW_SIM = 0.85     # 제6~14조 유형과 이만큼 비슷하면 법 조문 인용으로 본다
# 유형 목록은 제6~14조뿐이라 제3·4·5조 조문이 그대로 통과했다(실측 6건).
# 그래서 **법 전문 105문장**과도 대조한다. 0.75~0.80 구간이 비어 있어 경계가 깨끗하고,
# 이 선에서 걸리는 6건은 전부 법 조문이며 실제 약관은 하나도 걸리지 않는다.
FULL_LAW_SIM = 0.75
FULL_LAW = ROOT / "data" / "laws" / "약관규제법_전문.json"
DUP_SIM = 0.90     # 이만큼 비슷하면 같은 조항으로 본다


def collect() -> list[dict]:
    out, seen = [], set()
    for line in CASES.open(encoding="utf-8"):
        d = json.loads(line)
        body = (d.get("판례내용") or "").replace("<br/>", " ")
        for m in QUOTE.finditer(body):
            q = re.sub(r"\s+", " ", m.group(1)).strip()
            if LAW_WORD.search(q) or LAW_TAIL.search(q) or q.endswith("조항")                     or not END.search(q):
                continue
            if q in seen:
                continue
            seen.add(q)
            out.append({"본문": q, "사건번호": d["사건번호"],
                        "법원": d.get("법원명", ""), "선고": d.get("선고일자", "")})
    return out


def main():
    from match_clauses import encode

    items = collect()
    print(f"문자열 규칙 통과 {len(items)}개")

    types = [t["유형"] for t in json.loads(LAW_TYPES.read_text(encoding="utf-8"))["유형"]]
    L = encode(types)
    V = encode([x["본문"] for x in items])

    # 1) 법 조문 인용 제거 — 유형과 너무 비슷하면 약관이 아니라 법이다
    maxsim = (V @ L.T).max(axis=1)
    keep = [i for i in range(len(items)) if maxsim[i] < LAW_SIM]
    print(f"  법 조문 인용 제외 (유형 유사도 {LAW_SIM} 이상)  → {len(keep)}개"
          f"  [{len(items) - len(keep)}개 제외]")

    # 1-b) 법 전문과 대조 — 유형 목록에 없는 제1~5조·부칙 조문을 여기서 잡는다
    if FULL_LAW.exists():
        full = [x["내용"] for x in
                json.loads(FULL_LAW.read_text(encoding="utf-8"))["문장"]]
        F = encode(full)
        sim2 = (V[keep] @ F.T).max(axis=1)
        keep2 = [k for k, sm in zip(keep, sim2) if sm < FULL_LAW_SIM]
        print(f"  법 전문 대조 제외 (유사도 {FULL_LAW_SIM} 이상)      → {len(keep2)}개"
              f"  [{len(keep) - len(keep2)}개 제외]")
        keep = keep2
    else:
        print("  [!] 약관규제법_전문.json 이 없습니다. fetch_full_law.py 를 먼저 도세요.")

    # 2) 같은 조항 묶기 — 판례가 달라도 같은 약관을 다툰 경우가 많다
    V2 = V[keep]
    S = V2 @ V2.T
    np.fill_diagonal(S, 0)
    used, reps = set(), []
    for i in range(len(keep)):
        if i in used:
            continue
        g = [i] + [j for j in range(i + 1, len(keep))
                   if j not in used and S[i, j] >= DUP_SIM]
        used.update(g)
        reps.append((keep[i], len(g)))
    print(f"  같은 조항 묶기 (유사도 {DUP_SIM})              → {len(reps)}개 그룹")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows, out_items = [], []
    for n, (i, cnt) in enumerate(sorted(reps, key=lambda x: -x[1]), 1):
        x = items[i]
        rows.append([n, x["사건번호"], x["법원"], x["선고"], cnt, x["본문"], "", ""])
        out_items.append({"n": str(n), "src": f"{x['법원']} {x['사건번호']}",
                          "title": f"판례 인용 조항 (같은 조항 {cnt}건)",
                          "t": x["본문"], "c": []})

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "사건번호", "법원", "선고일자", "중복건수", "본문", "정답", "메모"])
        w.writerows(rows)

    labels = [{"id": str(a), "ref": f"제{a}조", "title": t}
              for a, t in sorted({(t["조"], t["조제목"]) for t in
                                  json.loads(LAW_TYPES.read_text(encoding="utf-8"))["유형"]
                                  if t["조"] != 6})]
    OUT_JSON.write_text(json.dumps({"items": out_items, "labels": labels},
                                   ensure_ascii=False), encoding="utf-8")
    print(f"\n평가 세트 v3 {len(rows)}개 → {OUT_CSV.relative_to(ROOT)}")
    print("\n=== 앞 6개 ===")
    for r in rows[:6]:
        print(f"  [{r[1]}] (중복 {r[4]}건) {r[5][:74]}")


if __name__ == "__main__":
    main()
