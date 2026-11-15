export const BUDGET_COLUMNS = [
  'Year',
  'MonthNum',
  'Month',
  'Stipendio',
  'Reddito aggiuntivo',
  'Alimentari',
  'Bancomat',
  'Carburante',
  'Cene, Pranzo',
  'Immobili (affitto, mutuo, tasse, assicurazione)',
  'Investimenti',
  'Medicinali',
  'PayPal + Abbonamenti',
  'Spese Straordinarie',
  'Acquisto Auto',
  'Trasporti',
  'Viaggi, Divertimento',
] as const;

export type BudgetColumn = (typeof BUDGET_COLUMNS)[number];
export type MoneyColumn = Exclude<BudgetColumn, 'Year' | 'MonthNum' | 'Month'>;

export const INCOME_COLUMNS = ['Stipendio', 'Reddito aggiuntivo'] as const;
export type IncomeColumn = (typeof INCOME_COLUMNS)[number];

export const CAPEX_COLUMNS = ['Acquisto Auto'] as const;
export type CapexColumn = (typeof CAPEX_COLUMNS)[number];

export const EXPENSE_COLUMNS = [
  'Alimentari',
  'Bancomat',
  'Carburante',
  'Cene, Pranzo',
  'Immobili (affitto, mutuo, tasse, assicurazione)',
  'Investimenti',
  'Medicinali',
  'PayPal + Abbonamenti',
  'Spese Straordinarie',
  'Trasporti',
  'Viaggi, Divertimento',
] as const;
export type ExpenseCategory = (typeof EXPENSE_COLUMNS)[number];

export const MONTHS_EN = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const;

export const MONTHS_IT = [
  'Gennaio',
  'Febbraio',
  'Marzo',
  'Aprile',
  'Maggio',
  'Giugno',
  'Luglio',
  'Agosto',
  'Settembre',
  'Ottobre',
  'Novembre',
  'Dicembre',
] as const;

export interface MonthlyRow {
  Year: number;
  MonthNum: number;
  Month: string;
  Stipendio: number;
  'Reddito aggiuntivo': number;
  Alimentari: number;
  Bancomat: number;
  Carburante: number;
  'Cene, Pranzo': number;
  'Immobili (affitto, mutuo, tasse, assicurazione)': number;
  Investimenti: number;
  Medicinali: number;
  'PayPal + Abbonamenti': number;
  'Spese Straordinarie': number;
  'Acquisto Auto': number;
  Trasporti: number;
  'Viaggi, Divertimento': number;
}

export type MonthlyKey = { Year: number; MonthNum: number };

export interface TransactionRecord {
  id?: number;
  date: string;
  description: string;
  amount: number;
  category: string;
  source: string;
  imported_at?: string;
  month_ref: string;
}

export interface MerchantEntry {
  merchant: string;
  category: string;
  source: string;
  confidence: number;
  times_seen: number;
  first_seen?: string | null;
  last_seen?: string | null;
}

export interface DbInfo {
  dbPath: string;
  dbSizeKb: number;
  rowCount: number;
  lastBackupTime: string | null;
  transactionCount: number;
  merchantCount: number;
}

export type TimeWindow = 3 | 6 | 12 | 24 | 'All';
export type ClassifyMode = 'hybrid' | 'llm_only';

export type ProviderType =
  | 'opencode'
  | 'gemini'
  | 'groq'
  | 'ollama'
  | 'openrouter'
  | 'puter'
  | 'llamacpp';

export const PROVIDER_TYPES: ProviderType[] = [
  'opencode',
  'gemini',
  'groq',
  'ollama',
  'openrouter',
  'puter',
  'llamacpp',
];

export const PROVIDER_LABELS: Record<ProviderType, string> = {
  opencode: '🔵 OpenCode Go (CLI, low cost)',
  gemini: '☁️ Gemini (Cloud)',
  groq: '⚡ Groq (LPU Cloud)',
  ollama: '🖥️ Ollama (Local)',
  openrouter: '🌐 OpenRouter (Unified API)',
  puter: '🧠 Puter (Free / Claude)',
  llamacpp: '🦙 LlamaCpp (TurboQuant, local)',
};

