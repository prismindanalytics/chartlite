#!/usr/bin/env python3
"""
Export Meta MMS model to ONNX format with INT8 quantization.

Requires:
    pip install transformers optimum[onnxruntime] torch

Produces:
    app/src/main/assets/models/mms_300m_int8.onnx  (~80MB)
    app/src/main/assets/models/mms_vocab.json
"""

import os
import json
from pathlib import Path

def export_mms():
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
    from optimum.onnxruntime import ORTModelForCTC, ORTQuantizer
    from optimum.onnxruntime.configuration import AutoQuantizationConfig

    model_id = "facebook/mms-1b-all"
    output_dir = Path("app/src/main/assets/models")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {model_id}...")
    processor = Wav2Vec2Processor.from_pretrained(model_id)
    model = Wav2Vec2ForCTC.from_pretrained(model_id)

    # Export to ONNX
    print("Exporting to ONNX...")
    ort_model = ORTModelForCTC.from_pretrained(
        model_id,
        export=True,
    )

    # Save intermediate ONNX
    temp_dir = output_dir / "temp_onnx"
    ort_model.save_pretrained(temp_dir)

    # Quantize to INT8
    print("Quantizing to INT8...")
    quantizer = ORTQuantizer.from_pretrained(temp_dir)
    qconfig = AutoQuantizationConfig.avx512_vnni(is_static=False)
    quantizer.quantize(
        save_dir=output_dir,
        quantization_config=qconfig,
    )

    # Rename to our expected filename
    onnx_files = list(output_dir.glob("*.onnx"))
    if onnx_files:
        onnx_files[0].rename(output_dir / "mms_300m_int8.onnx")

    # Export vocabulary
    print("Exporting vocabulary...")
    vocab = processor.tokenizer.get_vocab()
    # Invert: id -> token
    id_to_token = {v: k for k, v in vocab.items()}
    with open(output_dir / "mms_vocab.json", "w") as f:
        json.dump(id_to_token, f, indent=2, ensure_ascii=False)

    # Cleanup temp
    import shutil
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    final_model = output_dir / "mms_300m_int8.onnx"
    if final_model.exists():
        size_mb = final_model.stat().st_size / (1024 * 1024)
        print(f"Done! Model exported: {final_model} ({size_mb:.1f}MB)")
    else:
        print("Warning: ONNX model file not found after export")

    vocab_file = output_dir / "mms_vocab.json"
    if vocab_file.exists():
        with open(vocab_file) as f:
            v = json.load(f)
        print(f"Vocabulary exported: {vocab_file} ({len(v)} tokens)")


if __name__ == "__main__":
    export_mms()
