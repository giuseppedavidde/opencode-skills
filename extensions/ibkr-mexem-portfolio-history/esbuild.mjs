import esbuild from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const production = process.argv.includes('--production');
const watchMode = process.argv.includes('--watch');

const outdir = path.join(root, 'dist');
fs.mkdirSync(outdir, { recursive: true });
fs.mkdirSync(path.join(root, 'media'), { recursive: true });

const common = {
  bundle: true,
  minify: production,
  sourcemap: production ? false : 'inline',
  logLevel: 'info',
  legalComments: 'none'
};

const extensionConfig = {
  ...common,
  entryPoints: [path.join(root, 'src', 'extension.ts')],
  outfile: path.join(outdir, 'extension.cjs'),
  platform: 'node',
  format: 'cjs',
  target: 'node20',
  external: ['vscode']
};

const webviewConfig = {
  ...common,
  entryPoints: [path.join(root, 'src', 'panel', 'webview', 'main.ts')],
  outfile: path.join(root, 'media', 'webview.js'),
  platform: 'browser',
  format: 'iife',
  target: 'es2020'
};

const chatWebviewConfig = {
  ...common,
  entryPoints: [path.join(root, 'src', 'chat', 'webview', 'main.ts')],
  outfile: path.join(root, 'media', 'chat.js'),
  platform: 'browser',
  format: 'iife',
  target: 'es2020'
};

async function build(config) {
  if (watchMode) {
    const ctx = await esbuild.context(config);
    await ctx.watch();
    console.log(`[esbuild] watching ${path.basename(config.outfile)}`);
    return;
  }
  await esbuild.build(config);
}

try {
  await Promise.all([build(extensionConfig), build(webviewConfig), build(chatWebviewConfig)]);
} catch (error) {
  console.error('[esbuild] build failed', error);
  process.exit(1);
}
