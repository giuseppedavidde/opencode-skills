import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { BudgetDb } from '../src/db';
import { extractPdfText } from '../src/importer/pdf';
import { processBankFile } from '../src/importer/bankImporter';
import { decodeBuffer } from '../src/importer/csv';
import type { MonthlyRow } from '../src/types';

function buildMinimalPdf(text: string): Buffer {
  const content = `BT /F1 18 Tf 20 50 Td (${text}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 100] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${Buffer.byteLength(content)} >>\nstream\n${content}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  const chunks: Buffer[] = [Buffer.from('%PDF-1.4\n', 'utf8')];
  const offsets: number[] = [];
  let length = chunks[0]?.length ?? 0;
  objects.forEach((object, index) => {
    offsets.push(length);
    const chunk = Buffer.from(`${index + 1} 0 obj\n${object}\nendobj\n`, 'utf8');
    chunks.push(chunk);
    length += chunk.length;
  });
  const xrefOffset = length;
  let xref = `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) xref += `${String(offset).padStart(10, '0')} 00000 n \n`;
  xref += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
  chunks.push(Buffer.from(xref, 'utf8'));
  return Buffer.concat(chunks);
}

function emptyRow(): MonthlyRow {
  return {
    Year: 2025,
    MonthNum: 1,
    Month: 'January',
    Stipendio: 3000,
    'Reddito aggiuntivo': 0,
    Alimentari: 200,
    Bancomat: 0,
    Carburante: 0,
    'Cene, Pranzo': 0,
    'Immobili (affitto, mutuo, tasse, assicurazione)': 0,
    Investimenti: 0,
    Medicinali: 0,
    'PayPal + Abbonamenti': 0,
    'Spese Straordinarie': 0,
    'Acquisto Auto': 0,
    Trasporti: 0,
    'Viaggi, Divertimento': 0,
  };
}

async function main(): Promise<void> {
  const dir = mkdtempSync(join(tmpdir(), 'budget-smoke-'));
  try {
    const seedPath = join(dir, 'seed.json');
    writeFileSync(
      seedPath,
      JSON.stringify([{ merchant: 'BILLA', category: 'Alimentari', confidence: 0.9 }]),
    );
    const db = await BudgetDb.open({
      dbPath: join(dir, 'budget.db'),
      seedPath,
      wasmPath: resolve('dist/sql-wasm.wasm'),
    });
    db.saveData([emptyRow()]);
    const rows = db.loadData();
    if (rows.length !== 1 || rows[0]?.Stipendio !== 3000) {
      throw new Error(`DB smoke test failed: ${JSON.stringify(rows)}`);
    }
    if (db.getMerchantCount() !== 1) throw new Error('Merchant seed failed');
    db.close();

    const decoded = decodeBuffer(Buffer.from([0x42, 0x49, 0x4c, 0x4c, 0x41, 0x20, 0x80]));
    if (decoded !== 'BILLA €') throw new Error(`cp1252 decode failed: ${decoded}`);

    const pdf = buildMinimalPdf('Hello Budget 123');
    const extracted = await extractPdfText(pdf, resolve('dist'));
    if (!extracted.text.includes('Hello Budget 123')) {
      throw new Error(`PDF smoke test failed: ${JSON.stringify(extracted.text)}`);
    }

    const imported = await processBankFile(pdf, 'statement.pdf', {
      targetCategories: ['Alimentari', 'Trasporti'],
      incomeColumns: ['Stipendio'],
      merchantMap: {},
      classifyMode: 'llm_only',
      llm: {
        categorize: async (prompt) =>
          prompt.includes('BANK STATEMENT TEXT')
            ? '[{"Buchungsdatum":"15.01.2025","Umsatztext":"BILLA","Betrag":"-25,50"}]'
            : '{"0":"A"}',
      },
      pdfAssetsDir: resolve('dist'),
      sourceName: 'statement.pdf',
    });
    if (imported.rows.length !== 1 || imported.rows[0]?.newCategory !== 'Alimentari') {
      throw new Error(`PDF import pipeline failed: ${JSON.stringify(imported.rows)}`);
    }
    console.log(
      `smoke ok: db rows=${rows.length}, pdf pages=${extracted.pages}, imported=${imported.rows.length}`,
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
