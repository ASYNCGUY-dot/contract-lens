# -*- coding: utf-8 -*-
"""
라벨링용 HTML 도구를 만든다. 엑셀에서 100줄 채우는 것보다 빠르고 덜 지친다.

브라우저에서 열어 조항 하나씩 보고 버튼을 누른다. 진행 상황은 브라우저에 자동 저장돼서
중간에 닫아도 이어서 할 수 있다. 다 하면 결과 한 줄이 나오고, 그걸 붙여넣으면 CSV에 반영된다.

데이터를 HTML 안에 박아 넣는다. `file://`로 열면 fetch가 CORS에 막혀서 외부 JSON을 못 읽는다.

실행:  python src/make_labeler.py
출력:  data/eval/labeler.html
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "eval" / "_items.json"
OUT = ROOT / "data" / "eval" / "labeler.html"

HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>조항 라벨링</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--dim:#666;--line:#e0e0e0;--sel:#2563eb;--ok:#059669;--hold:#d97706}
@media (prefers-color-scheme:dark){:root{--bg:#16181c;--fg:#e8e8e8;--dim:#9aa0a6;--line:#333;--sel:#60a5fa;--ok:#34d399;--hold:#fbbf24}}
*{box-sizing:border-box}
body{margin:0;padding:20px;font:15px/1.6 -apple-system,'Segoe UI',sans-serif;background:var(--bg);color:var(--fg)}
.wrap{max-width:860px;margin:0 auto}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin-bottom:8px}
.bar>i{display:block;height:100%;background:var(--sel);transition:width .2s}
.meta{display:flex;justify-content:space-between;color:var(--dim);font-size:13px;margin-bottom:16px}
.clause{border:1px solid var(--line);border-left:3px solid var(--sel);padding:16px;border-radius:6px;
  font-size:16px;line-height:1.7;margin-bottom:6px;min-height:90px}
.src{color:var(--dim);font-size:12px;margin-bottom:16px}
h3{font-size:13px;color:var(--dim);margin:18px 0 8px;font-weight:600}
.opt{display:block;width:100%;text-align:left;border:1px solid var(--line);background:transparent;
  color:var(--fg);padding:10px 12px;border-radius:6px;margin-bottom:6px;cursor:pointer;font:inherit;font-size:14px}
.opt:hover{border-color:var(--sel)}
.opt b{color:var(--sel);margin-right:8px}
.opt small{color:var(--dim);display:block;margin-top:2px;font-size:12.5px}
.row{display:flex;gap:8px;margin-top:14px}
.row button{flex:1;padding:12px;border-radius:6px;border:1px solid var(--line);background:transparent;
  color:var(--fg);cursor:pointer;font:inherit;font-size:14px}
.row .none{border-color:var(--ok);color:var(--ok)}
.row .hold{border-color:var(--hold);color:var(--hold)}
.row .back{color:var(--dim)}
details{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}
summary{cursor:pointer;color:var(--dim);font-size:13px}
.all{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:10px}
.all button{text-align:left;border:1px solid var(--line);background:transparent;color:var(--fg);
  padding:7px 9px;border-radius:5px;cursor:pointer;font:inherit;font-size:12.5px}
.all button:hover{border-color:var(--sel)}
.done{text-align:center;padding:30px 0}
textarea{width:100%;height:120px;font:12px/1.5 ui-monospace,monospace;padding:10px;border-radius:6px;
  border:1px solid var(--line);background:var(--bg);color:var(--fg);margin-top:12px}
.hint{color:var(--dim);font-size:12.5px;margin-top:10px}
kbd{border:1px solid var(--line);border-radius:3px;padding:1px 5px;font-size:11px}
</style></head><body><div class="wrap" id="app"></div>
<script>
const DATA=__DATA__;
const KEY='clauseledger_labels_v1';
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
      <button class="back" onclick="i=0;render()">처음부터 다시 보기</button>
      <button class="hold" onclick="if(confirm('라벨을 전부 지웁니다'))(ans={},save(),i=0,render())">초기화</button></div></div>`;
    return;
  }
  const it=DATA.items[i];
  const cands=it.c.map((c,k)=>{
    const t=DATA.types.find(t=>t.id===c[0])||{};
    return `<button class="opt" onclick="pick('${c[0]}')"><b>${k+1}</b>${t.ref||c[0]}
      <small>${(t.txt||c[1]).slice(0,80)}</small></button>`}).join('');
  const all=DATA.types.map(t=>`<button onclick="pick('${t.id}')">${t.ref} · ${t.txt.slice(0,26)}</button>`).join('');
  app.innerHTML=`
    <div class="bar"><i style="width:${i/DATA.items.length*100}%"></i></div>
    <div class="meta"><span>${i+1} / ${DATA.items.length}</span><span>${it.g}군</span></div>
    <div class="clause">${it.t}</div>
    <div class="src">${it.src}</div>
    <h3>이 조항에 해당하는 유형이 있습니까</h3>
    ${cands}
    <div class="row">
      <button class="none" onclick="pick('없음')">해당 없음 <kbd>N</kbd></button>
      <button class="hold" onclick="pick('보류')">보류 <kbd>H</kbd></button>
      <button class="back" onclick="if(i>0){i--;render()}">← 이전</button>
    </div>
    <details><summary>후보에 없는 유형 고르기 (28개 전체)</summary><div class="all">${all}</div></details>
    <p class="hint"><kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> 후보 선택 · <kbd>N</kbd> 해당 없음 ·
      <kbd>H</kbd> 보류 · 애매하면 억지로 고르지 말고 보류를 누르세요</p>`;
}
document.addEventListener('keydown',e=>{
  if(i>=DATA.items.length)return;
  const k=e.key.toLowerCase();
  if(['1','2','3'].includes(k))pick(DATA.items[i].c[+k-1][0]);
  else if(k==='n')pick('없음'); else if(k==='h')pick('보류');
  else if(e.key==='Backspace'&&i>0){i--;render()}
});
render();
</script></body></html>"""


def main():
    if not SRC.exists():
        raise SystemExit("[!] data/eval/_items.json 이 없습니다.")
    OUT.write_text(HTML.replace("__DATA__", SRC.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"라벨링 도구 → {OUT}")
    print("\n브라우저에서 이 파일을 열면 됩니다. 진행 상황은 자동 저장됩니다.")


if __name__ == "__main__":
    main()
