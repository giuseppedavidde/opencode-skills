import { resolveRange } from '../core/dates.ts';
import type { DateRange, FormState, RangePreset } from '../core/types.ts';
import { RANGE_PRESETS } from '../core/types.ts';

export interface ValidatedForm {
  /** Undefined when the user kept the stored token (input left blank). */
  readonly token: string | undefined;
  readonly queryId: string;
  readonly range: DateRange;
  readonly accountId: string;
}

export interface ValidationSuccess {
  readonly ok: true;
  readonly value: ValidatedForm;
}

export interface ValidationFailure {
  readonly ok: false;
  readonly errors: Readonly<Record<string, string>>;
  readonly message: string;
}

export type ValidationResult = ValidationSuccess | ValidationFailure;

export interface ValidationOptions {
  readonly hasStoredToken: boolean;
  readonly hasStoredQueryId: boolean;
  readonly now?: Date;
}

function isPreset(value: string): value is RangePreset {
  return (RANGE_PRESETS as readonly string[]).includes(value);
}

export function validateForm(form: FormState, options: ValidationOptions): ValidationResult {
  const errors: Record<string, string> = {};
  const token = (form.token ?? '').trim();
  const queryId = (form.queryId ?? '').trim();
  const accountId = (form.accountId ?? '').trim();

  if (token && /\s/.test(token)) {
    errors['token'] = 'The Flex token must not contain spaces or line breaks. Paste it again without whitespace.';
  }
  if (!token && !options.hasStoredToken) {
    errors['token'] = 'A Flex token is required. Create one in Client Portal > Reporting > Flex Queries > Flex Web Service Configuration.';
  }
  if (!queryId && !options.hasStoredQueryId) {
    errors['queryId'] = 'A numeric Query ID is required. Find it next to the query name in Client Portal.';
  } else if (queryId && !/^\d{3,12}$/.test(queryId)) {
    errors['queryId'] = 'The Query ID must contain 3 to 12 digits and nothing else.';
  }
  if (accountId && !/^[A-Za-z0-9.-]{1,32}$/.test(accountId)) {
    errors['accountId'] = 'The account filter accepts letters, digits, dots and dashes only.';
  }
  if (!isPreset(form.preset)) {
    errors['preset'] = `Unknown date range preset "${String(form.preset)}".`;
  }

  const preset = isPreset(form.preset) ? form.preset : 'ytd';
  const range = resolveRange(preset, form.customStart, form.customEnd, options.now ?? new Date());
  if (!range.ok) {
    errors[preset === 'custom' ? 'range' : 'preset'] = range.message;
  }

  const messages = Object.values(errors);
  if (messages.length > 0 || !range.ok) {
    return {
      ok: false,
      errors,
      message: messages.length > 0 ? (messages[0] ?? 'Invalid input.') : 'Invalid date range.'
    };
  }

  return {
    ok: true,
    value: {
      token: token.length > 0 ? token : undefined,
      queryId,
      range: range.range,
      accountId
    }
  };
}
