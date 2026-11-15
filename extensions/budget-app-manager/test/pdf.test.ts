import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { extractPdfText } from '../src/importer/pdf';

const MINIMAL_PDF = 'JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCAzMDAgMTAwXSAvQ29udGVudHMgNCAwIFIgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAvRjEgNSAwIFIgPj4gPj4gPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCA0NiA+PgpzdHJlYW0KQlQgL0YxIDE4IFRmIDIwIDUwIFRkIChIZWxsbyBCdWRnZXQgMTIzKSBUaiBFVAplbmRzdHJlYW0KZW5kb2JqCjUgMCBvYmoKPDwgL1R5cGUgL0ZvbnQgL1N1YnR5cGUgL1R5cGUxIC9CYXNlRm9udCAvSGVsdmV0aWNhID4+CmVuZG9iagp4cmVmCjAgNgowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMDkgMDAwMDAgbiAKMDAwMDAwMDA1OCAwMDAwMCBuIAowMDAwMDAwMTE1IDAwMDAwIG4gCjAwMDAwMDAyNDEgMDAwMDAgbiAKMDAwMDAwMDMzNyAwMDAwMCBuIAp0cmFpbGVyCjw8IC9TaXplIDYgL1Jvb3QgMSAwIFIgPj4Kc3RhcnR4cmVmCjQwNwolJUVPRgo=';

describe('extractPdfText', () => {
  it('extracts text from a PDF with pdfjs-dist', async () => {
    const result = await extractPdfText(
      Buffer.from(MINIMAL_PDF, 'base64'),
      resolve('node_modules/pdfjs-dist'),
    );
    expect(result.pages).toBe(1);
    expect(result.text).toContain('Hello Budget 123');
  });

  it.skipIf(!existsSync(resolve('dist/pdf.worker.mjs')))(
    'extracts text using the packaged dist assets',
    async () => {
      const result = await extractPdfText(
        Buffer.from(MINIMAL_PDF, 'base64'),
        resolve('dist'),
      );
      expect(result.pages).toBe(1);
      expect(result.text).toContain('Hello Budget 123');
    },
  );
});
