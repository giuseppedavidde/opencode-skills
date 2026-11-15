import type { DerivedRow } from '../metrics';
import type { ForecastPoint } from '../types';

declare global {
  interface Window {
    Plotly?: {
      react: (
        element: HTMLElement,
        data: unknown[],
        layout?: unknown,
        config?: unknown,
      ) => Promise<unknown>;
      purge: (element: HTMLElement) => void;
    };
  }
}

const FONT = { color: '#e6edf3', family: 'system-ui, sans-serif', size: 12 };
const CONFIG = { displayModeBar: false, responsive: true };

function plot(element: HTMLElement, data: unknown[], layout: Record<string, unknown>): void {
  if (!window.Plotly) {
    element.textContent = 'Plotly non disponibile';
    return;
  }
  void window.Plotly.react(element, data, layout, CONFIG);
}

function baseLayout(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    template: 'plotly_dark',
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: FONT,
    margin: { l: 48, r: 16, t: 24, b: 36 },
    hovermode: 'x unified',
    legend: { orientation: 'h', y: 1.12, font: { size: 11 } },
    ...extra,
  };
}

function isoDates(rows: readonly { DateStr: string }[]): string[] {
  return rows.map((row) => `${row.DateStr}-01`);
}

function monthAxis(): Record<string, unknown> {
  return { type: 'date', tickformat: '%b %Y', gridcolor: 'rgba(255,255,255,0.06)' };
}

function yAxis(title: string, side?: 'right'): Record<string, unknown> {
  return {
    title: { text: title, font: { size: 11 } },
    gridcolor: 'rgba(255,255,255,0.06)',
    zerolinecolor: 'rgba(255,255,255,0.15)',
    ...(side === 'right' ? { overlaying: 'y', side: 'right', showgrid: false } : {}),
  };
}

export function patrimonioChart(
  element: HTMLElement,
  rows: readonly DerivedRow[],
  forecast: readonly ForecastPoint[],
): void {
  const dates = isoDates(rows);
  const values = rows.map((row) => row.patrimonio);
  const data: unknown[] = [
    {
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Patrimonio',
      x: dates,
      y: values,
      fill: 'tozeroy',
      line: { color: '#3498db', width: 3 },
      fillcolor: 'rgba(52, 152, 219, 0.15)',
      hovertemplate: '%{x|%b %Y}: € %{y:,.2f}<extra></extra>',
    },
  ];
  const shapes: unknown[] = [
    {
      type: 'line',
      xref: 'paper',
      x0: 0,
      x1: 1,
      y0: 0,
      y1: 0,
      line: { color: 'rgba(255,255,255,0.3)', dash: 'dash', width: 1 },
    },
  ];

  if (forecast.length > 0 && rows.length > 0) {
    const last = values[values.length - 1] ?? 0;
    let cumulative = last;
    let lower = last;
    let upper = last;
    const fDates: string[] = [];
    const fPat: number[] = [];
    const fNet: number[] = [];
    const fUpper: number[] = [];
    const fLower: number[] = [];
    for (const point of forecast) {
      cumulative += point.net;
      lower += point.lower;
      upper += point.upper;
      fDates.push(point.date);
      fPat.push(cumulative);
      fNet.push(point.net);
      fUpper.push(upper);
      fLower.push(lower);
    }
    data.push(
      {
        type: 'scatter',
        mode: 'lines',
        name: 'Intervallo 80%',
        x: [...fDates, ...[...fDates].reverse()],
        y: [...fUpper, ...[...fLower].reverse()],
        fill: 'toself',
        fillcolor: 'rgba(52, 152, 219, 0.18)',
        line: { color: 'rgba(0,0,0,0)' },
        hoverinfo: 'skip',
      },
      {
        type: 'scatter',
        mode: 'lines',
        name: 'Proiezione Patrimonio',
        x: fDates,
        y: fPat,
        line: { color: '#3498db', width: 2, dash: 'dash' },
        hovertemplate: '%{x|%b %Y}: € %{y:,.2f}<extra></extra>',
      },
      {
        type: 'bar',
        name: 'Netto mensile (futuro)',
        x: fDates,
        y: fNet,
        yaxis: 'y2',
        marker: { color: fNet.map((value) => (value >= 0 ? '#2ecc71' : '#e74c3c')) },
        opacity: 0.35,
        hovertemplate: '%{x|%b %Y}: € %{y:,.2f}<extra></extra>',
      },
    );
    shapes.push({
      type: 'rect',
      xref: 'x',
      yref: 'paper',
      x0: fDates[0],
      x1: fDates[fDates.length - 1],
      y0: 0,
      y1: 1,
      fillcolor: 'rgba(241, 196, 15, 0.06)',
      line: { width: 0 },
      layer: 'below',
    });
  }

  plot(element, data, baseLayout({
    xaxis: monthAxis(),
    yaxis: yAxis('Patrimonio (€)'),
    yaxis2: yAxis('Netto mensile (€)', 'right'),
    shapes,
    height: 380,
  }));
}

