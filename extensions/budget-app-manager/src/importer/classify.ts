import { EXCLUDED_CATEGORY, type ClassifyMode } from '../types';

export const TR_TYPE_MAP: Record<string, string> = {
  BUY: 'Investimenti',
  TRANSFER_INSTANT_OUTBOUND: EXCLUDED_CATEGORY,
  TRANSFER_INSTANT_INBOUND: EXCLUDED_CATEGORY,
  FREE_RECEIPT: EXCLUDED_CATEGORY,
  BENEFITS_SAVEBACK: 'Reddito aggiuntivo',
  INTEREST_PAYMENT: 'Reddito aggiuntivo',
};

export const GERMAN_CATEGORY_MAP: Record<string, string> = {
  Lebensmittel: 'Alimentari',
  Bargeld: 'Bancomat',
  Versicherung: 'Immobili (affitto, mutuo, tasse, assicurazione)',
  'Wohnen & Haushalt': 'Immobili (affitto, mutuo, tasse, assicurazione)',
  Gesundheit: 'Medicinali',
  Einkünfte: 'Stipendio',
  'Kommunikation & Medien': 'PayPal + Abbonamenti',
};

const FUEL_TOKENS = ['JET', 'DISKONT', 'TANKSTELLE'];

const RESTAURANT_TOKENS = [
  'restaurant',
  'ristorante',
  'trattoria',
  'osteria',
  'pizzeria',
  'bar',
  'cafe',
  'caff',
  'coffee',
  'bistro',
  'gelateria',
  'enoteca',
  'sushi',
  'wurstel',
  'ditsch',
  'stroeck',
  'mcdonald',
  'kfc',
  'piadineria',
  'salud',
  'racers',
  'mcmullens',
  'yarra',
  'meschik',
  'dampfer',
  'terrazza',
  'egglab',
  'hungry',
  'starbucks',
  'bakery',
  'pastry',
  'konditorei',
];

export function mapTradeType(stdType: string | null | undefined): string | null {
  const value = String(stdType ?? '').trim().toUpperCase();
  return TR_TYPE_MAP[value] ?? null;
}

export function mapGermanCategory(
  germanCategory: string | null | undefined,
  description: string | null | undefined,
): string | null {
  const category = String(germanCategory ?? '').trim();
  if (category === 'Mobilität') {
    const upper = String(description ?? '').toUpperCase();
    return FUEL_TOKENS.some((token) => upper.includes(token)) ? 'Carburante' : 'Trasporti';
  }
  if (category === 'Freizeit & Genuss') {
    const lower = String(description ?? '').toLowerCase();
    return RESTAURANT_TOKENS.some((token) => lower.includes(token))
      ? 'Cene, Pranzo'
      : 'Viaggi, Divertimento';
  }
  return GERMAN_CATEGORY_MAP[category] ?? null;
}

export function deterministicCategory(
  stdType: string | null | undefined,
  stdCategory: string | null | undefined,
  description: string | null | undefined,
): string | null {
  return mapTradeType(stdType) ?? mapGermanCategory(stdCategory, description);
}

export function assertClassifyMode(mode: string): asserts mode is ClassifyMode {
  if (mode !== 'hybrid' && mode !== 'llm_only') {
    throw new Error(`classify_mode non valido: ${JSON.stringify(mode)}. Valori ammessi: hybrid, llm_only.`);
  }
}

export function cleanAmount(value: unknown): number {
  if (value === null || value === undefined || value === '') return 0;
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  let text = String(value).trim();
  if (!text) return 0;
  text = text.replace(/[€$\s]/g, '');
  const lastComma = text.lastIndexOf(',');
  const lastDot = text.lastIndexOf('.');
  if (lastComma >= 0 && lastDot >= 0) {
    if (lastComma > lastDot) {
      text = text.replace(/\./g, '').replace(',', '.');
    } else {
      text = text.replace(/,/g, '');
    }
  } else if (lastComma >= 0) {
    const decimals = text.length - lastComma - 1;
    text = decimals === 2 ? text.replace(',', '.') : text.replace(/,/g, '');
  }
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : 0;
}

export interface BatchItem {
  id: number;
  description: string;
  amount: number | string;
  old_category: string;
}

export function buildLetterIndex(targetCategories: readonly string[]): Record<string, string> | null {
  if (targetCategories.length === 0 || targetCategories.length > 26) return null;
  const index: Record<string, string> = {};
  targetCategories.forEach((category, i) => {
    index[String.fromCharCode(65 + i)] = category;
  });
  return index;
}

