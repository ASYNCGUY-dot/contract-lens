import { useEffect, useMemo, useState } from "react";
import { addFeedback, allFeedback, analyze, articles, health, myFeedback } from "./api";
import "./App.css";

const NAME = "계약서 돋보기";
const SUB = "Contract Lens";
const MAX = 200000;

const SAMPLE = `제1조 (목적) 이 약관은 회사가 제공하는 서비스의 이용조건을 정함을 목적으로 한다.
제2조 (면책) 회사는 회원에게 발생한 어떠한 손해에 대하여도 일체 책임을 지지 아니한다.
제3조 (관할법원) 이 약관에 관한 소송의 관할법원은 회사의 본점 소재지 법원으로 한다.
제4조 (서비스 이용시간) 서비스는 연중무휴 1일 24시간 제공함을 원칙으로 한다.`;

// 조항이 가질 수 있는 상태는 셋뿐이다. 색은 경고가 아니라 구분용으로만 쓴다.
function stateOf(c) {
  if (c.건너뜀) return "skip";
  if (!c.후보 || c.후보.length === 0) return "none";
  return "found";
}

const STATE_LABEL = {
  found: "함께 볼 조문",
  none: "관련 조문 없음",
  skip: "대조하지 않음",
};

function Header({ tab, setTab, hasResult, dark, setDark }) {
  return (
    <header className="hdr">
      <div className="brand">
        <span className="mark" aria-hidden="true">◎</span>
        <span className="bname">{NAME}</span>
        <span className="bsub">{SUB}</span>
      </div>
      <nav className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "input"}
                className={tab === "input" ? "on" : ""}
                onClick={() => setTab("input")}>입력</button>
        <button role="tab" aria-selected={tab === "result"}
                className={tab === "result" ? "on" : ""}
                disabled={!hasResult}
                onClick={() => setTab("result")}>결과</button>
        <button role="tab" aria-selected={tab === "feedback"}
                className={tab === "feedback" ? "on" : ""}
                onClick={() => setTab("feedback")}>후기</button>
      </nav>
      <button className="ghost" onClick={() => setDark(!dark)}
              aria-label={dark ? "밝은 화면으로" : "어두운 화면으로"}>
        {dark ? "☀" : "☾"}
      </button>
    </header>
  );
}

/**
 * 사진에서 글자를 읽어 온다. **브라우저 안에서 처리하므로 사진이 서버로 가지 않는다.**
 *
 * 읽은 결과를 바로 대조에 넘기지 않고 편집창에 넣는다. OCR 이 틀리면 조항 내용
 * 자체가 바뀌기 때문이다. "책임을 진다"가 "책임을 지지 않는다"로 읽히면 대조가
 * 아무리 정확해도 결과는 완전히 틀린다. **사람이 눈으로 보고 고쳐야 한다.**
 *
 * 2026-09-09 실측(한글 계약서 이미지 7종)에서 tesseract 자체 신뢰도가 글자
 * 정확도를 잘 따라갔다 — 신뢰도 66 일 때 정확도 95.2%, 27 일 때 16.8%,
 * 13 일 때 4.8%. 다만 표본이 7개뿐이라 아래 경계값은 정밀한 기준이 아니라
 * 대략의 눈금이다. 조건별로는 조명이 가장 크게 깎았고(-20.8%p), 해상도가
 * 그다음(-15.0%p)이었으며, 둘이 겹치면 곱해져서 무너진다.
 */
/**
 * 사진을 두 배로 키운다. **글자를 더 잘 읽으려는 것이지 화질을 높이는 게 아니다.**
 *
 * 실측에서 같은 사진을 두 배로 키우자 인식 신뢰도가 66 에서 92 로 오르고, 네 개
 * 조항의 조 번호를 2/4 에서 4/4 로 전부 살렸다. 세 배는 두 배와 결과가 같았으므로
 * 두 배까지만 키운다. 다만 원본이 이미 크면 메모리만 쓰므로 긴 변 3000px 에서 멈춘다.
 */
