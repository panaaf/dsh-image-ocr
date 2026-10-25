# 更新日志

## v1.0.0 — 2026-10-25

首个版本。

**新增**

- 工具 `image_ocr`：把图片变成逐行文字，`source` 支持三种写法
  （DSH 粘贴图的 8 位 sha256 前缀 / `latest` / 图片文件路径）。
- `layout: true` 时返回每行的像素包围盒，便于定位按钮与控件坐标。
- 按内容寻址读取 DSH 附件库（`~/.dsh/attachments/v1/objects/<前两位>/<sha256>`，
  文件无扩展名），自动按文件头判断格式并给出可读副本。

**工程**

- OCR 引擎：RapidOCR（PaddleOCR PP-OCRv6，ONNXRuntime **CPU** 推理，线程限制 2）。
- 模型文件由 `rapidocr` wheel 自带，**运行期零下载**；加载路径上不存在网络分支。
- `setup.ps1` / `setup.sh` 一键创建自带环境；`tests/selftest.mjs` 可离线自测。
- 代码 MIT；第三方组件与模型许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

**验证（发布时实测）**

- 820×840 中文界面截图：72 个文字块，识别正确。
- 802×596 中文设置界面：49 个文字块。
- 清空环境变量后仍可识别：不依赖其他应用的目录或虚拟环境。
- 匿名（未登录）可读取仓库内容与下载整包。