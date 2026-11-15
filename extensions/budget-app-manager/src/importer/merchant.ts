const FILLER_TOKENS = new Set(['dankt', 'fil', 'filiale', 'filiale.', 'fill.']);

const PAYPAL_SERVICE_PATTERNS: RegExp[] = [
  /rate/,
  /\binst\b/,
  /installment/,
  /paga\s+in/,
  /transfer/,
  /top\s*up/,
  /topup/,
  /guthaben/,
  /aufladung/,
  /^in\s+\d/,
];

const STORE_CODE_RE = /^[a-z]{0,2}\d{3,7}$/;

function looksLikePaypalService(rest: string): boolean {
  return PAYPAL_SERVICE_PATTERNS.some((pattern) => pattern.test(rest));
}

function stripStoreSuffix(tokens: string[]): string {
  const cleaned = tokens.filter((token) => !FILLER_TOKENS.has(token));
  while (cleaned.length > 1) {
    const last = cleaned[cleaned.length - 1] ?? '';
    if (/^\d+$/.test(last) || STORE_CODE_RE.test(last)) {
      cleaned.pop();
    } else {
      break;
    }
  }
  return cleaned.join(' ');
}

export function normalizeMerchant(description: string | null | undefined): string {
  if (description === null || description === undefined) return '';
  let value = String(description).toLowerCase().trim();
  if (!value) return '';

  const paypalMatch = /^paypal\s*\*?\s*([\s\S]*)$/.exec(value);
  if (paypalMatch) {
    const rest = (paypalMatch[1] ?? '').trim();
    if (!rest || looksLikePaypalService(rest)) return 'paypal';
    value = rest;
  }

  value = value.replace(/^(sumup|sq)\b\s*\*?\s*/, '');
  value = value.replace(/^(www\.)?amazon\.[a-z0-9.]+\s*/, '');
  value = value.split(/\biban\b/)[0]?.trim() ?? '';
  value = value.replace(/[^\p{L}\p{N}_\s]/gu, ' ');
  value = value.replace(/\s+/g, ' ').trim();
  value = stripStoreSuffix(value.split(' '));
  return value.slice(0, 60).trim();
}

export function merchantKeys(stdName: string, description: string): string[] {
  const keys: string[] = [];
  for (const candidate of [normalizeMerchant(stdName), normalizeMerchant(description)]) {
    if (candidate && !keys.includes(candidate)) {
      keys.push(candidate);
    }
  }
  return keys;
}
