import type {
  AiConfigState,
  ChatMessage,
  ClassifyMode,
  CloudConfig,
  DbInfo,
  ImportResultPayload,
  MerchantEntry,
  MonthlyRow,
  ProviderType,
  TimeWindow,
  TransactionRecord,
  WebviewMessage,
} from '../types';

export type Page = 'dashboard' | 'data' | 'month' | 'chat';

export interface UiState {
  rows: MonthlyRow[];
  targets: Record<string, number>;
  dbInfo: DbInfo;
  transactions: TransactionRecord[];
  ai: AiConfigState;
  cloud: CloudConfig;
  chat: ChatMessage[];
  defaultWindow: TimeWindow;
  page: Page;
  window: TimeWindow;
  selectedMonth: string;
  filters: {
    investimenti: boolean;
    straordinarie: boolean;
    capex: boolean;
  };
  classifyMode: ClassifyMode;
  merchant: { entries: MerchantEntry[]; categories: string[]; count: number } | null;
  importResult: ImportResultPayload | null;
  importProgress: { percent: number; message: string } | null;
  importError: string | null;
  cloudStatus: string;
  chatStreaming: { requestId: string; text: string } | null;
  version: string;
}

export interface UiContext {
  state: UiState;
  post: (message: WebviewMessage) => void;
  toast: (level: 'info' | 'warn' | 'error' | 'success', message: string) => void;
  renderMain: () => void;
  renderAll: () => void;
  persist: () => void;
}

export interface PersistedState {
  page?: Page;
  window?: TimeWindow;
  selectedMonth?: string;
  filters?: UiState['filters'];
  classifyMode?: ClassifyMode;
  providerDraft?: ProviderType;
  modelDraft?: string;
}
