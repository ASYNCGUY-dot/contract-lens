# -*- coding: utf-8 -*-
"""
ONNX 런타임으로 문장을 벡터로 만든다. `match_clauses.encode` 와 **같은 결과**를 낸다.

## 왜 만들었나

배포 때문이다. torch 로 모델을 올리면 프로세스가 711MB 를 쓴다. 무료 배포처는
대개 512MB 라 들어가지 않는다(Render 무료 512MB, HF Spaces 는 Docker 가 유료,
Railway·Fly.io 는 무료 티어 폐지).

ONNX 로 바꾸니 **272MB** 로 떨어졌다. 모델이 작아져서가 아니라 torch 런타임이
빠졌기 때문이다. 그리고 **벡터가 원본과 완전히 같다(코사인 유사도 1.000000).**

int8 양자화도 해봤지만 269MB 로 3MB 밖에 더 못 줄이면서 유사도가 0.957 로
떨어졌다. **얻는 것 없이 정확도만 잃으므로 쓰지 않는다.**

## 준비

    python src/build_onnx.py     models/onnx 를 만든다 (441MB, 리포에 넣지 않는다)

실행:  python src/encode_onnx.py     원본과 같은 값이 나오는지 확인
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
# ONNX_INT8=1 이면 양자화본을 쓴다. 메모리는 줄지만 정확도가 떨어질 수 있어 실측 후 결정한다.
ONNX_DIR = ROOT / "models" / ("onnx-int8" if os.getenv("ONNX_INT8") == "1" else "onnx")

# sentence-transformers 는 모델이 정한 max_seq_length 로 자른다. ko-sroberta 는 128 이다.
# 512 로 두면 긴 조항에서 더 많은 토큰을 보게 되어 **벡터가 달라진다.**
# 짧은 문장만으로 검증했을 때는 1.000000 이 나와 이 차이를 놓쳤다.
MAX_LEN = 128

_sess = None
_tok = None


def _load():
    global _sess, _tok
    if _sess is None:
        import onnxruntime as ort
        from transformers import AutoTokenizer
        if not ONNX_DIR.exists():
            raise SystemExit(f"[!] {ONNX_DIR} 가 없습니다. build_onnx.py 를 먼저 도세요.")
        f = next(p for p in ONNX_DIR.glob("*.onnx"))
        _sess = ort.InferenceSession(str(f),
                                     providers=["CPUExecutionProvider"])
        _tok = AutoTokenizer.from_pretrained(str(ONNX_DIR))
    return _sess, _tok


def encode(texts: list[str], batch: int = 16) -> np.ndarray:
    """
    문장을 정규화된 벡터로. **mean pooling 후 L2 정규화**는
    sentence-transformers 가 하던 것과 같아야 한다. 다르면 지금까지의 수치가 전부 무효다.
    """
    sess, tok = _load()
    out = []
    for i in range(0, len(texts), batch):
        b = tok(list(texts[i:i + batch]), padding=True, truncation=True,
                max_length=MAX_LEN, return_tensors="np")
        feed = {k: v for k, v in b.items() if k in {x.name for x in sess.get_inputs()}}
        h = sess.run(None, feed)[0]                       # (n, seq, dim)
        m = b["attention_mask"][:, :, None].astype(h.dtype)
        v = (h * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
        out.append(v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-12, None))
    return np.vstack(out).astype("float32")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from match_clauses import encode as orig
    t = ["회사는 회원에게 발생한 어떠한 손해에 대하여도 일체 책임을 지지 아니한다.",
         "이 약관에 관한 소송의 관할법원은 회사의 본점 소재지 법원으로 한다.",
         "사업자의 고의 또는 중대한 과실로 인한 법률상의 책임을 배제하는 조항"]
    a, b = orig(t), encode(t)
    s = [float(np.dot(a[i], b[i])) for i in range(len(t))]
    print(f"  원본과의 유사도 평균 {np.mean(s):.6f}  최저 {min(s):.6f}")