async function 두배로(file) {
  try {
    const img = await createImageBitmap(file);
    const k = Math.min(2, 3000 / Math.max(img.width, img.height));
    if (k <= 1) return file;
    const c = document.createElement("canvas");
    c.width = Math.round(img.width * k);
    c.height = Math.round(img.height * k);
    const ctx = c.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, 0, 0, c.width, c.height);
    img.close();
    const blob = await new Promise((r) => c.toBlob(r, "image/png"));
    return blob || file;
  } catch {
    return file;               // 못 키우면 원본으로 간다. 실패할 일은 아니다.
  }
}

/**
 * 인식이 쓸 만한지 판단한다.
 *
 * **신뢰도만 보면 안 된다.** 실측에서 나쁜 사진을 키웠더니 신뢰도가 27 에서 51 로
 * 올랐는데 조 번호는 여전히 하나도 못 살렸다. 조 번호는 한 글자라, 그것이 틀리면
 * 그 조항이 통째로 앞 조항에 붙어 대조 자체가 어긋난다. 그래서 조 번호 개수를
 * 먼저 보고 신뢰도는 참고로만 쓴다.
 */
function 인식평가(조수, conf) {
  if (조수 === 0) {
    return ["bad", "조 번호(제1조, 제2조 …)를 하나도 찾지 못했습니다. 글자가 크게 나오도록 " +
                   "가까이서 다시 찍거나, 아래 칸에 직접 붙여넣어 주세요."];
  }
  if (conf >= 70) {
    return ["ok", "조항 " + 조수 + "개를 찾았습니다. 원본과 개수가 같은지, 글자가 맞는지 " +
                  "한 번 훑어봐 주세요."];
  }
  return ["warn", "조항 " + 조수 + "개를 찾았습니다. 다만 군데군데 틀렸을 수 있으니 " +
                  "원본과 대조해 고쳐 주세요. 특히 빠진 조항이 없는지 보세요."];
}

function PhotoInput({ onText, disabled }) {
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [done, setDone] = useState(null);
  const [err, setErr] = useState("");

  // 인자로 FileList 를 그대로 받으면 안 된다. 같은 사진을 다시 고를 수 있게
  // input.value 를 비우는 순간 그 FileList 도 함께 비워지기 때문이다. 배열로
  // 복사해 넘긴다.
  async function read(files) {
    if (!files || !files.length) return;
    setBusy(true); setErr(""); setDone(null);
    try {
      setProgress("글자 인식기를 준비하는 중… 처음 한 번은 20초쯤 걸립니다");
      const { createWorker } = await import("tesseract.js");
      const worker = await createWorker("kor", 1, {
        logger: (m) => {
          if (m.status === "recognizing text") {
            setProgress("읽는 중… " + Math.round(m.progress * 100) + "%");
          }
        },
      });
      const parts = [];
      let sum = 0;
      for (let i = 0; i < files.length; i++) {
        if (files.length > 1) setProgress((i + 1) + " / " + files.length + "장째를 읽는 중…");
        const { data } = await worker.recognize(await 두배로(files[i]));
        parts.push(data.text.trim());
        sum += data.confidence;
      }
      await worker.terminate();
      const text = parts.join(String.fromCharCode(10, 10));
      onText(text);
      setDone({
        conf: Math.round(sum / files.length),
        n: files.length,
        // 조항 분리기가 쓰는 것과 같은 규칙으로 센다
        조수: (text.match(/제\s*\d+\s*조/g) || []).length,
      });
    } catch (e) {
      setErr("글자를 읽지 못했습니다. " + (e && e.message ? e.message : ""));
    } finally {
      setBusy(false); setProgress("");
    }
  }

  const [tone, msg] = done ? 인식평가(done.조수, done.conf) : [];

  return (
    <div className="ocr">
      <div className="rowbetween">
        <label className={"ocrbtn" + (busy || disabled ? " off" : "")}>
          {busy ? "읽는 중…" : "사진에서 글자 가져오기"}
          <input type="file" accept="image/*" multiple hidden
                 disabled={disabled || busy}
                 onChange={(e) => {
                   const picked = Array.from(e.target.files);
                   e.target.value = "";
                   read(picked);
                 }} />
        </label>
        <span className="small">사진은 이 브라우저 안에서만 처리됩니다</span>
      </div>
      {busy && <p className="small ocrbar">{progress}</p>}
      {err && <p className="err" role="alert">{err}</p>}
      {done && (
        <p className={"ocrmsg " + tone}>
          <b>사진 {done.n}장을 읽었습니다.</b> {msg}
          <span className="small"> (인식 신뢰도 {done.conf})</span>
        </p>
      )}
    </div>
  );
}

