# -*- coding: utf-8 -*-
"""
ko-sroberta 를 ONNX 로 변환한다. 배포 때 메모리를 711MB → 272MB 로 줄이기 위해서다.

**결과물(models/onnx, 441MB)은 리포에 넣지 않는다.** 이 스크립트로 언제든 다시 만든다.

실행:  python src/build_onnx.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "jhgan/ko-sroberta-multitask"     # 4번 모듈에서 실측으로 고른 모델
OUT = ROOT / "models" / "onnx"


def main():
    from optimum.onnxruntime import ORTModelForFeatureExtraction
    from transformers import AutoTokenizer
    OUT.parent.mkdir(exist_ok=True)
    print(f"  {MODEL} → ONNX 변환 중…")
    ORTModelForFeatureExtraction.from_pretrained(MODEL, export=True).save_pretrained(OUT)
    AutoTokenizer.from_pretrained(MODEL).save_pretrained(OUT)
    sz = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"  완료 → {OUT.relative_to(ROOT)} ({sz:.0f} MB)")


if __name__ == "__main__":
    main()