export const PROVIDER_ENV_KEY: Record<ProviderType, string> = {
  opencode: 'OPENCODE_GO_API_KEY',
  gemini: 'GOOGLE_API_KEY',
  groq: 'GROQ_API_KEY',
  ollama: 'OLLAMA_API_KEY',
  openrouter: 'OPENROUTER_API_KEY',
  puter: 'PUTER_API_KEY',
  llamacpp: 'LLAMACPP_API_KEY',
};

export const PROVIDER_MODELS: Record<ProviderType, string[]> = {
  opencode: [
    'deepseek-v4-pro',
    'deepseek-v4.1-flash',
    'glm-5.2',
    'glm-5.3',
    'glm-5.3-flash',
    'kimi-k2.7-code',
    'kimi-k3',
    'kimi-k3.1-pro',
    'minimax-m3',
    'minimax-m3.1-flash',
    'mimo-v2.6-pro',
    'mimo-v2.6-flash',
    'qwen3.7-plus',
    'qwen3.8-max',
    'qwen3.8-flash',
    'grok-4.7',
    'gemini-4-argon',
    'gpt-5.6-luna',
    'gpt-6-luna',
    'claude-haiku-5-5',
    'hy3',
    'hy4',
    'hy4-preview',
    'longcat-2.0',
    'longcat-2.5-free',
    'step-5-preview',
    'beam-free',
    'muse-spark-1.2-contributor',
    'muse-spark-1.3-contributor',
    'iceman-contributor-free',
  ],
  gemini: [
    'gemini-3-pro-preview',
    'gemini-3-flash-preview',
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite',
    'gemini-2.5-pro',
    'gemini-1.5-flash',
    'gemini-1.5-pro',
  ],
  groq: [
    'moonshotai/kimi-k2-instruct',
    'llama-3.3-70b-versatile',
    'llama-3.1-8b-instant',
    'llama3-70b-8192',
    'llama3-8b-8192',
    'mixtral-8x7b-32768',
    'gemma2-9b-it',
  ],
  ollama: ['llama3.2', 'llama3.1', 'qwen2.5', 'mistral', 'gemma2'],
  openrouter: [
    'anthropic/claude-sonnet-4',
    'google/gemini-2.5-flash',
    'openai/gpt-4o-mini',
    'meta-llama/llama-3.3-70b-instruct',
  ],
  llamacpp: ['local-model'],
  puter: [
    'claude-sonnet-4-5',
    'claude-3-7-sonnet',
    'claude-3-5-sonnet',
    'claude-3-haiku',
    'gemini-2.5-flash',
    'gemini-1.5-pro',
  ],
};

export interface AiConfig {
  provider: ProviderType;
  model: string;
}

export interface AiConfigState extends AiConfig {
  keySet: boolean;
  models: string[];
  envKeyAvailable: boolean;
}

