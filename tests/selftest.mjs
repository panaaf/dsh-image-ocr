// 自测：用桩 ctx 加载本插件，直接执行它注册的 image_ocr 工具。
// 不接触 DSH 运行时，用来确认「装好依赖之后，工具本身是通的」。
//
//   node tests/selftest.mjs <图片路径 | 粘贴图 sha256 前缀 | latest>
//
// 默认使用本包 .venv 里的解释器（先跑 setup.ps1 / setup.sh）；
// 想用别的解释器就设 DSH_IMAGE_OCR_PYTHON。
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(here);

const own =
  process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
const pythonPath = process.env.DSH_IMAGE_OCR_PYTHON || own;

if (!existsSync(pythonPath)) {
  console.error(`找不到解释器：${pythonPath}\n先跑一次 setup.ps1（Windows）或 setup.sh（macOS/Linux）。`);
  process.exit(2);
}

const { apply } = await import(pathToFileURL(path.join(root, 'index.js')).href);

const registered = {};
const ctx = {
  logger: { info: (msg) => console.log('[logger]', msg) },
  effect: (fn) => fn(),
  tools: {
    register(definition) {
      registered[definition.name] = definition;
      return () => {};
    },
  },
};

apply(ctx, { pythonPath });

const tool = registered['image_ocr'];
if (!tool) {
  console.error('FAIL: image_ocr 未注册');
  process.exit(1);
}

const source = process.argv[2] || 'latest';
console.log(`工具已注册：${Object.keys(registered).join(', ')}；source=${source}`);

const result = await tool.execute({ source }, { signal: null });
console.log(`path=${result.path}\nblocks=${result.blocks}\n---\n${result.text}`);

const ok = result.blocks > 0;
console.log(ok ? '\nPASS' : '\nFAIL: 没有识别到任何文字块');
process.exit(ok ? 0 : 1);