function InputView({ text, setText, onRun, busy, err, apiUp }) {
  return (
    <section className="wrap narrow">
      <h1 className="h1">약관을 붙여넣고<br />어떤 법 조문을 볼지 확인하세요</h1>
      <p className="lead">
        계약서나 약관 전문을 붙여넣거나 사진으로 올리면 조항마다 관련 있어 보이는
        약관규제법 조문을 나란히 놓아 드립니다.
      </p>

      <div className="card pad">
        <div className="rowbetween">
          <label className="lbl" htmlFor="ta">약관 전문</label>
          <button className="link" onClick={() => setText(SAMPLE)}>예시 넣기</button>
        </div>
        <PhotoInput onText={setText} disabled={busy} />
        <textarea id="ta" value={text} onChange={(e) => setText(e.target.value)}
                  placeholder="여기에 약관 전문을 붙여넣어 주세요."
                  maxLength={MAX} rows={10} />
        <div className="rowbetween small">
          <span>{text.length.toLocaleString()} / {MAX.toLocaleString()}자</span>
          <span>조항 단위로 나누어 대조합니다</span>
        </div>
        {err && <p className="err" role="alert">{err}</p>}
        <div className="rowend">
          <button className="primary" onClick={onRun} disabled={busy || !text.trim()}>
            {busy ? "대조하는 중…" : "관련 조문 살펴보기"}
          </button>
        </div>
        {!apiUp && (
          <p className="note">
            분석 서버에 닿지 않습니다. 프로젝트 폴더에서
            <code> uvicorn src.api:app --port 8000 </code>을 실행해 주세요.
          </p>
        )}
      </div>

      <div className="card pad promise">
        <p className="lbl">이 서비스는</p>
        <ul>
          <li><b>관련 있어 보이는 법 조문을 나란히 제시합니다</b></li>
          <li>불공정 여부를 판정하지 않습니다</li>
          <li>무효인지 말하지 않습니다</li>
          <li>점수나 등급을 매기지 않습니다</li>
        </ul>
      </div>

      <div className="card pad privacy">
        <p className="lbl">붙여넣은 내용은 저장하지 않습니다</p>
        <p>
          입력한 약관은 대조에만 쓰이고 <b>파일이나 데이터베이스에 남기지 않습니다.</b>
          서버 기록에도 본문은 남지 않습니다. 화면을 닫으면 결과도 사라지므로,
          남겨 두시려면 결과 화면에서 내려받으세요.
        </p>
        <p className="small">
          <b>사진은 서버로 보내지 않습니다.</b> 글자 인식을 이 브라우저 안에서
          처리하므로 사진 파일 자체는 이 기기를 벗어나지 않습니다.
        </p>
        <p className="small">
          다만 시험용으로 만든 것이라 계약 당사자를 알아볼 수 있는 부분은
          지우고 넣으시는 편이 안전합니다.
        </p>
        <p className="small">
          <b>후기 탭에 남기신 글은 저장됩니다.</b> 쓰신 분과 운영자만 볼 수 있습니다.
        </p>
      </div>
    </section>
  );
}

/**
 * 결과를 사람이 읽을 수 있는 텍스트로 만든다.
 *
 * .txt 로 주는 이유는 어디서나 열리기 때문이다. 이 도구를 쓰는 사람은
 * 법을 모르는 일반인이라 .md 나 .json 은 열어도 읽기 어렵다.
 *
 * **고지를 파일 안에도 넣는다.** 파일은 화면을 떠나 혼자 돌아다니고,
 * 받은 사람은 이것이 무엇인지 모른 채 읽는다.
 */
