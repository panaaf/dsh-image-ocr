# 第三方组件与许可

本插件自身代码为 MIT。它**不打包**任何模型文件，而是使用安装到本机 Python 环境里的
第三方包及其随包分发的模型，运行时不下载任何内容。

| 组件 | 用途 | 许可 | 说明 |
|---|---|---|---|
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | OCR 引擎（Python 包 `rapidocr`） | Apache-2.0 | 由 `pip install rapidocr` 提供；其 wheel 内含下列 PP-OCR 模型文件 |
| PaddleOCR PP-OCRv6 模型 | 文本检测 / 方向分类 / 文本识别 | Apache-2.0 | 文件：`PP-OCRv6_det_small.onnx`、`ch_ppocr_mobile_v2.0_cls_mobile.onnx`、`PP-OCRv6_rec_small.onnx`，位于 `rapidocr/models/` |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | 模型推理（CPU） | MIT | Python 包 `onnxruntime` |
| [OpenCV](https://github.com/opencv/opencv-python) | 图像解码（headless 版） | Apache-2.0 | Python 包 `opencv-python-headless` |
| [NumPy](https://numpy.org/) | 数组处理 | BSD-3-Clause | 由 rapidocr 依赖带入 |
| [OmegaConf](https://github.com/omry/omegaconf) | 引擎配置对象 | BSD-3-Clause | 由 rapidocr 依赖带入 |

## 关于模型文件的再分发

本仓库**不含**任何 `.onnx` 模型文件，也不含 `.venv`。使用者通过
`pip install rapidocr` 从 PyPI 获取包与模型，因此再分发许可以上游包为准
（Apache-2.0，允许商用与再分发，需保留版权与许可声明）。

如果你把本插件打包进商业产品，请在「关于」页面保留上表中的归属说明。