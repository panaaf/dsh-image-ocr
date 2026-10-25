# -*- coding: utf-8 -*-
"""离线识图：把图片变成「可读的文字 + 版面位置」。不联网、不需要任何服务器或 API Key。

引擎是 RapidOCR（PaddleOCR 的 PP-OCRv6 模型 + ONNXRuntime，CPU 推理）。模型文件的
查找顺序（**都不存在下载分支**）：

1. ``$DSH_OCR_MODEL_DIR``（显式覆盖）；
2. 本脚本同级的 ``models/``（若把模型随包分发）；
3. **已安装的 rapidocr wheel 自带的 ``rapidocr/models/``** —— 默认就走这条，
   所以只要 ``pip install rapidocr onnxruntime opencv-python-headless`` 就能跑。

用法：
    python image_read.py <图片路径 | 粘贴图 sha256 前缀 | latest> [--json] [--layout]

依赖：rapidocr、onnxruntime、opencv-python-headless（numpy / omegaconf 由 rapidocr 带入）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pasted_image import find_by_prefix, materialize, newest  # noqa: E402

#: 三个模型文件（键就是 rapidocr 配置里的段名，注入 session 时按它对应）。
MODEL_FILES = {
    "Det": "PP-OCRv6_det_small.onnx",
    "Cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    "Rec": "PP-OCRv6_rec_small.onnx",
}

#: 交给 rapidocr 的固定配置：日志降到 error（整图无文字是正常输入，不该刷日志），
#: GPU 开关显式关掉，作为「执行提供者只有 CPU」的第二道防线。
RAPIDOCR_PARAMS = {
    "Global.log_level": "error",
    "EngineConfig.onnxruntime.use_cuda": False,
    "EngineConfig.onnxruntime.use_dml": False,
    "EngineConfig.onnxruntime.enable_cpu_mem_arena": False,
}

MIN_THREADS, MAX_THREADS = 1, 2


class OcrError(RuntimeError):
    """能直接给用户看的中文原因。"""


def _candidate_model_dirs() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("DSH_OCR_MODEL_DIR")
    if override:
        candidates.append(Path(override))
    candidates.append(HERE / "models")
    try:
        import rapidocr  # 没装时由 build_engine 报人话

        candidates.append(Path(rapidocr.__file__).resolve().parent / "models")
    except Exception:
        pass
    return candidates


def resolve_model_dir() -> Path:
    tried: list[str] = []
    for directory in _candidate_model_dirs():
        missing = [name for name in MODEL_FILES.values() if not (directory / name).is_file()]
        if not missing:
            return directory
        tried.append(f"{directory}（缺 {', '.join(missing)}）")
    raise OcrError(
        "找不到本地 OCR 模型。已试过：" + "；".join(tried) + "。"
        "最省事的修法是 pip install rapidocr（它自带这三个模型），"
        "或用 DSH_OCR_MODEL_DIR 指向放有模型的目录。"
    )


def _new_session(model_path: Path, cpu_threads: int):
    """CPU-only、关自旋的 ONNXRuntime session（常驻程序不该把 CPU 打满，线程默认限制在 2）。"""
    from onnxruntime import GraphOptimizationLevel, InferenceSession, SessionOptions

    options = SessionOptions()
    options.log_severity_level = 4  # 只报 fatal，info 会把命令行刷满
    options.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL
    options.intra_op_num_threads = cpu_threads
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    for key in ("session.intra_op.allow_spinning", "session.inter_op.allow_spinning"):
        try:
            options.add_session_config_entry(key, "0")
        except Exception:
            pass
    return InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])


def build_engine(cpu_threads: int = MAX_THREADS):
    """按模型目录建好引擎；缺依赖/缺模型都抛 :class:`OcrError`（人话）。"""
    directory = resolve_model_dir()
    try:
        import rapidocr
    except ImportError as exc:
        raise OcrError(
            f"本地 OCR 库 rapidocr 不可用（{exc}）。请先安装："
            "pip install rapidocr onnxruntime opencv-python-headless"
        ) from exc

    threads = max(MIN_THREADS, min(MAX_THREADS, int(cpu_threads)))
    sessions = {}
    for section, file_name in MODEL_FILES.items():
        try:
            sessions[section] = _new_session(directory / file_name, threads)
        except Exception as exc:
            raise OcrError(f"本地 OCR 模型加载失败（{file_name}）：{exc}") from exc

    try:
        engine = rapidocr.RapidOCR(params=dict(RAPIDOCR_PARAMS))
    except Exception as exc:
        raise OcrError(f"本地 OCR 引擎初始化失败：{exc}") from exc

    # 把自建 session 写回引擎配置：rapidocr 的 OrtInferSession 支持外部 session，
    # 但它的参数入口经 OmegaConf 拒收活对象，只能建好引擎后写回它自己的 cfg
    # （allow_objects 正是 OmegaConf 为「配置里挂活对象」提供的开关）。
    # 这一步是「不下载」的承重结构：没注入成功，第一次推理就会去网上找模型。
    try:
        from omegaconf import OmegaConf
    except ImportError as exc:
        raise OcrError("缺少 omegaconf（rapidocr 的依赖），请重装 rapidocr") from exc
    try:
        for section, session in sessions.items():
            node = OmegaConf.create(
                OmegaConf.to_container(engine.cfg[section]), flags={"allow_objects": True}
            )
            node.session = session
            engine.cfg[section] = node
    except Exception as exc:
        raise OcrError(f"本地 OCR 引擎的 session 注入失败：{exc}") from exc
    return engine


def load_bgr(path: Path):
    """图片 → 连续 BGR ndarray（rapidocr 直接吃这种形状）。"""
    image = None
    try:
        import cv2

        image = cv2.imread(str(path))
    except ImportError:
        image = None
    if image is None:  # cv2 读不出 webp/异常文件时用 PIL 兜底
        import numpy as np
        from PIL import Image

        with Image.open(path) as handle:
            image = np.array(handle.convert("RGB"))[:, :, ::-1].copy()
    return image


def to_blocks(result) -> list[dict]:
    """引擎原始输出 → 块列表（没文字就是空列表，不是错误）。"""
    if result is None:
        raise OcrError("本地 OCR 引擎没有返回结果")
    texts = getattr(result, "txts", None)
    if not texts:
        return []
    boxes = getattr(result, "boxes", None)
    scores = getattr(result, "scores", None)
    if boxes is None or len(boxes) < len(texts):
        raise OcrError(
            f"识别结果缺框坐标（文字 {len(texts)} 块，框 {0 if boxes is None else len(boxes)} 个）"
        )
    blocks: list[dict] = []
    for index, text in enumerate(texts):
        if not text:
            continue
        score = float(scores[index]) if scores is not None and index < len(scores) else 0.0
        box = [[float(point[0]), float(point[1])] for point in boxes[index]]
        blocks.append({"text": str(text), "score": score, "box": box})
    return blocks


def group_lines(blocks: list[dict], tol_ratio: float = 0.6) -> list[list[dict]]:
    """按「同一行」把文字块聚起来：中心 y 落在行高一半以内算同一行，行内按 x 排序。"""
    if not blocks:
        return []
    items = []
    for block in blocks:
        box = block.get("box") or []
        xs = [point[0] for point in box] or [0.0]
        ys = [point[1] for point in box] or [0.0]
        items.append(
            {
                "text": str(block.get("text") or ""),
                "box": box,
                "score": block.get("score"),
                "cy": sum(ys) / len(ys),
                "h": max(1.0, max(ys) - min(ys)),
                "x0": min(xs),
            }
        )
    items.sort(key=lambda item: item["cy"])
    lines: list[list[dict]] = []
    for item in items:
        placed = False
        for line in lines:
            reference = line[0]
            if abs(item["cy"] - reference["cy"]) <= max(reference["h"], item["h"]) * tol_ratio:
                line.append(item)
                placed = True
                break
        if not placed:
            lines.append([item])
    for line in lines:
        line.sort(key=lambda item: item["x0"])
    return lines


def render(lines: list[list[dict]]) -> str:
    return "\n".join(
        "  ".join(part["text"] for part in line if part["text"]) for line in lines
    ).strip()


def resolve_image(target: str) -> Path:
    """支持：真实路径 / latest / 粘贴图 sha256 前缀。"""
    candidate = Path(target)
    if candidate.is_file():
        return candidate
    found = newest(1) if target == "latest" else find_by_prefix(target)
    if not found:
        raise OcrError(f"找不到图片：{target}（附件库里没有匹配项，也不是磁盘上的文件）")
    return materialize(found[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="离线识图（本地 OCR，不联网、无 API Key）")
    parser.add_argument("image", help="图片路径 / latest / 粘贴图 sha256 前缀")
    parser.add_argument("--json", action="store_true", help="输出带坐标与置信度的 JSON")
    parser.add_argument("--layout", action="store_true", help="额外打印每行的包围盒")
    parser.add_argument("--threads", type=int, default=MAX_THREADS, help="CPU 线程数（默认 2）")
    parser.add_argument("--model-dir", default="", help="显式指定模型目录（覆盖自动查找）")
    args = parser.parse_args()

    if args.model_dir:
        os.environ["DSH_OCR_MODEL_DIR"] = str(args.model_dir)

    try:
        path = resolve_image(args.image)
        engine = build_engine(args.threads)
        image = load_bgr(path)
        height, width = image.shape[:2]
        blocks = to_blocks(engine(image))
    except OcrError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    lines = group_lines(blocks)
    text = render(lines)

    if args.json:
        print(
            json.dumps(
                {
                    "path": str(path),
                    "size": [width, height],
                    "blocks": [
                        {"text": part["text"], "box": part["box"], "score": part["score"]}
                        for line in lines
                        for part in line
                    ],
                    "text": text,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"[图片] {path}  {width}x{height}px  文字块 {len(blocks)} 个")
    print(text or "（没有识别到文字：这张图可能纯图形/照片，OCR 读不出内容）")
    if args.layout:
        print("\n[版面] 行  y0:x0 → y1:x1")
        for index, line in enumerate(lines, 1):
            xs = [
                p
                for part in line
                for p in ([part["box"][0][0], part["box"][2][0]] if part["box"] else [0, 0])
            ]
            ys = [
                p
                for part in line
                for p in ([part["box"][0][1], part["box"][2][1]] if part["box"] else [0, 0])
            ]
            if not xs or not ys:
                continue
            print(
                f"  {index:>3}. y{min(ys):.0f}:x{min(xs):.0f} → y{max(ys):.0f}:x{max(xs):.0f}  "
                + " ".join(part["text"] for part in line)[:60]
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())