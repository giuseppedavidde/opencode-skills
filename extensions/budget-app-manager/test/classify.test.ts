import { describe, expect, it } from 'vitest';
import {
  buildJsonPrompt,
  buildLetterIndex,
  buildLetterPrompt,
  cleanAmount,
  deterministicCategory,
  mapGermanCategory,
  mapTradeType,
  parseJsonMappings,
  parseLetterMappings,
  type BatchItem,
} from '../src/importer/classify';

describe('deterministic rules', () => {
  it('maps Trade Republic transaction types', () => {
    expect(mapTradeType('BUY')).toBe('Investimenti');
    expect(mapTradeType('transfer_instant_outbound')).toBe('Escluso');
    expect(mapTradeType('INTEREST_PAYMENT')).toBe('Reddito aggiuntivo');
    expect(mapTradeType('UNKNOWN')).toBeNull();
  });

  it('maps German categories with fuel/restaurant refinement', () => {
    expect(mapGermanCategory('Lebensmittel', '')).toBe('Alimentari');
    expect(mapGermanCategory('Mobilität', 'JET Tankstelle')).toBe('Carburante');
    expect(mapGermanCategory('Mobilität', 'ÖBB Ticket')).toBe('Trasporti');
    expect(mapGermanCategory('Freizeit & Genuss', 'Ristorante Da Mario')).toBe('Cene, Pranzo');
    expect(mapGermanCategory('Freizeit & Genuss', 'Cinema')).toBe('Viaggi, Divertimento');
    expect(mapGermanCategory('Unkategorisiert', '')).toBeNull();
  });

  it('prioritizes structural type over category', () => {
    expect(deterministicCategory('BUY', 'Lebensmittel', '')).toBe('Investimenti');
    expect(deterministicCategory('', 'Lebensmittel', '')).toBe('Alimentari');
  });
});

describe('cleanAmount', () => {
  it('parses European and plain formats', () => {
    expect(cleanAmount('1.234,56')).toBe(1234.56);
    expect(cleanAmount('-12,50')).toBe(-12.5);
    expect(cleanAmount('1,234.56')).toBe(1234.56);
    expect(cleanAmount('2500')).toBe(2500);
    expect(cleanAmount('€ 99,90')).toBe(99.9);
    expect(cleanAmount(null)).toBe(0);
    expect(cleanAmount('abc')).toBe(0);
  });
});

const batch: BatchItem[] = [
  { id: 12, description: 'BILLA', amount: -20, old_category: 'Lebensmittel' },
  { id: 13, description: 'Netflix', amount: -12, old_category: 'Sonstiges' },
];

describe('letter schema', () => {
  it('builds a letter index and prompt', () => {
    const index = buildLetterIndex(['Alimentari', 'PayPal + Abbonamenti']);
    expect(index).toEqual({ A: 'Alimentari', B: 'PayPal + Abbonamenti' });
    expect(buildLetterPrompt(batch, index as Record<string, string>)).toContain('A=Alimentari');
  });

  it('returns null when categories cannot be encoded', () => {
    expect(buildLetterIndex([])).toBeNull();
    expect(buildLetterIndex(Array.from({ length: 27 }, (_, i) => `C${i}`))).toBeNull();
  });

  it('parses JSON and line based letter mappings', () => {
    const index = { A: 'Alimentari', B: 'PayPal + Abbonamenti' };
    expect(parseLetterMappings('{"12":"A","13":"B"}', batch, index)).toEqual({
      12: 'Alimentari',
      13: 'PayPal + Abbonamenti',
    });
    expect(parseLetterMappings('```json\n{"12":"A"}\n```', batch, index)).toEqual({
      12: 'Alimentari',
    });
    expect(parseLetterMappings('12: A\n13 = B', batch, index)).toEqual({
      12: 'Alimentari',
      13: 'PayPal + Abbonamenti',
    });
    expect(parseLetterMappings('{"99":"A","12":"Z"}', batch, index)).toEqual({});
  });
});

describe('verbose JSON fallback', () => {
  it('parses arrays and id maps', () => {
    const categories = ['Alimentari', 'PayPal + Abbonamenti'];
    expect(
      parseJsonMappings(
        '[{"id":12,"new_category":"Alimentari"},{"id":13,"new_category":"Sconosciuta"}]',
        batch,
        categories,
      ),
    ).toEqual({ 12: 'Alimentari' });
    expect(
      parseJsonMappings('{"12":"Alimentari","13":"PayPal + Abbonamenti"}', batch, categories),
    ).toEqual({ 12: 'Alimentari', 13: 'PayPal + Abbonamenti' });
    expect(buildJsonPrompt(batch, categories)).toContain('Alimentari');
  });
});
