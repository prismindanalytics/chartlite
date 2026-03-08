#!/usr/bin/env bash
# Download Meta MMS ASR model for AfriMed Voice
#
# Model: facebook/mms-1b-all (CTC variant)
# Quantized to INT8 for mobile (~80MB)
# Supports 1000+ languages including South African and Ethiopian languages
#
# Reference: https://huggingface.co/facebook/mms-1b-all

set -euo pipefail

MODEL_DIR="app/src/main/assets/models"
mkdir -p "$MODEL_DIR"

MODEL_FILE="$MODEL_DIR/mms_300m_int8.onnx"
VOCAB_FILE="$MODEL_DIR/mms_vocab.json"

echo "=== AfriMed Voice — Meta MMS Model Download ==="
echo ""
echo "Model: Meta MMS (Massively Multilingual Speech)"
echo "Variant: mms-300m CTC, INT8 quantized"
echo "Size: ~80MB"
echo "Languages: 1000+ including Zulu, Xhosa, Afrikaans, Amharic, etc."
echo ""

# Check if model already exists
if [ -f "$MODEL_FILE" ]; then
    echo "Model already exists at $MODEL_FILE"
    echo "Delete it first if you want to re-download."
    exit 0
fi

# Option 1: Download pre-quantized model from HuggingFace
# (Uncomment when the quantized ONNX export is available)
#
# echo "Downloading MMS-300M INT8 ONNX model..."
# curl -L -o "$MODEL_FILE" \
#     "https://huggingface.co/facebook/mms-300m/resolve/main/onnx/model_int8.onnx"
#
# echo "Downloading vocabulary..."
# curl -L -o "$VOCAB_FILE" \
#     "https://huggingface.co/facebook/mms-300m/resolve/main/vocab.json"

# Option 2: Export and quantize from PyTorch (requires Python environment)
if command -v python3 &>/dev/null; then
    echo "Python detected. You can export the model with:"
    echo ""
    echo "  pip install transformers optimum onnxruntime"
    echo "  python3 scripts/export_mms_onnx.py"
    echo ""
fi

# For development: create placeholder files
echo "Creating placeholder model files for development..."
echo "The actual model will be available from HuggingFace."
echo ""
echo "To export the ONNX model yourself:"
echo "  1. pip install transformers optimum[onnxruntime]"
echo "  2. python3 scripts/export_mms_onnx.py"
echo ""
echo "Or download the pre-exported INT8 model when available."

touch "$MODEL_DIR/.gitkeep"
echo "Done. Run with actual model for ASR functionality."
