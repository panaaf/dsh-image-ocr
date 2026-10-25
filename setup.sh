#!/usr/bin/env bash
# 就地重建本插件自带的 Python 环境（离线 OCR 需要）。
#
#   bash setup.sh
#
# 装完即可用：插件会自动优先使用本目录下的 .venv/bin/python。
# OCR 模型由 rapidocr wheel 自带（rapidocr/models/*.onnx），不需要额外下载模型文件。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
PY="${PYTHON:-python3}"

if [ -d "$VENV" ]; then
  echo "已存在 .venv，跳过创建（想重建就先删掉它）"
else
  echo "创建虚拟环境：$VENV"
  "$PY" -m venv "$VENV"
fi

PIP="$VENV/bin/python"
if [ ! -x "$PIP" ]; then
  PIP="$VENV/Scripts/python.exe"   # Git Bash on Windows
fi

echo "安装 OCR 依赖（rapidocr / onnxruntime / opencv-python-headless）…"
"$PIP" -m pip install --upgrade pip
"$PIP" -m pip install rapidocr onnxruntime opencv-python-headless

echo
echo "自检："
"$PIP" - <<'PY'
import sys
print('  python :', sys.executable)
import rapidocr, onnxruntime, cv2
from pathlib import Path
d = Path(rapidocr.__file__).parent / 'models'
need = ['PP-OCRv6_det_small.onnx', 'ch_ppocr_mobile_v2.0_cls_mobile.onnx', 'PP-OCRv6_rec_small.onnx']
print('  模型目录:', d)
print('  模型齐备:', all((d / f).is_file() for f in need))
PY
echo
echo "完成。若自检显示「模型齐备: True」，工具 image_ocr 立即可用（不联网、无 Key）。"