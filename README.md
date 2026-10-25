# dsh-image-ocr

给**装不了图的模型**装一只眼睛：聊天里粘贴的截图 → 可读文字。

**完全离线** · **不需要 API Key** · **不需要任何模型服务器** · 一个工具，只做一件事。

---

## 它解决什么问题

在 DeepSeek Harness（DSH）里，当会话使用的模型不支持图片输入时，你粘贴的图不会到达模型，
取而代之的是一行占位符：

```
[image omitted because this model accepts text only; attachment sha256:6c8ad019]
```

于是「看看这张截图里的报错」这类请求就没法回答。装上本插件多出一个工具 `image_ocr`：

```jsonc
{ "source": "6c8ad019" }        // 就是那行占位符里的 8 位 sha256 前缀
```

它把那 8 位前缀对应的图片找出来，用**本机离线 OCR** 转成逐行文字交回模型：

```
模型清单  名称与能力来自上游清单与公开能力表，可用性由本机出口实测得出
Kilo  Kilo Auto Free  Kilo  Kilo Nemotron 3.5 Sup...
纯文本  思考不可关  上下文 256K  视觉  可调思考  上下文 1.0M
最长输出 33K  默认档上限 33K  最长输出 131K  默认档上限 33K
刷新清单  重新探测可用性
```

（以上为真实识别结果示例，取自一张 820×840 的中文界面截图，共 72 个文字块。）

## 能力与边界

| ✅ 能 | ❌ 不能 |
|---|---|
| 截图、报错信息、日志 | 理解画面内容（「这是什么动物」） |
| 表格、菜单、按钮文字 | 手写体、艺术字（会出错字） |
| 代码、聊天记录、文档照片 | 极小的字号（建议先裁切放大） |
| 中文 / 英文为主的界面 | 需要联网的翻译、问答 |

**为什么不做「看懂画面」**：那需要视觉语言模型，意味着要联网或跑一个几 GB 的模型。
本插件的定位是**永远可用**的那条兜底路线：断网、没额度、没 Key 时它照样工作。

## 安装

### 方式 A：让你的 DSH agent 装（最省事）

在 DSH 里对它说：

> 帮我安装这个插件：github.com/`<你的账号>`/dsh-image-ocr

agent 会用插件管理器完成安装并启用。

### 方式 B：命令行

```bash
# 1) 装包（转发给 pnpm，支持 github: 规格）
dsh plugin --profile web add github:<账号>/dsh-image-ocr

# 2) 启用它的 bundle：在 DSH 的 设置 → 插件 里打开 dsh-image-ocr，
#    或让 agent 执行 plugin_manager / set_bundle
```

### 方式 C：手动 clone（下载 zip 也一样）

```bash
git clone https://github.com/<账号>/dsh-image-ocr.git
# 然后在 DSH 里把该目录作为 bundle 安装（plugin_manager / install_bundle，目标填本地目录）
```

### 装完做一次：准备 Python 环境

`image_ocr` 需要 Python 依赖（rapidocr / onnxruntime / opencv）。

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File setup.ps1
```

```bash
# macOS / Linux
bash setup.sh
```

这一步会：

1. 在插件目录下建 `.venv`；
2. 安装三个依赖（约 285 MB，其中 **OCR 模型由 rapidocr 这个 wheel 自带**，不需要另外下载模型文件）；
3. 打印自检：`模型齐备: True` 表示可以直接用。

> 已经有 Python 环境（含这三个包）也可以跳过，用行配置 `pythonPath` 或环境变量
> `DSH_IMAGE_OCR_PYTHON` 指过去即可。

## 用法

### 模型侧（工具调用）

```jsonc
// 读最近一张粘贴的图
{ "source": "latest" }

// 读某张粘贴的图，并要每行的像素坐标（用来定位按钮/控件）
{ "source": "6c8ad019", "layout": true }

