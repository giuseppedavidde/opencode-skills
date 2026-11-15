import { existsSync } from 'node:fs';
import * as path from 'node:path';
import { pathToFileURL } from 'node:url';
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist/legacy/build/pdf.mjs';

export interface PdfTextResult {
  text: string;
  pages: number;
}

export async function extractPdfText(
  data: Buffer | Uint8Array,
  assetsDir: string,
): Promise<PdfTextResult> {
  const workerCandidates = [
    path.join(assetsDir, 'pdf.worker.mjs'),
    path.join(assetsDir, 'legacy', 'build', 'pdf.worker.mjs'),
    path.join(assetsDir, 'legacy', 'build', 'pdf.worker.min.mjs'),
  ];
  const workerPath = workerCandidates.find((candidate) => existsSync(candidate));
  if (!workerPath) {
    throw new Error(`Worker PDF.js mancante in ${assetsDir}.`);
  }
  GlobalWorkerOptions.workerSrc = pathToFileURL(workerPath).href;
  const cMapDir = [
    path.join(assetsDir, 'pdfjs', 'cmaps'),
    path.join(assetsDir, 'cmaps'),
  ].find((candidate) => existsSync(candidate));
  const fontDir = [
    path.join(assetsDir, 'pdfjs', 'standard_fonts'),
    path.join(assetsDir, 'standard_fonts'),
  ].find((candidate) => existsSync(candidate));
  const cMapUrl = cMapDir ? `${cMapDir}${path.sep}` : undefined;
  const standardFontDataUrl = fontDir ? `${fontDir}${path.sep}` : undefined;

  const loadingTask = getDocument({
    data: new Uint8Array(data),
    cMapUrl,
    cMapPacked: true,
    standardFontDataUrl,
    useWorkerFetch: false,
    isEvalSupported: false,
    disableFontFace: true,
    useSystemFonts: false,
  });

  const document = await loadingTask.promise;
  const chunks: string[] = [];
  try {
    for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
      const page = await document.getPage(pageNumber);
      const content = await page.getTextContent();
      const line: string[] = [];
      for (const item of content.items) {
        if ('str' in item && typeof item.str === 'string') {
          line.push(item.str);
          if (item.hasEOL) line.push('\n');
          else line.push(' ');
        }
      }
      chunks.push(line.join('').replace(/[ \t]+/g, ' ').trim());
    }
  } finally {
    await document.destroy();
  }

  return { text: chunks.join('\n\n'), pages: document.numPages };
}
