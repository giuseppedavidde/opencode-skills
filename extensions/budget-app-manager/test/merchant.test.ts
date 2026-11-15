import { describe, expect, it } from 'vitest';
import { merchantKeys, normalizeMerchant } from '../src/importer/merchant';

describe('normalizeMerchant', () => {
  it('strips store and branch suffixes', () => {
    expect(normalizeMerchant('dm fil a055')).toBe('dm');
    expect(normalizeMerchant('mcdonalds 42')).toBe('mcdonalds');
    expect(normalizeMerchant('INTERSPAR DANKT 8820')).toBe('interspar');
    expect(normalizeMerchant('BILLA DANKT 0007950')).toBe('billa');
  });

  it('keeps standalone codes', () => {
    expect(normalizeMerchant('cm103')).toBe('cm103');
    expect(normalizeMerchant('1859')).toBe('1859');
  });

  it('reduces PayPal to the merchant or to paypal for services', () => {
    expect(normalizeMerchant('PAYPAL *Paga in 3 rate')).toBe('paypal');
    expect(normalizeMerchant('PAYPAL *STEAM GAMES')).toBe('steam games');
    expect(normalizeMerchant('PayPal')).toBe('paypal');
  });

  it('removes payment processors and Amazon prefixes', () => {
    expect(normalizeMerchant('SumUp *Caffetteria Roma')).toBe('caffetteria roma');
    expect(normalizeMerchant('www.amazon.de AMZN Mktp')).toBe('amzn mktp');
  });

  it('truncates SEPA descriptions at IBAN', () => {
    expect(normalizeMerchant('Katja Stefanie Davidde IBAN: AT27 1234')).toBe(
      'katja stefanie davidde',
    );
  });

  it('normalizes punctuation and case', () => {
    expect(normalizeMerchant('  CAFFÈ   ROMA-01! ')).toBe('caffè roma');
    expect(normalizeMerchant('')).toBe('');
    expect(normalizeMerchant(null)).toBe('');
  });
});

describe('merchantKeys', () => {
  it('returns cleaned name first and deduplicates', () => {
    const keys = merchantKeys('HOTEL TRIESTE', 'IT 24,00 POS ... HOTEL TRIESTE');
    expect(keys[0]).toBe('hotel trieste');
    expect(keys).toContain('it 24 00 pos hotel trieste');
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('returns an empty array when both are empty', () => {
    expect(merchantKeys('', '   ')).toEqual([]);
  });
});