function toText(data, laws) {
  const L = [];
  const line = "─".repeat(58);
  L.push(`${NAME} (${SUB}) — 대조 결과`);
  L.push(`생성 ${new Date().toLocaleString("ko-KR")}`);
  L.push(line, data.고지, line, "");

  data.조항.forEach((c) => {
    const st = stateOf(c);
    L.push(`■ ${c.조} ${c.제목 || ""}`.trimEnd());
    L.push(`  ${c.본문}`);
    L.push("");
    if (st === "skip") {
      L.push(`  · 대조하지 않음 — ${c.건너뜀}`);
    } else if (st === "none") {
      L.push("  · 관련 조문 없음 — 제7~14조와 관련이 뚜렷한 조문을 찾지 못했습니다.");
    } else {
      L.push(`  · 관련 있어 보이는 조문 ${c.후보.length}개 (순서는 정답 순서가 아닙니다)`);
      c.후보.forEach((x) => {
        L.push(`    [후보 ${x.순위}] ${x.인용} (${x.제목})`);
        const a = laws?.[x.조];
        if (a) {
          L.push(`      ${a.본문}`);
          a.호.forEach((h) => L.push(`        ${h.번호}. ${h.내용} [${h.효력}]`));
        }
      });
    }
    L.push("");
  });

  L.push(line, data.고지);
  return L.join(String.fromCharCode(10));
}

