# 就地重建本插件自带的 Python 环境（离线 OCR 需要）。
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1
#
# 装完即可用：插件会自动优先使用本目录下的 .venv\Scripts\python.exe。
# OCR 模型由 rapidocr wheel 自带（rapidocr\models\*.onnx），不需要额外下载模型文件。
param(
    [string]$Python = "python"
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $here '.venv'

if (Test-Path $venv) {
    Write-Host "已存在 .venv，跳过创建（想重建就先删掉它）"
} else {
    Write-Host "创建虚拟环境：$venv"
    & $Python -m venv $venv
}

$pip = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $pip)) { $pip = Join-Path $venv 'bin/python' }

Write-Host "安装 OCR 依赖（rapidocr / onnxruntime / opencv-python-headless）…"
& $pip -m pip install --upgrade pip
& $pip -m pip install rapidocr onnxruntime opencv-python-headless

Write-Host ""
Write-Host "自检："
& $pip -c "import sys; print('  python :', sys.executable); import rapidocr, onnxruntime, cv2; from pathlib import Path; d=Path(rapidocr.__file__).parent/'models'; print('  模型目录:', d); print('  模型齐备:', all((d/f).is_file() for f in ['PP-OCRv6_det_small.onnx','ch_ppocr_mobile_v2.0_cls_mobile.onnx','PP-OCRv6_rec_small.onnx']))"
Write-Host ""
Write-Host "完成。若自检显示「模型齐备: True」，工具 image_ocr 立即可用（不联网、无 Key）。"