export interface CloudConfig {
  enabled: boolean;
  repo: string;
  branch: string;
  path: string;
  csvPath: string;
  tokenSet: boolean;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface DistributionStats {
  mean: number;
  median: number;
  std: number;
  min: number;
  max: number;
  p25: number;
  p75: number;
  minMonth: string;
  maxMonth: string;
}

export interface SavingsStats {
  mean: number;
  median: number;
  std: number;
  cv: number | null;
  positiveMonthsPct: number;
  bestMonth: string;
  bestValue: number;
  worstMonth: string;
  worstValue: number;
}

export interface PatrimonioStats {
  initial: number;
  final: number;
  cagr: number | null;
  cagrNote: string;
  yoyGrowthPct: number | null;
  avgYearlyAccumulation: number;
}

export interface StatsResult {
  nMonths: number;
  income: DistributionStats;
  expense: DistributionStats;
  savings: SavingsStats;
  savingsRate: DistributionStats;
  patrimonio: PatrimonioStats;
  runwayMonths: number | null;
}

export interface ForecastPoint {
  date: string;
  net: number;
  lower: number;
  upper: number;
}

export interface ForecastResult {
  method: string;
  ciLevel: number;
  points: ForecastPoint[];
}

export interface ImportReviewRow {
  index: number;
  date: string;
  description: string;
  amount: number;
  originalCategory: string;
  aiCategory: string;
  proposedCategory: string;
  newCategory: string;
  deleted: boolean;
  stdName: string;
  stdType: string;
  year: number | null;
  monthNum: number | null;
  month: string;
}

export interface AggregatedMonth {
  Year: number;
  MonthNum: number;
  Month: string;
  values: Record<string, number>;
  totaleEntrate: number;
  totaleUscite: number;
  redditoMenoSpese: number;
  risparmioPct: number;
}

export interface AiStats {
  mode: ClassifyMode;
  llmSent: number;
  llmMapped: number;
  llmFailed: number;
  errors: string[];
}

export interface ImportResultPayload {
  rows: ImportReviewRow[];
  aggregated: AggregatedMonth[];
  report: string;
  stats: AiStats;
  categoryOptions: string[];
  sourceName: string;
}

export interface InitialState {
  rows: MonthlyRow[];
  targets: Record<string, number>;
  dbInfo: DbInfo;
  transactions: TransactionRecord[];
  ai: AiConfigState;
  cloud: CloudConfig;
  defaultTimeWindow: string;
  chat: ChatMessage[];
  extensionVersion: string;
}

export type ToastLevel = 'info' | 'warn' | 'error' | 'success';

export type HostMessage =
  | { type: 'init'; payload: InitialState }
  | { type: 'database'; rows: MonthlyRow[]; targets: Record<string, number>; dbInfo: DbInfo }
  | { type: 'transactions'; monthRef: string; rows: TransactionRecord[] }
  | { type: 'aiConfig'; config: AiConfigState }
  | { type: 'importProgress'; percent: number; message: string }
  | { type: 'importResult'; result: ImportResultPayload }
  | { type: 'importSaved'; message: string; monthRef?: string }
  | { type: 'importError'; message: string }
  | { type: 'chatChunk'; requestId: string; text: string }
  | { type: 'chatDone'; requestId: string; text: string }
  | { type: 'chatError'; requestId: string; message: string }
  | { type: 'chatHistory'; messages: ChatMessage[] }
  | { type: 'merchantMap'; entries: MerchantEntry[]; categories: string[]; count: number }
  | { type: 'cloudState'; state: CloudConfig; status: string }
  | { type: 'cloudResult'; action: string; ok: boolean; message: string }
  | { type: 'navigate'; page: 'dashboard' | 'data' | 'month' | 'chat' }
  | { type: 'toast'; level: ToastLevel; message: string }
  | { type: 'saved'; message: string };

export type WebviewMessage =
  | { type: 'ready' }
  | { type: 'refreshAll' }
  | { type: 'loadTransactions'; monthRef: string }
  | { type: 'saveMonthly'; rows: MonthlyRow[]; deleted: MonthlyKey[] }
  | { type: 'saveTargets'; targets: Record<string, number> }
  | { type: 'loadMerchants' }
  | { type: 'setMerchantManual'; merchant: string; category: string }
  | { type: 'deleteMerchant'; merchant: string }
  | { type: 'addMerchantManual'; merchant: string; category: string }
  | { type: 'importSeed' }
  | { type: 'exportCsv' }
  | { type: 'exportMerchants' }
  | { type: 'chooseImportFile'; classifyMode: ClassifyMode }
  | { type: 'importStatement'; fileName: string; dataBase64: string; classifyMode: ClassifyMode }
  | { type: 'applyImportEdits'; rows: ImportReviewRow[] }
  | { type: 'saveImport'; rows: ImportReviewRow[] }
  | { type: 'cancelImport' }
  | { type: 'setAiConfig'; provider: ProviderType; model: string }
  | { type: 'setApiKey'; provider: ProviderType; apiKey: string }
  | { type: 'clearApiKey'; provider: ProviderType }
  | { type: 'chatSend'; requestId: string; text: string }
  | { type: 'chatClear' }
  | { type: 'setCloudEnabled'; enabled: boolean }
  | { type: 'setCloudConfig'; repo: string; branch: string; path: string; csvPath: string }
  | { type: 'setGithubToken'; token: string }
  | { type: 'clearGithubToken' }
  | { type: 'cloudBackup' }
  | { type: 'cloudRestore' }
  | { type: 'cloudImportCsv' }
  | { type: 'cloudStatus' }
  | { type: 'addManualMonth'; year: number; month: string; mode: 'increment' | 'create'; values: Record<string, number> };

export const UNCLASSIFIED_PLACEHOLDER = '❓ Da classificare';
export const EXCLUDED_CATEGORY = 'Escluso';