export function sparkline(element: HTMLElement, values: readonly number[], color: string): void {
  plot(
    element,
    [
      {
        type: 'scatter',
        mode: 'lines',
        y: values,
        line: { color, width: 2 },
        fill: 'tozeroy',
        fillcolor: `${color}22`,
        hoverinfo: 'skip',
      },
    ],
    {
      height: 58,
      margin: { l: 0, r: 0, t: 0, b: 0 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      xaxis: { visible: false },
      yaxis: { visible: false },
      showlegend: false,
    },
  );
}

export function investedCharts(element: HTMLElement, rows: readonly DerivedRow[]): void {
  const dates = isoDates(rows);
  const data: unknown[] = [
    {
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Investimenti Cumulativo',
      x: dates,
      y: rows.map((row) => row.investimentiCumulativo),
      fill: 'tozeroy',
      line: { color: '#9b59b6', width: 3 },
      fillcolor: 'rgba(155, 89, 182, 0.15)',
      hovertemplate: '%{x|%b %Y}: € %{y:,.2f}<extra></extra>',
    },
    {
      type: 'bar',
      name: 'Investimenti Mensili',
      x: dates,
      y: rows.map((row) => row['Investimenti']),
      marker: {
        color: rows.map((row) => (row['Investimenti'] >= 0 ? '#2ecc71' : '#e74c3c')),
      },
      hovertemplate: '%{x|%b %Y}: € %{y:,.2f}<extra></extra>',
    },
  ];
  plot(element, data, baseLayout({
    xaxis: monthAxis(),
    yaxis: yAxis('€ Euro'),
    height: 300,
    legend: { orientation: 'h', y: 1.15 },
  }));
}

export function cashflowChart(
  element: HTMLElement,
  rows: readonly DerivedRow[],
  selectedDate: string,
): void {
  const dates = isoDates(rows);
  const income = rows.map((row) => row.totaleEntrate);
  const expense = rows.map((row) => row.totaleUscite);
  const avgIncome = income.length ? income.reduce((a, b) => a + b, 0) / income.length : 0;
  const avgExpense = expense.length ? expense.reduce((a, b) => a + b, 0) / expense.length : 0;
  plot(
    element,
    [
      {
        type: 'scatter',
        mode: 'lines',
        name: 'Entrate',
        x: dates,
        y: income,
        fill: 'tozeroy',
        line: { color: '#2ecc71', width: 3 },
        fillcolor: 'rgba(46, 204, 113, 0.1)',
      },
      {
        type: 'scatter',
        mode: 'lines',
        name: 'Uscite',
        x: dates,
        y: expense,
        fill: 'tozeroy',
        line: { color: '#e74c3c', width: 3 },
        fillcolor: 'rgba(231, 76, 60, 0.1)',
      },
    ],
    baseLayout({
      xaxis: monthAxis(),
      yaxis: yAxis('€ Euro'),
      height: 350,
      shapes: [
        {
          type: 'line',
          xref: 'paper',
          x0: 0,
          x1: 1,
          y0: avgIncome,
          y1: avgIncome,
          line: { color: '#2ecc71', dash: 'dot', width: 1 },
        },
        {
          type: 'line',
          xref: 'paper',
          x0: 0,
          x1: 1,
          y0: avgExpense,
          y1: avgExpense,
          line: { color: '#e74c3c', dash: 'dot', width: 1 },
        },
        {
          type: 'line',
          xref: 'x',
          yref: 'paper',
          x0: `${selectedDate}-01`,
          x1: `${selectedDate}-01`,
          y0: 0,
          y1: 1,
          line: { color: 'rgba(255,255,255,0.5)', dash: 'dash', width: 1 },
        },
      ],
      annotations: [
        {
          xref: 'paper',
          yref: 'y',
          x: 0,
          y: avgIncome,
          text: `Media Entrate: €${avgIncome.toFixed(0)}`,
          showarrow: false,
          font: { size: 10, color: '#2ecc71' },
          yshift: 8,
        },
        {
          xref: 'paper',
          yref: 'y',
          x: 0,
          y: avgExpense,
          text: `Media Uscite: €${avgExpense.toFixed(0)}`,
          showarrow: false,
          font: { size: 10, color: '#e74c3c' },
          yshift: -8,
        },
      ],
    }),
  );
}

export function waterfallChart(
  element: HTMLElement,
  labels: readonly string[],
  values: readonly number[],
  measures: readonly string[],
): void {
  plot(
    element,
    [
      {
        type: 'waterfall',
        x: labels,
        y: values,
        measure: measures,
        textposition: 'outside',
        connector: { line: { color: 'rgba(255,255,255,0.3)' } },
        increasing: { marker: { color: '#2ecc71' } },
        decreasing: { marker: { color: '#e74c3c' } },
        totals: { marker: { color: '#3498db' } },
        hovertemplate: '%{x}: € %{y:,.2f}<extra></extra>',
      },
    ],
    baseLayout({
      xaxis: { tickangle: -25 },
      yaxis: yAxis('€ Euro'),
      height: 380,
    }),
  );
}

export function benchmarkChart(
  element: HTMLElement,
  categories: readonly string[],
  actual: readonly number[],
  target: readonly number[],
  delta = false,
): void {
  if (delta) {
    const values = categories.map((_, index) => (actual[index] ?? 0) - (target[index] ?? 0));
    plot(
      element,
      [
        {
          type: 'bar',
          x: categories,
          y: values,
          marker: { color: values.map((value) => (value > 0 ? '#e74c3c' : '#2ecc71')) },
          hovertemplate: '%{x}: € %{y:,.2f}<extra></extra>',
        },
      ],
      baseLayout({
        xaxis: { tickangle: -25 },
        yaxis: yAxis('Delta €'),
        height: 350,
        showlegend: false,
        shapes: [
          {
            type: 'line',
            xref: 'paper',
            x0: 0,
            x1: 1,
            y0: 0,
            y1: 0,
            line: { color: 'rgba(255,255,255,0.3)', dash: 'dash' },
          },
        ],
      }),
    );
    return;
  }
  plot(
    element,
    [
      { type: 'bar', name: 'Effettivo', x: categories, y: actual, marker: { color: '#3498db' } },
      {
        type: 'bar',
        name: 'Target',
        x: categories,
        y: target,
        marker: { color: '#95a5a6', opacity: 0.7 },
      },
    ],
    baseLayout({
      barmode: 'group',
      xaxis: { tickangle: -25 },
      yaxis: yAxis('€ Euro'),
      height: 350,
    }),
  );
}

export function donutChart(
  element: HTMLElement,
  labels: readonly string[],
  values: readonly number[],
): void {
  plot(
    element,
    [
      {
        type: 'pie',
        hole: 0.6,
        labels,
        values,
        textinfo: 'percent',
        hovertemplate: '%{label}: € %{value:,.2f}<extra></extra>',
      },
    ],
    baseLayout({
      height: 350,
      legend: { orientation: 'v', x: 1, y: 0.5, font: { size: 10 } },
      margin: { l: 0, r: 0, t: 20, b: 0 },
    }),
  );
}

export function savingsRateChart(
  element: HTMLElement,
  dates: readonly string[],
  values: readonly number[],
): void {
  plot(
    element,
    [
      {
        type: 'scatter',
        mode: 'lines+markers',
        name: 'Risparmio %',
        x: dates,
        y: values,
        line: { color: '#f1c40f', width: 3 },
        hovertemplate: '%{y:.1f}%<extra></extra>',
      },
    ],
    baseLayout({
      xaxis: monthAxis(),
      yaxis: yAxis('%'),
      height: 300,
      shapes: [
        {
          type: 'line',
          xref: 'paper',
          x0: 0,
          x1: 1,
          y0: 0,
          y1: 0,
          line: { color: 'rgba(255,255,255,0.3)', dash: 'dash' },
        },
        {
          type: 'line',
          xref: 'paper',
          x0: 0,
          x1: 1,
          y0: 20,
          y1: 20,
          line: { color: 'rgba(46, 204, 113, 0.5)', dash: 'dash' },
        },
      ],
    }),
  );
}

export function netChart(
  element: HTMLElement,
  dates: readonly string[],
  net: readonly number[],
  movingAverage: readonly number[],
): void {
  plot(
    element,
    [
      {
        type: 'bar',
        name: 'Netto mensile',
        x: dates,
        y: net,
        marker: { color: net.map((value) => (value >= 0 ? '#2ecc71' : '#e74c3c')) },
        hovertemplate: '%{x|%b %Y}: € %{y:,.2f}<extra></extra>',
      },
      {
        type: 'scatter',
        mode: 'lines',
        name: 'Media mobile 6 mesi',
        x: dates,
        y: movingAverage,
        line: { color: '#f1c40f', width: 3 },
        hovertemplate: '%{x|%b %Y}: € %{y:,.2f}<extra></extra>',
      },
    ],
    baseLayout({
      xaxis: monthAxis(),
      yaxis: yAxis('€ Euro'),
      height: 350,
      shapes: [
        {
          type: 'line',
          xref: 'paper',
          x0: 0,
          x1: 1,
          y0: 0,
          y1: 0,
          line: { color: 'rgba(255,255,255,0.3)', dash: 'dash' },
        },
      ],
    }),
  );
}

export function heatmapChart(
  element: HTMLElement,
  years: readonly string[],
  matrix: readonly (number | null)[][],
): void {
  plot(
    element,
    [
      {
        type: 'heatmap',
        x: ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'],
        y: years,
        z: matrix,
        colorscale: 'RdYlGn',
        reversescale: true,
        hovertemplate: '%{y} %{x}: € %{z:,.0f}<extra></extra>',
        colorbar: { title: '€', thickness: 12 },
      },
    ],
    baseLayout({
      height: 400,
      margin: { l: 48, r: 20, t: 30, b: 30 },
    }),
  );
}

export function trendCategoriesChart(
  element: HTMLElement,
  dates: readonly string[],
  series: readonly { name: string; values: readonly number[] }[],
): void {
  plot(
    element,
    series.map((entry) => ({
      type: 'scatter',
      mode: 'lines',
      name: entry.name,
      x: dates,
      y: entry.values,
      stackgroup: 'one',
      line: { width: 0.6 },
      hovertemplate: '%{x|%b %Y}: € %{y:,.2f}<extra>%{fullData.name}</extra>',
    })),
    baseLayout({
      xaxis: monthAxis(),
      yaxis: yAxis('€ Euro'),
      height: 350,
    }),
  );
}

export function yoyChart(
  element: HTMLElement,
  labels: readonly string[],
  income: readonly number[],
  expense: readonly number[],
  net: readonly number[],
): void {
  plot(
    element,
    [
      {
        type: 'bar',
        name: 'Entrate',
        x: labels,
        y: income,
        marker: { color: '#2ecc71' },
        hovertemplate: '€ %{y:,.2f}<extra></extra>',
      },
      {
        type: 'bar',
        name: 'Uscite',
        x: labels,
        y: expense,
        marker: { color: '#e74c3c' },
        hovertemplate: '€ %{y:,.2f}<extra></extra>',
      },
      {
        type: 'scatter',
        mode: 'lines+markers',
        name: 'Netto',
        x: labels,
        y: net,
        line: { color: '#f1c40f', width: 3 },
        hovertemplate: '€ %{y:,.2f}<extra></extra>',
      },
    ],
    baseLayout({
      barmode: 'group',
      yaxis: yAxis('€ Euro'),
      height: 350,
    }),
  );
}

export function gaugeChart(element: HTMLElement, value: number): void {
  plot(
    element,
    [
      {
        type: 'indicator',
        mode: 'gauge+number+delta',
        value,
        title: { text: 'Risparmio Mensile %', font: { size: 13 } },
        delta: { reference: 20, increasing: { color: 'green' } },
        gauge: {
          axis: { range: [-100, 100], tickwidth: 1, tickcolor: 'white' },
          bar: { color: value > 0 ? '#2ecc71' : '#e74c3c' },
          bgcolor: 'rgba(0,0,0,0)',
          borderwidth: 2,
          bordercolor: '#333',
          steps: [
            { range: [-100, 0], color: '#550000' },
            { range: [0, 20], color: '#555500' },
            { range: [20, 100], color: '#005500' },
          ],
        },
      },
    ],
    {
      paper_bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#e6edf3' },
      margin: { l: 24, r: 24, t: 48, b: 16 },
      height: 300,
    },
  );
}
