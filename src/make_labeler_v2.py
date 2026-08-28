# -*- coding: utf-8 -*-
"""
평가 세트 v2용 라벨링 도구. 9지선다(제7~14조 + 관련없음)라 v1보다 훨씬 빠르다.

실행:  python src/make_labeler_v2.py        표준약관 세트(v2)
       python src/make_labeler_v2.py v3     판례 인용 조항 세트(v3)
출력:  data/eval/labeler_v2.html  또는  labeler_v3.html

**저장 키를 버전마다 다르게 둔다.** 같은 키를 쓰면 브라우저에 남은 v2 라벨이
v3 화면에 그대로 나타나 라벨이 섞인다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VER = "v3" if "v3" in sys.argv else "v2"
SRC = ROOT / "data" / "eval" / f"_items_{VER}.json"
OUT = ROOT / "data" / "eval" / f"labeler_{VER}.html"

HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>조문 관련성 라벨링</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--dim:#666;--line:#e0e0e0;--sel:#2563eb;--ok:#059669;--hold:#d97706}
@media (prefers-color-scheme:dark){:root{--bg:#16181c;--fg:#e8e8e8;--dim:#9aa0a6;--line:#333;--sel:#60a5fa;--ok:#34d399;--hold:#fbbf24}}
*{box-sizing:border-box}
body{margin:0;padding:20px;font:15px/1.6 -apple-system,'Segoe UI',sans-serif;background:var(--bg);color:var(--fg)}
.wrap{max-width:880px;margin:0 auto}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin-bottom:8px}
.bar>i{display:block;height:100%;background:var(--sel);transition:width .2s}
.meta{display:flex;justify-content:space-between;color:var(--dim);font-size:13px;margin-bottom:14px}
.title{font-size:17px;font-weight:600;margin-bottom:6px}
.clause{border:1px solid var(--line);border-left:3px solid var(--sel);padding:14px;border-radius:6px;
  line-height:1.7;margin-bottom:6px;max-height:260px;overflow:auto}
.src{color:var(--dim);font-size:12px;margin-bottom:14px}
h3{font-size:13px;color:var(--dim);margin:16px 0 8px;font-weight:600}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.grid button{text-align:left;border:1px solid var(--line);background:transparent;color:var(--fg);
  padding:11px 12px;border-radius:6px;cursor:pointer;font:inherit;font-size:14px}
.grid button:hover{border-color:var(--sel)}
.grid button.cand{border-color:var(--sel);border-width:2px}
.grid b{color:var(--sel);margin-right:8px}
.row{display:flex;gap:8px;margin-top:12px}
.row button{flex:1;padding:12px;border-radius:6px;border:1px solid var(--line);background:transparent;
  color:var(--fg);cursor:pointer;font:inherit;font-size:14px}
.row .none{border-color:var(--ok);color:var(--ok)}
.row .hold{border-color:var(--hold);color:var(--hold)}
.row .back{color:var(--dim)}
.done{text-align:center;padding:30px 0}
textarea{width:100%;height:110px;font:12px/1.5 ui-monospace,monospace;padding:10px;border-radius:6px;
  border:1px solid var(--line);background:var(--bg);color:var(--fg);margin-top:12px}
.hint{color:var(--dim);font-size:12.5px;margin-top:10px}
kbd{border:1px solid var(--line);border-radius:3px;padding:1px 5px;font-size:11px}
</style></head><body><div class="wrap" id="app"></div>
<script>
const DATA=__DATA__;
const KEY='clauseledger___VER___labels';
let ans=JSON.parse(localStorage.getItem(KEY)||'{}');
let i=Object.keys(ans).length;
const save=()=>localStorage.setItem(KEY,JSON.stringify(ans));
const pick=v=>{ans[DATA.items[i].n]=v;save();i++;render()};

function render(){
  const app=document.getElementById('app');
  if(i>=DATA.items.length){
    const line=DATA.items.map(x=>`${x.n}:${ans[x.n]||'보류'}`).join(',');
    app.innerHTML=`<div class="done"><h2>완료</h2>
      <p class="hint">아래 한 줄을 복사해서 대화창에 붙여넣으세요.</p>
      <textarea readonly onclick="this.select()">${line}</textarea>
      <div class="row"><button onclick="navigator.clipboard.writeText(document.querySelector('textarea').value)">복사</button>
      <button class="back" onclick="i=0;render()">처음부터</button>
      <button class="hold" onclick="if(confirm('전부 지웁니다'))(ans={},save(),i=0,render())">초기화</button></div></div>`;
    return;
  }
  const it=DATA.items[i];
  const btns=DATA.labels.map(l=>{
    const isC=it.c.includes(l.id);
    return `<button class="${isC?'cand':''}" onclick="pick('${l.id}')">
      <b>${l.id}</b>${l.title}</button>`}).join('');
  app.innerHTML=`
    <div class="bar"><i style="width:${i/DATA.items.length*100}%"></i></div>
    <div class="meta"><span>${i+1} / ${DATA.items.length}</span><span>${it.g}</span></div>
    <div class="title">${it.title}</div>
    <div class="clause">${it.t}</div>
    <div class="src">${it.src}</div>
    <h3>이 조항은 약관규제법 어느 조문과 관련됩니까 <span style="font-weight:400">(파란 테두리 = 기계가 고른 후보)</span></h3>
    <div class="grid">${btns}</div>
    <div class="row">
      <button class="none" onclick="pick('관련없음')">관련 없음 <kbd>N</kbd></button>
      <button class="hold" onclick="pick('보류')">보류 <kbd>H</kbd></button>
      <button class="back" onclick="if(i>0){i--;render()}">← 이전</button>
    </div>
    <p class="hint">숫자키 <kbd>7</kbd>~<kbd>9</kbd> 로 제7~9조 · 나머지는 클릭 ·
      <kbd>N</kbd> 관련없음 · <kbd>H</kbd> 보류<br>
      <b>불공정한지 묻는 게 아닙니다.</b> "이 조항이 무엇에 관한 것인가"만 보세요.
      해지 얘기면 제9조, 관할 얘기면 제14조입니다.</p>`;
}
document.addEventListener('keydown',e=>{
  if(i>=DATA.items.length)return;
  const k=e.key.toLowerCase();
  if(['7','8','9'].includes(k))pick(k);
  else if(k==='n')pick('관련없음'); else if(k==='h')pick('보류');
  else if(e.key==='Backspace'&&i>0){i--;render()}
});
render();
</script></body></html>"""


def main():
    if not SRC.exists():
        raise SystemExit(f"[!] {SRC.name} 이 없습니다.")
    html = (HTML.replace("__DATA__", SRC.read_text(encoding="utf-8"))
                .replace("__VER__", VER))
    OUT.write_text(html, encoding="utf-8")
    print(f"라벨링 도구 {VER} → {OUT}  ({json.loads(SRC.read_text(encoding='utf-8'))['items'].__len__()}개)")


if __name__ == "__main__":
    main()