// 读磁盘上的图片
{ "source": "C:\\shots\\error.png" }
```

### `source` 的三种写法

| 写法 | 含义 |
|---|---|
| 8 位十六进制（如 `6c8ad019`） | DSH 附件库里那行占位符给出的 sha256 前缀，4 位起即可 |
| `latest` | 最近一张粘贴的图片 |
| 文件路径 | 磁盘上任意 PNG / JPEG / WebP / GIF |

### 返回什么

```jsonc
{
  "path": "C:\\Users\\...\\dsh-pasted\\6c8ad019aee7.png",
  "text": "模型清单  名称与能力来自上游清单与公开能力表\nKilo  Kilo Auto Free  …",   // 按阅读顺序整理
  "blocks": 72,
  "truncated": false
}
```

`layout: true` 时，逐行文字会附带 `y0:x0 → y1:x1` 的像素范围。

### 不用插件，当命令行工具用

```bash
python python/image_read.py shot.png --layout
python python/image_read.py latest --json
```

## 配置（可选）

在 profile 里给本插件的行加 `config`：

```yaml
- id: dsh-image-ocr
  name: 'dsh-image-ocr'
  config:
    pythonPath: '/path/to/python'   # 指定解释器
    modelDir: '/path/to/models'     # 指定模型目录（默认取 rapidocr 自带）
    debug: false                    # true 时把诊断写到 %TEMP%\dsh-image-ocr.log
```

也可用环境变量：`DSH_IMAGE_OCR_PYTHON`、`DSH_OCR_MODEL_DIR`。

## 原理（想省时间可以跳过）

1. **图片其实一直在磁盘上。** DSH 把上传/粘贴的图片按内容寻址存成
   `~/.dsh/attachments/v1/objects/<sha256 前两位>/<完整 sha256>`（没有扩展名，
   所以普通看图工具认不出来）。插件按前缀找到它、按文件头判断格式，
   再复制一份带正确扩展名的副本给 OCR。
2. **离线 OCR。** 引擎是 [RapidOCR](https://github.com/RapidAI/RapidOCR)
   （PaddleOCR 的 PP-OCRv6 模型 + ONNXRuntime，CPU 推理），
   模型文件随 rapidocr wheel 分发。
3. **不存在下载分支。** 插件自己按显式路径建 ONNXRuntime session 并注入引擎配置，
   所以即使断网、即使 rapidocr 想去找模型，也走不到网络那条路。

## 依赖与平台

| 项目 | 要求 |
|---|---|
| DSH | 支持 profile bundle 的版本（0.2.x 及以上） |
| Python | 3.10+ |
| Python 包 | `rapidocr`、`onnxruntime`、`opencv-python-headless`（setup 脚本负责） |
| 操作系统 | Windows（`setup.ps1`）/ macOS、Linux（`setup.sh`）；OCR 本身跨平台 |
| 网络 | 安装时需要，运行识别时**不需要** |

## 常见问题

**Q：报「无法启动 Python」**
在插件目录跑一次 `setup.ps1` / `setup.sh`；或把 `pythonPath` 指到一个已装依赖的解释器。

**Q：报「找不到本地 OCR 模型」**
`python -m pip install rapidocr`（模型随它分发）；或用 `DSH_OCR_MODEL_DIR` 指向模型目录。

**Q：中文偶尔有错字**
用的是 PP-OCRv6 **small**（速度优先）。想更准可以换大模型，把 `modelDir` 指向替换后的模型目录。

**Q：图太大、识别慢**
先裁切要读的区域再识别；或调 `--threads`（默认 2，刻意限制，避免打满 CPU）。

**Q：能告诉我这张照片里有什么吗？**
不能——本插件只认字。要理解画面内容需要视觉模型（联网或本地大模型），那是另一条路线。

**Q：别人发的图片链接（http）能读吗？**
本插件只处理本机文件与 DSH 附件库。先用 `web_fetch` 之类的工具把图存到本地，再传文件路径。

## 卸载

1. 在 DSH 设置 → 插件里停用/移除 `dsh-image-ocr`（或让 agent 执行 `remove_bundle`）；
2. 删除插件目录即可（`.venv` 也在里面，一起删干净）。

## 许可与致谢

- 本插件代码：**MIT**（见 [LICENSE](LICENSE)）。
- OCR 引擎与模型：[RapidOCR](https://github.com/RapidAI/RapidOCR)（Apache-2.0）、
  PaddleOCR PP-OCRv6 模型（Apache-2.0）——详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

欢迎 issue / PR；如果你的模型有原生视觉能力，这个插件对你是多余的。