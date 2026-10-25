/**
 * dsh-image-ocr — 给纯文本模型装一只「读图」的眼睛。
 *
 * 一个工具，一件事：把图片变成文字。识别走**完全离线**的 OCR
 * （RapidOCR / PaddleOCR PP-OCRv6 + ONNXRuntime CPU），不联网、不需要
 * API Key、不需要任何模型服务器。模型文件由 `rapidocr` wheel 自带。
 *
 * 典型场景：DSH 里粘贴的截图对不支持图片的模型会变成一行
 * `[image omitted because this model accepts text only; attachment sha256:xxxxxxxx]`，
 * 把这个 8 位前缀（或 "latest"、或图片文件路径）交给本工具即可拿到图上文字。
 *
 * @module dsh-image-ocr
 */

import { spawn } from 'node:child_process';
import { appendFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export const name = 'dsh-image-ocr';
export const inject = ['tools'];

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url));
const PYTHON_DIR = path.join(PLUGIN_DIR, 'python');

/** 诊断日志：仅在 config.debug 或 DSH_IMAGE_OCR_DEBUG=1 时写（默认零落盘）。 */
const DIAG = path.join(process.env.TEMP || '.', 'dsh-image-ocr.log');

function makeDiag(enabled) {
  return (line) => {
    if (!enabled) return;
    try {
      appendFileSync(DIAG, `${new Date().toISOString()} ${line}\n`);
    } catch {
      /* 诊断写不了就算了，不能影响插件本身 */
    }
  };
}

/**
 * 解释器解析顺序：行 config `pythonPath` → 环境变量 `DSH_IMAGE_OCR_PYTHON` →
 * 本包 `.venv`（用 setup.ps1 / setup.sh 就地重建）→ PATH 上的 `python`。
 */
function resolvePython(config) {
  const own = path.join(PLUGIN_DIR, '.venv', 'Scripts', 'python.exe');
  const ownPosix = path.join(PLUGIN_DIR, '.venv', 'bin', 'python');
  const candidates = [config.pythonPath, process.env.DSH_IMAGE_OCR_PYTHON, own, ownPosix];
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim() && existsSync(candidate)) return candidate;
  }
  return 'python';
}

/** 跑一次自带脚本，返回 stdout；失败时抛出带 stderr 摘要的错误。 */
function runPython(script, args, { pythonPath, timeoutMs = 180000 }) {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonPath, [path.join(PYTHON_DIR, script), ...args], {
      cwd: PYTHON_DIR,
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error(`识别超时（${timeoutMs} ms），图片可能过大`));
    }, timeoutMs);
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      stdout += chunk;
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk;
    });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(
        new Error(
          `无法启动 Python（${pythonPath}）：${error.message}。` +
            `请在插件目录执行 setup.ps1（Windows）或 setup.sh（macOS/Linux）安装依赖。`,
        ),
      );
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code === 0) resolve(stdout);
      else reject(new Error(`识图脚本退出码 ${code}：${(stderr || stdout).trim().slice(-600) || '无输出'}`));
    });
  });
}

export function apply(ctx, config = {}) {
  const diag = makeDiag(config.debug === true || process.env.DSH_IMAGE_OCR_DEBUG === '1');
  const pythonPath = resolvePython(config);
  const modelDir = config.modelDir || process.env.DSH_OCR_MODEL_DIR || '';
  diag(`apply 进入；python=${pythonPath}; modelDir=${modelDir || '(自动)'}`);
  ctx.logger?.info?.(`dsh-image-ocr 就绪：python=${pythonPath}`);

  ctx.effect(() => {
    const dispose = ctx.tools.register({
      name: 'image_ocr',
      description:
        '读取一张图片里的文字（离线 OCR，不需要联网，也不需要 API Key）。当用户粘贴了图片时，' +
        '你会看到一行 `[image omitted because this model accepts text only; attachment sha256:xxxxxxxx]`，' +
        '把其中的 8 位 sha256 前缀作为 source 传进来即可；也可以传 "latest" 读最近一张粘贴的图，' +
        '或直接传图片文件路径。返回按阅读顺序整理的逐行文字；加 layout=true 还会给出每行的像素坐标。',
      parameters: {
        type: 'object',
        additionalProperties: false,
        properties: {
          source: {
            type: 'string',
            description: '图片文件路径，或粘贴图片的 sha256 前缀（至少 4 位十六进制），或 "latest"。',
          },
          layout: {
            type: 'boolean',
            description: '是否附带每行的像素包围盒（找按钮/控件坐标时有用）。默认 false。',
          },
        },
        required: ['source'],
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            path: { type: 'string' },
            text: { type: 'string' },
            blocks: { type: 'integer' },
            truncated: { type: 'boolean' },
          },
          required: ['path', 'text', 'truncated'],
        },
        render: (_args, value) => [
          {
            type: 'text',
            text:
              `图片：${value.path}\n` +
              `文字块：${value.blocks ?? '?'} 个\n\n` +
              (value.text || '（没有识别到文字）'),
          },
        ],
        presentationMeta: (_args, value) => ({ path: value.path, blocks: value.blocks }),
      },
      timeoutMs: 180000,
      isConcurrencySafe: () => true,
      async execute(args, exec) {
        const source = String(args?.source ?? '').trim();
        if (!source) throw new Error('source 不能为空：需要图片路径、sha256 前缀或 "latest"');
        const argv = [source, '--json'];
        if (args?.layout) argv.push('--layout');
        if (modelDir) argv.push('--model-dir', modelDir);
        const stdout = await runPython('image_read.py', argv, { pythonPath });
        let payload;
        try {
          payload = JSON.parse(stdout);
        } catch {
          throw new Error(`识图结果不是合法 JSON：${stdout.slice(0, 300)}`);
        }
        exec.signal?.throwIfAborted?.();
        diag(`image_ocr 完成：${payload.path}`);
        return {
          path: payload.path,
          text: payload.text ?? '',
          blocks: Array.isArray(payload.blocks) ? payload.blocks.length : 0,
          truncated: false,
        };
      },
      presentCall: (args) => ({
        card: 'generic',
        title: `读取图片 ${args?.source ?? ''}`,
        kind: 'read',
      }),
      presentResult: (_args, result) => ({
        card: 'generic',
        title: `识图：${result?.meta?.blocks ?? ''} 个文字块`.trim(),
      }),
    });
    diag('image_ocr 工具注册成功');
    return dispose;
  });
}