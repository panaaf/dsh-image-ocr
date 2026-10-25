# -*- coding: utf-8 -*-
"""把聊天里粘贴的图片（attachment-id: sha256:xxxxxxxx…）解析成可读的真实文件路径。

DSH 把上传/粘贴的图片按内容寻址落盘在：
    %USERPROFILE%\\.dsh\\attachments\\v1\\objects\\<sha256 前两位>\\<完整 sha256>
文件**没有扩展名**，所以视觉工具（modlens / 图片查看器）认不出来。
本脚本按前缀定位对象、按文件头判断真实格式，再复制一份带正确扩展名的副本到临时目录。

用法：
    python pasted_image.py latest            # 最近一张
    python pasted_image.py 6c8ad019          # 按 sha256 前缀（4 位以上即可）
    python pasted_image.py list 10           # 列出最近 10 张（含时间、格式、大小）
    python pasted_image.py latest --show     # 顺便打印解析出的路径
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

MAGIC = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"RIFF", ".webp"),
    (b"BM", ".bmp"),
]


def objects_root() -> Path:
    root = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
    return root / "attachments" / "v1" / "objects"


def sniff(path: Path) -> str:
    """按文件头判断真实图片格式（不认识就退回 .bin）。"""
    with path.open("rb") as handle:
        head = handle.read(16)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    for magic, ext in MAGIC:
        if head.startswith(magic):
            return ext
    return ".bin"


def iter_objects():
    root = objects_root()
    if not root.is_dir():
        return
    for bucket in root.iterdir():
        if not bucket.is_dir():
            continue
        for item in bucket.iterdir():
            if item.is_file():
                yield item


def find_by_prefix(prefix: str) -> list[Path]:
    prefix = prefix.strip().lower().replace("sha256:", "")
    if len(prefix) < 4:
        raise SystemExit("前缀至少 4 位十六进制字符，或直接用 latest")
    root = objects_root()
    bucket = root / prefix[:2]
    candidates = [p for p in bucket.glob(f"{prefix}*") if p.is_file()] if bucket.is_dir() else []
    if not candidates:  # 前缀可能不完整到桶级，退化为全量扫描
        candidates = [p for p in iter_objects() if p.name.startswith(prefix)]
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def newest(n: int = 1) -> list[Path]:
    return sorted(iter_objects(), key=lambda p: p.stat().st_mtime, reverse=True)[:n]


def materialize(path: Path) -> Path:
    """复制成带扩展名的临时文件，返回该路径（内容不变，md5 一致）。"""
    ext = sniff(path)
    out_dir = Path(tempfile.gettempdir()) / "dsh-pasted"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{path.name[:12]}{ext}"
    if not target.exists() or target.stat().st_size != path.stat().st_size:
        shutil.copyfile(path, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="解析聊天粘贴图片的落盘路径")
    parser.add_argument("target", help="latest | sha256 前缀 | list")
    parser.add_argument("count", nargs="?", type=int, default=10, help="配合 list 使用")
    parser.add_argument("--raw", action="store_true", help="只输出对象原始路径（不加扩展名副本）")
    args = parser.parse_args()

    if args.target == "list":
        for path in newest(max(1, args.count)):
            stat = path.stat()
            stamp = __import__("datetime").datetime.fromtimestamp(stat.st_mtime).strftime("%m-%d %H:%M:%S")
            print(f"{path.name[:12]}  {stamp}  {sniff(path):<5} {stat.st_size / 1024:8.1f} KB")
        return 0

    if args.target == "latest":
        found = newest(1)
    else:
        found = find_by_prefix(args.target)

    if not found:
        print("没找到匹配的附件（检查前缀，或先用 list 看看）", file=sys.stderr)
        return 1

    path = found[0]
    print(str(path if args.raw else materialize(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())