import { build } from 'esbuild';
import { cp, mkdir, rm, access } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const dist = join(root, 'dist');
const watch = process.argv.includes('--watch');

async function copyIfExists(from, to) {
  try {
    await access(from);
    await cp(from, to, { recursive: true });
    return true;
  } catch {
    console.warn(`[build] optional asset missing: ${from}`);
    return false;
  }
}

async function copyAssets() {
  await mkdir(join(dist, 'media'), { recursive: true });
  await copyIfExists(join(root, 'media', 'styles.css'), join(dist, 'media', 'styles.css'));
  await copyIfExists(join(root, 'media', 'merchant_seed.json'), join(dist, 'media', 'merchant_seed.json'));
  await copyIfExists(join(root, 'media', 'icon.png'), join(dist, 'media', 'icon.png'));
  await copyIfExists(join(root, 'media', 'examples'), join(dist, 'media', 'examples'));
  await copyIfExists(join(root, 'node_modules', 'plotly.js-dist-min', 'plotly.min.js'), join(dist, 'media', 'plotly.min.js'));
  await copyIfExists(join(root, 'node_modules', 'sql.js', 'dist', 'sql-wasm.wasm'), join(dist, 'sql-wasm.wasm'));
  await copyIfExists(join(root, 'node_modules', 'pdfjs-dist', 'legacy', 'build', 'pdf.worker.min.mjs'), join(dist, 'pdf.worker.mjs'));
  await copyIfExists(join(root, 'node_modules', 'pdfjs-dist', 'cmaps'), join(dist, 'pdfjs', 'cmaps'));
  await copyIfExists(join(root, 'node_modules', 'pdfjs-dist', 'standard_fonts'), join(dist, 'pdfjs', 'standard_fonts'));
}

async function main() {
  if (!watch) {
    await rm(dist, { recursive: true, force: true });
  }
  await mkdir(dist, { recursive: true });

  const common = {
    bundle: true,
    sourcemap: true,
    logLevel: 'info',
    define: { 'process.env.NODE_ENV': '"production"' },
  };

  const extensionOptions = {
    ...common,
    entryPoints: [join(root, 'src', 'extension.ts')],
    outfile: join(dist, 'extension.js'),
    platform: 'node',
    format: 'cjs',
    target: ['node18'],
    external: ['vscode', 'canvas'],
  };

  const webviewOptions = {
    ...common,
    entryPoints: [join(root, 'src', 'webview-ui', 'main.ts')],
    outfile: join(dist, 'webview.js'),
    platform: 'browser',
    format: 'iife',
    target: ['es2020'],
    external: ['plotly.js-dist-min'],
  };

  if (watch) {
    const { context } = await import('esbuild');
    const ctxA = await context(extensionOptions);
    const ctxB = await context(webviewOptions);
    await copyAssets();
    await Promise.all([ctxA.watch(), ctxB.watch()]);
    console.log('[build] watching...');
    return;
  }

  await Promise.all([build(extensionOptions), build(webviewOptions)]);
  await copyAssets();
  console.log('[build] done');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
