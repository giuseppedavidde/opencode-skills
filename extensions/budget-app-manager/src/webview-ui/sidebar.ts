import {
  PROVIDER_LABELS,
  PROVIDER_MODELS,
  PROVIDER_TYPES,
  type ProviderType,
  type TimeWindow,
} from '../types';
import { availableMonthRefs } from '../metrics';
import { confirmThen, el, fmtNum, clear } from './dom';
import type { Page, UiContext } from './context';

const NAV: Array<{ page: Page; label: string }> = [
  { page: 'dashboard', label: '📊 Dashboard' },
  { page: 'data', label: '📝 Gestione Dati' },
  { page: 'month', label: '➕ Gestione Mese' },
  { page: 'chat', label: '💬 Assistant AI' },
];

function field(label: string, control: HTMLElement): HTMLElement {
  return el('label', { className: 'field' }, [el('span', { text: label }), control]);
}

function passwordInput(placeholder: string): HTMLInputElement {
  return el('input', {
    className: 'control',
    attrs: { type: 'password', placeholder, autocomplete: 'off' },
  }) as HTMLInputElement;
}

export function renderSidebar(root: HTMLElement, ctx: UiContext): void {
  clear(root);
  const { state } = ctx;

  const brand = el('div', { className: 'brand' }, [
    el('div', { className: 'brand-icon', text: '💰' }),
    el('div', {}, [
      el('div', { className: 'brand-title', text: 'Budget App' }),
      el('div', { className: 'brand-sub', text: `v${state.version}` }),
    ]),
  ]);
  root.append(brand);

  const nav = el('nav', { className: 'nav' });
  for (const item of NAV) {
    const button = el('button', {
      className: `nav-item ${state.page === item.page ? 'active' : ''}`,
      text: item.label,
      attrs: { type: 'button' },
    });
    button.addEventListener('click', () => {
      state.page = item.page;
      ctx.persist();
      ctx.renderAll();
    });
    nav.append(button);
  }
  root.append(nav);

  // Time filters (mirrors the Streamlit sidebar)
  const filtersDetails = el('details', {
    className: 'expander sidebar-expander',
    attrs: { open: 'true' },
  });
  filtersDetails.append(el('summary', { text: '📅 Filtri Temporali' }));
  const filtersBody = el('div', { className: 'expander-body' });
  const months = availableMonthRefs(state.rows);
  const monthSelect = el('select', { className: 'control' });
  for (const month of months) {
    const option = el('option', { text: month });
    option.value = month;
    option.selected = month === state.selectedMonth;
    monthSelect.append(option);
  }
  monthSelect.addEventListener('change', () => {
    state.selectedMonth = monthSelect.value;
    ctx.persist();
    ctx.post({ type: 'loadTransactions', monthRef: state.selectedMonth });
    ctx.renderAll();
  });
  const windowSelect = el('select', { className: 'control' });
  for (const option of [3, 6, 12, 24, 'All'] as TimeWindow[]) {
    const node = el('option', { text: option === 'All' ? 'Tutto lo storico' : `${option} mesi` });
    node.value = String(option);
    node.selected = String(option) === String(state.window);
    windowSelect.append(node);
  }
  windowSelect.addEventListener('change', () => {
    state.window = (windowSelect.value === 'All' ? 'All' : Number(windowSelect.value)) as TimeWindow;
    ctx.persist();
    ctx.renderAll();
  });
  const expenseToggle = (
    label: string,
    checked: boolean,
    onChange: (value: boolean) => void,
  ): HTMLElement => {
    const input = el('input', { attrs: { type: 'checkbox' } }) as HTMLInputElement;
    input.checked = checked;
    input.addEventListener('change', () => {
      onChange(input.checked);
      ctx.persist();
      ctx.renderAll();
    });
    return el('label', { className: 'toggle' }, [input, el('span', { text: label })]);
  };
  filtersBody.append(
    field('Seleziona mese', monthSelect),
    field('Orizzonte trend', windowSelect),
    el('div', { className: 'section-label', text: 'Spese incluse' }),
    expenseToggle('💼 Investimenti', state.filters.investimenti, (value) => {
      state.filters.investimenti = value;
    }),
    expenseToggle('🎢 Spese Straordinarie', state.filters.straordinarie, (value) => {
      state.filters.straordinarie = value;
    }),
    expenseToggle('🚗 Acquisto Auto (vista)', state.filters.capex, (value) => {
      state.filters.capex = value;
    }),
  );
  filtersDetails.append(filtersBody);
  root.append(filtersDetails);

  // AI configuration
  const aiDetails = el('details', { className: 'expander sidebar-expander', attrs: { open: 'true' } });
  aiDetails.append(el('summary', { text: '🤖 AI Configuration' }));
  const aiBody = el('div', { className: 'expander-body' });

  const providerSelect = el('select', { className: 'control' });
  for (const provider of PROVIDER_TYPES) {
    const option = el('option', { text: PROVIDER_LABELS[provider] });
    option.value = provider;
    option.selected = provider === state.ai.provider;
    providerSelect.append(option);
  }

  const modelSelect = el('select', { className: 'control' });
  const fillModels = (provider: ProviderType): void => {
    clear(modelSelect);
    const models = [
      ...(provider === state.ai.provider ? state.ai.models : PROVIDER_MODELS[provider]),
    ];
    if (provider === state.ai.provider && state.ai.model && !models.includes(state.ai.model)) {
      models.unshift(state.ai.model);
    }
    for (const model of models) {
      const option = el('option', { text: model });
      option.value = model;
      modelSelect.append(option);
    }
    modelSelect.value = provider === state.ai.provider ? state.ai.model : models[0] ?? '';
  };
  fillModels(state.ai.provider);

  providerSelect.addEventListener('change', () => {
    const provider = providerSelect.value as ProviderType;
    fillModels(provider);
    const model = PROVIDER_MODELS[provider][0] ?? '';
    ctx.post({ type: 'setAiConfig', provider, model });
  });
  modelSelect.addEventListener('change', () => {
    ctx.post({
      type: 'setAiConfig',
      provider: state.ai.provider,
      model: modelSelect.value,
    });
  });

  const customModel = el('input', {
    className: 'control',
    attrs: { type: 'text', placeholder: 'Modello personalizzato (opzionale)' },
  }) as HTMLInputElement;
  const saveModel = el('button', { className: 'btn small', text: 'Salva modello', attrs: { type: 'button' } });
  saveModel.addEventListener('click', () => {
    const model = customModel.value.trim() || modelSelect.value;
    if (!model) {
      ctx.toast('warn', 'Seleziona o inserisci un modello.');
      return;
    }
    ctx.post({ type: 'setAiConfig', provider: state.ai.provider, model });
    customModel.value = '';
  });

  const keyInput = passwordInput('API key (salvata in SecretStorage)');
  const saveKey = el('button', { className: 'btn small', text: 'Salva key', attrs: { type: 'button' } });
  saveKey.addEventListener('click', () => {
    const value = keyInput.value.trim();
    if (!value) {
      ctx.toast('warn', 'Inserisci una API key.');
      return;
    }
    ctx.post({ type: 'setApiKey', provider: state.ai.provider, apiKey: value });
    keyInput.value = '';
  });
  const clearKey = el('button', { className: 'btn small ghost', text: 'Rimuovi', attrs: { type: 'button' } });
  clearKey.addEventListener('click', () => {
    ctx.post({ type: 'clearApiKey', provider: state.ai.provider });
  });

  const keyStatus = el('div', { className: `status-line ${state.ai.keySet ? 'ok' : 'warn'}` }, [
    el('span', { text: state.ai.keySet ? '✅ API key presente' : '⚠️ API key assente' }),
    state.ai.envKeyAvailable ? el('span', { className: 'muted', text: ' (fallback .env disponibile)' }) : null,
  ]);

  aiBody.append(
    field('Provider', providerSelect),
    field('Model', modelSelect),
    el('div', { className: 'inline-form' }, [customModel, saveModel]),
    field('API key', el('div', { className: 'inline-form' }, [keyInput, saveKey, clearKey])),
    keyStatus,
  );

  if (state.ai.provider === 'opencode') {
    aiBody.append(
      el('p', {
        className: 'hint',
        text: 'OpenCode Go usa la CLI locale (modello opencode-go/*, timeout 300 s). L’agente viene ricreato a ogni cambio di provider, modello o API key.',
      }),
    );
  }

  aiBody.append(el('hr', { className: 'sep' }));
  aiBody.append(el('div', { className: 'section-label', text: '🧭 Modalità classificazione AI' }));
  const modeGroup = el('div', { className: 'radio-group' });
  const modes: Array<{ value: 'hybrid' | 'llm_only'; label: string }> = [
    { value: 'hybrid', label: '🔀 Ibrida (negozi + AI)' },
    { value: 'llm_only', label: '🧠 Solo AI (forza LLM su tutte)' },
  ];
  for (const mode of modes) {
    const input = el('input', { attrs: { type: 'radio', name: 'classify-mode' } }) as HTMLInputElement;
    input.checked = state.classifyMode === mode.value;
    input.value = mode.value;
    input.addEventListener('change', () => {
      if (!input.checked) return;
      state.classifyMode = mode.value;
      ctx.persist();
      if (state.page === 'month') ctx.renderMain();
      ctx.toast('info', `Modalità classificazione: ${mode.label}`);
    });
    modeGroup.append(el('label', { className: 'radio' }, [input, el('span', { text: mode.label })]));
  }
  aiBody.append(modeGroup);
  aiDetails.append(aiBody);
  root.append(aiDetails);

  // Database
  const dbDetails = el('details', { className: 'expander sidebar-expander' });
  dbDetails.append(el('summary', { text: '💾 Database' }));
  const dbBody = el('div', { className: 'expander-body' }, [
    el('div', { className: 'kv' }, [el('span', { text: 'File' }), el('code', { text: state.dbInfo.dbPath })]),
    el('div', { className: 'kv' }, [el('span', { text: 'Dimensione' }), el('span', { text: `${state.dbInfo.dbSizeKb.toFixed(1)} KB` })]),
    el('div', { className: 'kv' }, [el('span', { text: 'Records' }), el('span', { text: fmtNum(state.dbInfo.rowCount) })]),
    el('div', { className: 'kv' }, [el('span', { text: 'Transazioni' }), el('span', { text: fmtNum(state.dbInfo.transactionCount) })]),
    el('div', { className: 'kv' }, [el('span', { text: 'Mappature' }), el('span', { text: fmtNum(state.dbInfo.merchantCount) })]),
    el('div', { className: 'kv' }, [el('span', { text: 'Ultimo backup' }), el('span', { text: state.dbInfo.lastBackupTime ?? 'n/a' })]),
  ]);
  const exportCsv = el('button', { className: 'btn small', text: '📥 Export CSV', attrs: { type: 'button' } });
  exportCsv.addEventListener('click', () => ctx.post({ type: 'exportCsv' }));
  dbBody.append(exportCsv);
  dbDetails.append(dbBody);
  root.append(dbDetails);

  // Cloud
  const cloudDetails = el('details', { className: 'expander sidebar-expander' });
  cloudDetails.append(el('summary', { text: '☁️ Cloud Sync (GitHub)' }));
  const cloudBody = el('div', { className: 'expander-body' });
  const enabled = el('input', { attrs: { type: 'checkbox' } }) as HTMLInputElement;
  enabled.checked = state.cloud.enabled;
  enabled.addEventListener('change', () => {
    ctx.post({ type: 'setCloudEnabled', enabled: enabled.checked });
  });

  const repo = el('input', { className: 'control', attrs: { type: 'text', placeholder: 'owner/repo', value: state.cloud.repo } }) as HTMLInputElement;
  const branch = el('input', { className: 'control', attrs: { type: 'text', value: state.cloud.branch } }) as HTMLInputElement;
  const dbPath = el('input', { className: 'control', attrs: { type: 'text', value: state.cloud.path } }) as HTMLInputElement;
  const csvPath = el('input', { className: 'control', attrs: { type: 'text', value: state.cloud.csvPath } }) as HTMLInputElement;
  const saveCloud = el('button', { className: 'btn small', text: 'Salva configurazione', attrs: { type: 'button' } });
  saveCloud.addEventListener('click', () => {
    ctx.post({
      type: 'setCloudConfig',
      repo: repo.value.trim(),
      branch: branch.value.trim() || 'main',
      path: dbPath.value.trim() || 'budget.db',
      csvPath: csvPath.value.trim() || 'budget_database.csv',
    });
  });

  const token = passwordInput('GitHub token');
  const saveToken = el('button', { className: 'btn small', text: 'Salva token', attrs: { type: 'button' } });
  saveToken.addEventListener('click', () => {
    if (!token.value.trim()) {
      ctx.toast('warn', 'Inserisci un token GitHub.');
      return;
    }
    ctx.post({ type: 'setGithubToken', token: token.value.trim() });
    token.value = '';
  });
  const clearToken = el('button', { className: 'btn small ghost', text: 'Rimuovi', attrs: { type: 'button' } });
  clearToken.addEventListener('click', () => ctx.post({ type: 'clearGithubToken' }));

  const backup = el('button', { className: 'btn small', text: '⬆️ Backup ora', attrs: { type: 'button' } });
  backup.addEventListener('click', () => ctx.post({ type: 'cloudBackup' }));
  const restore = el('button', { className: 'btn small', text: '⬇️ Restore', attrs: { type: 'button' } });
  restore.addEventListener('click', () => {
    confirmThen(restore as HTMLButtonElement, () => ctx.post({ type: 'cloudRestore' }), '⚠️ Conferma restore?');
  });
  const status = el('button', { className: 'btn small ghost', text: 'Stato', attrs: { type: 'button' } });
  status.addEventListener('click', () => ctx.post({ type: 'cloudStatus' }));
  const seedCsv = el('button', { className: 'btn small ghost', text: '📄 Scarica CSV', attrs: { type: 'button' } });
  seedCsv.addEventListener('click', () => ctx.post({ type: 'cloudImportCsv' }));

  cloudBody.append(
    el('label', { className: 'toggle' }, [enabled, el('span', { text: 'Abilita cloud sync' })]),
    field('Repository', repo),
    field('Branch', branch),
    field('DB path', dbPath),
    field('CSV path', csvPath),
    el('div', { className: 'button-row' }, [saveCloud]),
    field(
      'GitHub token',
      el('div', { className: 'inline-form' }, [token, saveToken, clearToken]),
    ),
    el('div', { className: `status-line ${state.cloud.tokenSet ? 'ok' : 'warn'}` }, [
      el('span', { text: state.cloud.tokenSet ? '✅ Token presente' : '⚠️ Token assente' }),
    ]),
    el('div', { className: 'button-row wrap' }, [backup, restore, seedCsv, status]),
    ...(state.cloudStatus ? [el('div', { className: 'hint', text: state.cloudStatus })] : []),
  );
  cloudDetails.append(cloudBody);
  root.append(cloudDetails);

  root.append(
    el('div', { className: 'sidebar-footer' }, [
      el('span', { text: 'Dati locali, nessuna CDN.' }),
      el('button', { className: 'link', text: 'Aggiorna', attrs: { type: 'button' } }),
    ]),
  );
  const refresh = root.lastElementChild?.lastElementChild as HTMLElement | null;
  refresh?.addEventListener('click', () => ctx.post({ type: 'refreshAll' }));
}
