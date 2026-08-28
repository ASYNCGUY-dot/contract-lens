// FastAPI 백엔드 호출. 개발 중에는 uvicorn 이 8000 포트에서 돈다.
const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export async function analyze(text) {
  const r = await fetch(`${BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, llm: false }),
  });
  if (!r.ok) {
    // FastAPI 는 실패 사유를 detail 에 담아 보낸다. 그대로 보여주는 편이 낫다.
    let msg = `서버가 ${r.status} 를 돌려주었습니다.`;
    try {
      const d = await r.json();
      if (d.detail) msg = typeof d.detail === "string" ? d.detail : msg;
    } catch { /* 본문이 JSON 이 아닐 수 있다 */ }
    throw new Error(msg);
  }
  return r.json();
}

export async function health() {
  try {
    const r = await fetch(`${BASE}/health`);
    return r.ok && (await r.json()).ok === true;
  } catch {
    return false;
  }
}