function download(data, laws) {
  const d = new Date();
  const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  const blob = new Blob([toText(data, laws)], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `계약서돋보기_결과_${stamp}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * 후기 게시판. **작성자 본인과 운영자만 읽는다.**
 *
 * 로그인 체계를 만들지 않았다. 지인 몇 명이 쓰는 시험용이므로 이름과 비밀번호
 * 네 자리면 충분하다. 비밀번호는 서버에서 해시로만 보관한다.
 *
 * 비밀번호가 틀리면 "틀렸다"고 알리지 않고 빈 목록을 준다. 남의 이름으로
 * 비밀번호를 맞혀 보는 일을 조금이라도 어렵게 하기 위해서다.
 */
function FeedbackView() {
  const [mode, setMode] = useState("write");
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [body, setBody] = useState("");
  const [key, setKey] = useState("");
  const [list, setList] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(fn, after) {
    setBusy(true); setMsg("");
    try { after(await fn()); }
    catch (e) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  const canWrite = name && pw.length >= 4 && body.trim().length >= 5;
  const canRead = name && pw.length >= 4;

  return (
    <section className="wrap narrow">
      <h1 className="h1">써보시고 후기를 남겨 주세요</h1>
      <p className="lead">
        무엇이 도움이 됐는지, 어디가 엉뚱했는지 알려 주시면 고치는 데 씁니다.
        <b> 남기신 글은 쓰신 분과 운영자만 볼 수 있습니다.</b>
      </p>

      <div className="filters">
        {[["write", "후기 남기기"], ["mine", "내 후기 보기"], ["admin", "운영자"]].map(([k, l]) => (
          <button key={k} className={mode === k ? "on" : ""}
                  onClick={() => { setMode(k); setList(null); setMsg(""); }}>{l}</button>
        ))}
      </div>

      <div className="card pad">
        {mode !== "admin" ? (
          <>
            <div className="fbrow">
              <label>이름 또는 별명
                <input value={name} onChange={(e) => setName(e.target.value)}
                       maxLength={20} placeholder="예: 민수" />
              </label>
              <label>비밀번호 (4자 이상)
                <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
                       maxLength={32} placeholder="내 글을 다시 볼 때 씁니다" />
              </label>
            </div>
            {mode === "write" && (
              <>
                <label className="lbl" htmlFor="fb">후기</label>
                <textarea id="fb" rows={6} value={body} maxLength={4000}
                          onChange={(e) => setBody(e.target.value)}
                          placeholder="어떤 계약서를 넣어 보셨는지, 결과가 맞았는지, 화면에서 불편했던 점 등" />
              </>
            )}
            <div className="rowend">
              <button className="primary"
                      disabled={busy || (mode === "write" ? !canWrite : !canRead)}
                      onClick={() => mode === "write"
                        ? run(() => addFeedback(name, pw, body), () => {
                            setBody("");
                            setMsg("남겨 주셔서 고맙습니다. 내 후기 보기에서 다시 볼 수 있습니다.");
                          })
                        : run(() => myFeedback(name, pw), (d) => {
                            setList(d.목록);
                            if (!d.목록.length) setMsg("해당하는 글이 없습니다. 이름과 비밀번호를 확인해 주세요.");
                          })}>
                {busy ? "잠시만요…" : mode === "write" ? "후기 남기기" : "내 후기 불러오기"}
              </button>
            </div>
          </>
        ) : (
          <>
            <label className="lbl" htmlFor="ak">운영자 키</label>
            <input id="ak" type="password" value={key} onChange={(e) => setKey(e.target.value)}
                   placeholder="ADMIN_KEY" />
            <div className="rowend">
              <button className="primary" disabled={busy || !key}
                      onClick={() => run(() => allFeedback(key), (d) => setList(d.목록))}>
                {busy ? "잠시만요…" : "전체 후기 보기"}
              </button>
            </div>
          </>
        )}
        {msg && <p className="note">{msg}</p>}
      </div>

      {list?.length > 0 && (
        <div className="fblist">
          <p className="lbl">{list.length}건</p>
          {list.map((f) => (
            <div key={f.id} className="card pad fbitem">
              <div className="rowbetween small">
                <b>{f.이름}</b><span>{f.작성.slice(0, 16).replace("T", " ")}</span>
              </div>
              <p>{f.내용}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Summary({ data }) {
  const st = data.조항.map(stateOf);
  const items = [
    { k: "전체 조항", v: data.조항수, cls: "" },
    { k: "관련 조문을 찾은 조항", v: st.filter((s) => s === "found").length, cls: "found" },
    { k: "관련 조문 없음", v: st.filter((s) => s === "none").length, cls: "none" },
    { k: "대조하지 않음", v: st.filter((s) => s === "skip").length, cls: "skip" },
  ];
  return (
    <div className="summary">
      {items.map((i) => (
        <div key={i.k} className={`sm ${i.cls}`}>
          <div className="smv">{i.v}</div>
          <div className="smk">{i.k}</div>
        </div>
      ))}
    </div>
  );
}

// 법 조문 원문. **여기 "무효로 한다"는 법이 그렇게 쓰여 있는 것이지
// 이 서비스의 판정이 아니다.** 그 구분이 흐려지지 않게 출처를 함께 밝힌다.
function ArticleText({ art }) {
  if (!art) return <p className="msg">조문 원문을 불러오는 중입니다…</p>;
  return (
    <div className="artbox">
      <p className="artsrc">아래는 법 조문 원문입니다 — {art.인용}({art.제목})</p>
      <p className="artbody">{art.본문}</p>
      <ol className="arthos">
        {art.호.map((h) => (
          <li key={h.번호}>
            <span className="hono">{h.번호}.</span>
            <span>{h.내용}</span>
            {h.효력 && <em className="hoeff">{h.효력}</em>}
          </li>
        ))}
      </ol>

      {art.호?.[0]?.효력설명 && (
        <p className="effnote">※ {art.호[0].효력설명}</p>
      )}

      {art.용어?.length > 0 && (
        <div className="terms">
          <p className="termhead">이 조문에 나오는 말</p>
          <dl>
            {art.용어.map((t) => (
              <div key={t.말}>
                <dt>{t.말}</dt>
                <dd>{t.뜻}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

const LONG = 320;   // 이보다 길면 접는다. 조항 하나가 화면을 다 먹으면 대조가 안 된다.

function Clause({ c, laws }) {
  const s = stateOf(c);
  const [open, setOpen] = useState(null);
  const [more, setMore] = useState(false);
  const long = c.본문.length > LONG;
  const shown = long && !more ? c.본문.slice(0, LONG) + "…" : c.본문;
  return (
    <article className={`clause ${s}`}>
      <div className="left">
        {c.제목 && <div className="cno">{c.조}</div>}
        <h3 className="ct">{c.제목 || c.조}</h3>
        <p className="cb">{shown}</p>
        {long && (
          <button className="link" onClick={() => setMore(!more)}>
            {more ? "본문 접기" : `본문 전체 보기 (${c.본문.length.toLocaleString()}자)`}
          </button>
        )}
      </div>
      <div className="right">
        <div className={`badge ${s}`}>
          {STATE_LABEL[s]}{s === "found" ? ` ${c.후보.length}개` : ""}
        </div>
        {s === "found" && (
          <ul className="cands">
            {c.후보.map((x) => (
              <li key={x.순위} className={open === x.순위 ? "open" : ""}>
                <button className="candbtn"
                        aria-expanded={open === x.순위}
                        onClick={() => setOpen(open === x.순위 ? null : x.순위)}>
                  <span className="rank">후보 {x.순위}</span>
                  <span className="cite">{x.인용}</span>
                  <span className="ctitle">{x.제목}</span>
                  {laws?.[x.조]?.안내 && (
                    <span className="cguide">{laws[x.조].안내}</span>
                  )}
                  <span className="chev" aria-hidden="true">
                    {open === x.순위 ? "접기" : "조문 원문 보기"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {s === "none" && (
          <p className="msg">
            약관규제법 제7조부터 제14조까지 대조했지만 관련성이 뚜렷한 조문이 없었습니다.
          </p>
        )}
        {s === "skip" && <p className="msg">{c.건너뜀}</p>}
      </div>
      {open !== null && (
        <div className="artfull">
          <ArticleText art={laws?.[c.후보.find((x) => x.순위 === open)?.조]} />
        </div>
      )}
    </article>
  );
}

function ResultView({ data, laws }) {
  const [filter, setFilter] = useState("all");
  const st = useMemo(() => data.조항.map(stateOf), [data]);
  const counts = {
    all: data.조항.length,
    found: st.filter((s) => s === "found").length,
    none: st.filter((s) => s === "none").length,
    skip: st.filter((s) => s === "skip").length,
  };
  const shown = data.조항.filter((c, i) => filter === "all" || st[i] === filter);

  return (
    <section className="wrap">
      <div className="rowbetween resulthead">
        <h2 className="h2">대조 결과</h2>
        <button className="secondary" onClick={() => download(data, laws)}>
          결과 내려받기 (.txt)
        </button>
      </div>
      <Summary data={data} />

      <div className="notice">
        <p>{data.고지}</p>
      </div>

      <div className="filters" role="tablist">
        {[["all", "전체"], ["found", "관련 조문 있음"],
          ["none", "관련 조문 없음"], ["skip", "대조하지 않음"]].map(([k, label]) => (
          <button key={k} role="tab" aria-selected={filter === k}
                  className={filter === k ? "on" : ""}
                  onClick={() => setFilter(k)}>
            {label} <span className="cnt">{counts[k]}</span>
          </button>
        ))}
      </div>

      <div className="clauses">
        {shown.map((c, i) => <Clause key={`${c.조}-${i}`} c={c} laws={laws} />)}
        {shown.length === 0 && <p className="msg pad">해당하는 조항이 없습니다.</p>}
      </div>

      <div className="legend">
        <div className="lg found">
          <b>관련 조문 있음</b>
          <p>관련 있어 보이는 조문을 찾았습니다. 원문과 함께 살펴보세요.</p>
        </div>
        <div className="lg none">
          <b>관련 조문 없음</b>
          <p>제7~14조와 관련이 뚜렷한 조문을 찾지 못했습니다.</p>
        </div>
        <div className="lg skip">
          <b>대조하지 않음</b>
          <p>목적·정의 같은 문서 설명 조항이라 대조 대상에서 뺐습니다.</p>
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const [tab, setTab] = useState("input");
  const [text, setText] = useState("");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [apiUp, setApiUp] = useState(true);
  const [dark, setDark] = useState(false);
  const [laws, setLaws] = useState(null);

  useEffect(() => { health().then(setApiUp); }, []);
  // 조문은 고정이라 결과가 나오면 한 번만 받아둔다.
  useEffect(() => {
    if (data && !laws) articles().then(setLaws).catch(() => {});
  }, [data, laws]);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);

  async function run() {
    setBusy(true); setErr("");
    try {
      const d = await analyze(text);
      setData(d); setTab("result");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <Header tab={tab} setTab={setTab} hasResult={!!data} dark={dark} setDark={setDark} />
      <main>
        {tab === "feedback" ? <FeedbackView />
          : tab === "input"
          ? <InputView text={text} setText={setText} onRun={run}
                       busy={busy} err={err} apiUp={apiUp} />
          : data && <ResultView data={data} laws={laws} />}
      </main>
      <footer className="ftr">
        <span>{NAME} · {SUB}</span>
        <span>법률 자문이 아닌 정보 탐색 도구입니다</span>
      </footer>
    </div>
  );
}