export function buildLetterPrompt(
  batch: readonly BatchItem[],
  letterIndex: Record<string, string>,
): string {
  const lettersBlock = Object.entries(letterIndex)
    .map(([letter, category]) => `${letter}=${category}`)
    .join('\n');
  return `
        You are an expert financial assistant.
        Your task is to MAP bank transactions to valid budget categories.

        CATEGORY_LETTERS (answer with the single LETTER, not the full name):
        ${lettersBlock}

        RULES:
        1. "Freizeit & Genuss" is generic. You MUST be specific based on the description:
        - Restaurants, Bars, Food delivery -> 'Cene, Pranzo'
        - Pharmacies (Apotheke, DM often), Doctors -> 'Medicinali'
        - Trains, Buses, Taxi, Uber -> 'Trasporti'
        - Flights, Hotels, Airbnb, Cinema, Events -> 'Viaggi, Divertimento'
        - Gas stations (Tankstelle) -> 'Carburante'
        - Subscriptions (Spotify, Netflix) -> 'PayPal + Abbonamenti'
        2. "Lebensmittel" (Groceries) or Supermarkets -> 'Alimentari'.
        3. "Mobilität" usually maps to 'Carburante' or 'Trasporti'.
        4. "Miete" (Rent) / Insurance -> 'Immobili (affitto, mutuo, tasse, assicurazione)'.
        5. Salary/Wages -> 'Stipendio'.
        6. Incoming transfers -> 'Reddito aggiuntivo' (unless typical salary).

        TRANSACTIONS:
        ${JSON.stringify(batch)}

        Return ONLY a JSON object mapping each transaction id to its single
        category LETTER, e.g. {"12":"A","13":"C"}.
        `;
}

export function buildJsonPrompt(
  batch: readonly BatchItem[],
  targetCategories: readonly string[],
): string {
  return `
        Sei un assistente finanziario esperto.
        Assegna a ogni transazione UNA categoria valida dall'elenco:
        ${targetCategories.map((category) => `- ${category}`).join('\n')}

        TRANSACTIONS:
        ${JSON.stringify(batch)}

        Rispondi SOLO con un oggetto JSON che mappa ogni id alla categoria,
        per esempio {"12":"Alimentari","13":"Escluso"}.
        `;
}

function stripFences(text: string): string {
  let cleaned = text.trim();
  if (cleaned.includes('```json')) {
    cleaned = cleaned.split('```json')[1]?.split('```')[0] ?? cleaned;
  } else if (cleaned.includes('```')) {
    const parts = cleaned.split('```');
    if (parts.length >= 2) cleaned = parts[1] ?? cleaned;
  }
  return cleaned.trim();
}

export function parseLetterMappings(
  text: string,
  batch: readonly BatchItem[],
  letterIndex: Record<string, string> | null,
): Record<number, string> {
  if (!text || !letterIndex) return {};
  const validIds = new Set(batch.map((item) => Number(item.id)));
  const upperIndex: Record<string, string> = {};
  for (const [letter, category] of Object.entries(letterIndex)) {
    upperIndex[letter.toUpperCase()] = category;
  }
  const letterToCategory = (raw: unknown): string | null => {
    if (raw === null || raw === undefined) return null;
    const match = /[A-Za-z]/.exec(String(raw));
    if (!match) return null;
    return upperIndex[match[0].toUpperCase()] ?? null;
  };

  let cleaned = stripFences(text);
  const result: Record<number, string> = {};
  let candidate = cleaned;
  if (!candidate.startsWith('{')) {
    const start = candidate.indexOf('{');
    const end = candidate.lastIndexOf('}');
    if (start !== -1 && end > start) candidate = candidate.slice(start, end + 1);
  }
  if (candidate.startsWith('{')) {
    try {
      const parsed = JSON.parse(candidate) as unknown;
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
          const id = Number(String(key).trim().replace(/^["']|["']$/g, ''));
          if (!Number.isInteger(id) || !validIds.has(id)) continue;
          const category = letterToCategory(value);
          if (category) result[id] = category;
        }
      }
    } catch {
      // fall through to line parsing
    }
  }

  if (Object.keys(result).length === 0) {
    const regex = /["']?(\d+)["']?\s*[:=]\s*["']?([A-Za-z])/g;
    let match: RegExpExecArray | null;
    while ((match = regex.exec(cleaned)) !== null) {
      const id = Number(match[1]);
      if (!validIds.has(id)) continue;
      const category = upperIndex[(match[2] ?? '').toUpperCase()];
      if (category) result[id] = category;
    }
  }
  return result;
}

export function parseJsonMappings(
  text: string,
  batch: readonly BatchItem[],
  validCategories: readonly string[],
): Record<number, string> {
  const validIds = new Set(batch.map((item) => Number(item.id)));
  const valid = new Set(validCategories);
  const result: Record<number, string> = {};
  let cleaned = stripFences(text);
  const arrayStart = cleaned.indexOf('[');
  const objectStart = cleaned.indexOf('{');
  const start = arrayStart >= 0 && (objectStart < 0 || arrayStart < objectStart) ? arrayStart : objectStart;
  if (start >= 0) {
    const end = cleaned.lastIndexOf(arrayStart >= 0 && start === arrayStart ? ']' : '}');
    if (end > start) cleaned = cleaned.slice(start, end + 1);
  }
  try {
    const parsed = JSON.parse(cleaned) as unknown;
    if (Array.isArray(parsed)) {
      for (const item of parsed) {
        if (!item || typeof item !== 'object') continue;
        const record = item as Record<string, unknown>;
        const id = Number(record.id);
        const category = String(record.new_category ?? record.category ?? '');
        if (validIds.has(id) && valid.has(category)) result[id] = category;
      }
    } else if (parsed && typeof parsed === 'object') {
      for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
        const id = Number(key);
        const category = typeof value === 'string' ? value : '';
        if (validIds.has(id) && valid.has(category)) result[id] = category;
      }
    }
  } catch {
    return {};
  }
  return result;
}
