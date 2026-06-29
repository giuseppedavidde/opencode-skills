"""MarketAnalyzer — Streamlit dashboard powered by trading_mcp engine."""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_SRC = REPO_ROOT / "mcp" / "src"
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from trading_mcp.analysis.macro import detect_regime, get_dynamic_weights
from trading_mcp.analysis.scanner import (  # noqa: E402
    apply_macro_regime,
    load_universe,
    parse_custom_tickers,
    process_crypto_ticker,
    process_ticker,
    set_fetch_news,
)
from trading_mcp.analysis.options_calc import analyze_options_position  # noqa: E402
from trading_mcp.config import TICKERS_DIR  # noqa: E402

st.set_page_config(page_title="MarketAnalyzer", layout="wide")
st.title("MarketAnalyzer")

# ── Session State ──
if "report_sections" not in st.session_state:
    st.session_state.report_sections = []
if "report_title" not in st.session_state:
    st.session_state.report_title = "Market Analysis Report"
if "macro_snapshot" not in st.session_state:
    st.session_state.macro_snapshot = None
if "last_scan_results" not in st.session_state:
    st.session_state.last_scan_results = None
if "report_count" not in st.session_state:
    st.session_state.report_count = 0


# ── Cache ──

@st.cache_data(ttl=300, show_spinner=False)
def cached_macro() -> dict:
    try:
        import yfinance as yf
    except Exception:
        return {}
    vix = dxy = None
    dxy_trend = "neutral"
    try:
        vix_t = yf.Ticker("^VIX")
        h = vix_t.history(period="5d")
        if not h.empty:
            vix = round(float(h["Close"].iloc[-1]), 2)
    except Exception:
        pass
    try:
        dxy_t = yf.Ticker("DX-Y.NYB")
        h = dxy_t.history(period="1mo")
        if not h.empty and len(h) >= 5:
            dxy = round(float(h["Close"].iloc[-1]), 2)
            dxy_prev = float(
                h["Close"].iloc[-22] if len(h) >= 22 else h["Close"].iloc[0]
            )
            if dxy > dxy_prev * 1.02:
                dxy_trend = "rising"
            elif dxy < dxy_prev * 0.98:
                dxy_trend = "falling"
    except Exception:
        pass
    regime = detect_regime(vix=vix, dxy_trend=dxy_trend)
    if vix is not None:
        if vix < 15:
            window = "FULL"
        elif vix < 25:
            window = "NORMAL"
        elif vix < 35:
            window = "SELECTIVE"
        else:
            window = "DEFENSIVE"
    else:
        window = "NORMAL"
    return {
        "vix": vix, "dxy": dxy, "dxy_trend": dxy_trend,
        "regime": regime.value, "macro_window": window,
        "weights_stock": get_dynamic_weights(regime, False),
        "weights_crypto": get_dynamic_weights(regime, True),
    }


@st.cache_data(ttl=600, show_spinner="Scanning market...")
def cached_scan(universe, tickers_str, min_score, regime):
    set_fetch_news(True)
    if tickers_str:
        universe_list = parse_custom_tickers(tickers_str)
    else:
        universe_list = load_universe(universe, str(TICKERS_DIR))
    results = []
    for t_dict in universe_list:
        if t_dict.get("market") == "CRYPTO":
            r = process_crypto_ticker(t_dict)
        else:
            r = process_ticker(t_dict)
        if r:
            results.append(r)
    results.sort(key=lambda r: r["final_score"], reverse=True)
    results = apply_macro_regime(results, regime)
    results.sort(key=lambda r: r["final_score"], reverse=True)
    return [r for r in results if r["final_score"] >= min_score]


@st.cache_data(ttl=600, show_spinner="Analyzing...")
def cached_analyze(ticker):
    set_fetch_news(True)
    t_dict = {"symbol": ticker, "name": ticker, "market": "US"}
    return process_ticker(t_dict)


# ── Report HTML Generator ──

def _dim_score(dims, keyword):
    return next((d["score"] for d in dims if keyword.lower() in d.get("name", "").lower()), 0)


def _fmt_mod(mod):
    if isinstance(mod, dict):
        return mod.get("score"), mod.get("detail", "")
    return mod, ""


def generate_report_html() -> str:
    """Generate a complete HTML report from session_state data."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    css = """
    <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           max-width: 900px; margin: 0 auto; padding: 20px; color: #1a1a2e; background: #fff; }
    h1 { color: #1a1a2e; border-bottom: 3px solid #1a1a2e; padding-bottom: 10px; }
    h2 { color: #16213e; border-bottom: 2px solid #e94560; padding-bottom: 6px; margin-top: 30px; }
    h3 { color: #0f3460; margin-top: 20px; }
    table { border-collapse: collapse; width: 100%; margin: 10px 0 20px 0; }
    th { background: #1a1a2e; color: white; padding: 10px 8px; text-align: left; font-size: 13px; }
    td { padding: 8px; border-bottom: 1px solid #eee; font-size: 13px; }
    .verdict-long { color: #00b894; font-weight: bold; }
    .verdict-short { color: #fdcb6e; font-weight: bold; }
    .verdict-avoid { color: #d63031; font-weight: bold; }
    .score-bar { display: inline-block; height: 12px; border-radius: 3px; margin-right: 6px; }
    .meta { color: #636e72; font-size: 12px; }
    .risk { background: #fff3f3; border-left: 3px solid #d63031; padding: 8px 12px; margin: 8px 0; }
    .bullish { background: #f0fff4; border-left: 3px solid #00b894; padding: 8px 12px; margin: 8px 0; }
    .section-desc { color: #636e72; font-size: 13px; margin-bottom: 15px; }
    </style>
    """
    build = [f"<html><head><meta charset='UTF-8'><title>{st.session_state.report_title}</title>{css}</head><body>"]
    build.append(f"<h1>{st.session_state.report_title}</h1>")
    build.append(f"<p class='meta'>Generated: {now} | MarketAnalyzer v1.0</p>")

    # ── SECTION: Macro ──
    macro = st.session_state.macro_snapshot or cached_macro()
    if macro:
        regime_name = macro["regime"].replace("_", " ").title()
        build.append("<h2>Macro Context</h2>")
        build.append("<table><tr><th>Indicator</th><th>Value</th><th>Signal</th></tr>")
        vix_str = f"{macro['vix']:.1f}" if macro.get("vix") else "N/A"
        dxy_str = f"{macro['dxy']:.1f}" if macro.get("dxy") else "N/A"
        build.append(f"<tr><td>VIX</td><td>{vix_str}</td><td>—</td></tr>")
        build.append(f"<tr><td>DXY</td><td>{dxy_str}</td><td>{macro['dxy_trend']}</td></tr>")
        build.append(f"<tr><td>Regime</td><td>{regime_name}</td><td>Window: {macro['macro_window']}</td></tr>")
        build.append("</table>")
        build.append("<p class='section-desc'>Dynamic Weights — Stocks: " +
                     " | ".join(f"{k} {v:.0%}" for k, v in macro.get("weights_stock", {}).items()) + "</p>")

    # ── SECTIONS added by user ──
    for section in st.session_state.report_sections:
        stype = section.get("type", "")
        data = section.get("data", {})
        title = section.get("title", "")

        if stype == "scanner":
            results = data.get("results", [])
            universe_name = data.get("universe", "custom")
            build.append(f"<h2>Market Scan — {universe_name}</h2>")
            build.append(f"<p class='section-desc'>Tickers scanned: {data.get('tickers_scanned', len(results))} "
                         f"| Passed: {data.get('tickers_passed', len(results))} "
                         f"| Min score: {data.get('min_score', 50)}</p>")
            if results:
                build.append("<table><tr><th>#</th><th>Ticker</th><th>Score</th><th>W</th><th>VP</th><th>PA</th><th>S</th><th>F</th><th>Pattern</th><th>Sector</th><th>Price</th></tr>")
                for i, r in enumerate(results[:20], 1):
                    dims = r.get("dimensions", [])
                    w = _dim_score(dims, "wyckoff")
                    vp = _dim_score(dims, "volume")
                    pa = _dim_score(dims, "price")
                    s = _dim_score(dims, "sentiment")
                    f = _dim_score(dims, "fundamentals")
                    build.append(f"<tr><td>{i}</td><td><strong>{r['symbol']}</strong></td>"
                                f"<td><span class='score-bar' style='width:{r['final_score']}px;background:hsl({120*r['final_score']/100},70%,50%)'></span>{r['final_score']:.0f}</td>"
                                f"<td>{w:.0f}</td><td>{vp:.0f}</td><td>{pa:.0f}</td><td>{s:.0f}</td><td>{f:.0f}</td>"
                                f"<td>{r.get('pattern','')[:25]}</td><td>{r.get('sector','')[:20]}</td><td>${r.get('price',0):.2f}</td></tr>")
                build.append("</table>")

        elif stype == "stock":
            score = data.get("final_score", 0)
            dims = data.get("dimensions", [])
            verdict = "Long-Term Investment" if score >= 70 else ("Short-Term Speculation" if score >= 50 else "Avoid / Wait")
            vclass = "verdict-long" if score >= 70 else ("verdict-short" if score >= 50 else "verdict-avoid")
            build.append(f"<h2>Stock Analysis — {title}</h2>")
            build.append(f"<p><strong>Composite Score:</strong> {score:.1f} | <strong>Verdict:</strong> <span class='{vclass}'>{verdict}</span> | Sector: {data.get('sector','N/A')} | Price: ${data.get('price',0):.2f}</p>")

            build.append("<table><tr><th>Dimension</th><th>Score</th><th>Detail</th></tr>")
            for d in dims:
                build.append(f"<tr><td>{d['name']}</td><td>{d['score']:.0f}</td><td>{d.get('detail','')[:150]}</td></tr>")
            build.append("</table>")

            mods = data.get("modifiers", {})
            if mods:
                build.append("<h3>Modifiers</h3><table><tr><th>Name</th><th>Score</th><th>Detail</th></tr>")
                for n, v in mods.items():
                    ms, md = _fmt_mod(v)
                    build.append(f"<tr><td>{n.replace('_',' ').title()}</td><td>{ms}</td><td>{(md or '')[:120]}</td></tr>")
                build.append("</table>")

            flags = data.get("flags", [])
            if flags:
                build.append("<p class='risk'>Flags: " + ", ".join(flags) + "</p>")

        elif stype == "options":
            build.append(f"<h2>Options Analysis — {title}</h2>")
            build.append(f"<p><strong>Strategy:</strong> {data.get('strategy_classification','N/A')} | "
                        f"Spot: ${data.get('underlying_price',0):.2f} | DTE: {data.get('dte','N/A')}</p>")
            greeks = data.get("position_greeks", {})
            build.append(f"<p>Delta: {greeks.get('total_delta',0):.4f} | Gamma: {greeks.get('total_gamma',0):.4f} | "
                        f"Theta: {greeks.get('total_theta',0):.4f} | Vega: {greeks.get('total_vega',0):.4f}</p>")
            pnl = data.get("pnl", {})
            build.append(f"<p>P&L: ${pnl.get('total_pnl',0):.2f} ({pnl.get('total_pnl_pct',0):.1f}%) | "
                        f"Breakevens: {', '.join(f'${b:.2f}' for b in data.get('breakevens',[]))}</p>")
            legs = data.get("legs", [])
            if legs:
                build.append("<table><tr><th>Side</th><th>Type</th><th>Strike</th><th>Entry</th><th>Current</th><th>P&L</th><th>Delta</th></tr>")
                for l in legs:
                    build.append(f"<tr><td>{l['side']}</td><td>{l['type']}</td><td>{l['strike']}</td>"
                                f"<td>{l['entry_premium']}</td><td>{l['current_premium']}</td><td>{l['pnl']}</td><td>{l.get('delta',0):.3f}</td></tr>")
                build.append("</table>")

        elif stype == "custom":
            build.append(f"<h2>{title}</h2>")
            build.append(f"<div>{data.get('text','')}</div>")

    build.append("<hr><p class='meta'>Generated by MarketAnalyzer — trading_mcp engine</p></body></html>")
    return "\n".join(build)


# ── TAB 1: MACRO ──
def tab_macro():
    macro = cached_macro()
    if not macro:
        st.warning("Macro data unavailable (weekend/rate-limited).")
        return
    st.session_state.macro_snapshot = macro
    regime_color = {
        "trending_bull": "green", "trending_bear": "red",
        "high_volatility": "orange", "crisis": "darkred",
        "range_bound": "blue", "unknown": "gray",
    }
    c = regime_color.get(macro["regime"], "gray")

    cols = st.columns(4)
    cols[0].metric("VIX", f"{macro['vix']:.1f}" if macro["vix"] else "N/A")
    cols[1].metric("DXY", f"{macro['dxy']:.1f}" if macro["dxy"] else "N/A", macro["dxy_trend"])
    cols[2].metric("Regime", macro["regime"].replace("_", " ").title())
    cols[3].metric("Window", macro["macro_window"])
    st.markdown(f"### Regime: :{c}[{macro['regime'].replace('_', ' ').title()}] — {macro['macro_window']}")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Dynamic Weights (Stocks)**")
        for dim, w in macro["weights_stock"].items():
            st.text(f"{dim:20s} {w:.1%}  {'█' * int(w * 50)}")
    with col_r:
        st.markdown("**Dynamic Weights (Crypto)**")
        for dim, w in macro["weights_crypto"].items():
            st.text(f"{dim:20s} {w:.1%}  {'█' * int(w * 50)}")


# ── TAB 2: SCANNER ──
def tab_scanner():
    col1, col2, col3 = st.columns(3)
    with col1:
        universe = st.selectbox(
            "Universe",
            ["us_large", "us_tech", "all", "italy", "germany", "france", "uk", "spain", "crypto"],
            index=0,
        )
    with col2:
        custom = st.text_input("Custom tickers (comma-separated, overrides universe)", "")
    with col3:
        min_score = st.slider("Min score", 30, 80, 50, 5)

    if st.button("Scan", type="primary", use_container_width=True):
        results = cached_scan(universe, custom, min_score, "NORMAL")
        if not results:
            st.warning("No candidates found. Lower --min-score.")
            return

        st.session_state.last_scan_results = results
        df_data = []
        for r in results:
            dims = r.get("dimensions", [])
            df_data.append({
                "Ticker": r["symbol"],
                "Score": r["final_score"],
                "Pattern": r.get("pattern", ""),
                "Sector": r.get("sector", ""),
                "Price": r.get("price", 0),
                "W": _dim_score(dims, "wyckoff"),
                "VP": _dim_score(dims, "volume"),
                "PA": _dim_score(dims, "price"),
                "S": _dim_score(dims, "sentiment"),
                "F": _dim_score(dims, "fundamentals"),
            })
        df = pd.DataFrame(df_data)

        st.metric("Candidates", len(df), f"Scanned: {len(results)}")
        st.dataframe(df.sort_values("Score", ascending=False), hide_index=True, use_container_width=True,
                     column_config={"Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f")})

        c1, c2 = st.columns(2)
        with c1:
            st.download_button("Download CSV", df.to_csv(index=False), "scan_results.csv", "text/csv")
        with c2:
            universe_name = universe if not custom else "custom"
            if st.button("Add to Report", key="add_scan_report"):
                st.session_state.report_sections.append({
                    "type": "scanner",
                    "title": f"Scan: {universe_name}",
                    "data": {
                        "results": results,
                        "universe": universe_name,
                        "tickers_scanned": len(results),
                        "tickers_passed": len(results),
                        "min_score": min_score,
                    },
                })
                st.session_state.report_count += 1
                st.success(f"Scan added to report ({len(st.session_state.report_sections)} sections total)")


# ── TAB 3: STOCK ANALYZER ──
def tab_stock():
    ticker = st.text_input("Ticker", "AAPL").upper()
    if st.button("Analyze", type="primary"):
        result = cached_analyze(ticker)
        if result is None:
            st.error(f"Could not analyze '{ticker}'. Yahoo Finance may be rate-limiting — retry in a few minutes.")
            return

        score = result["final_score"]
        if score >= 70:
            verdict, vcolor = "Long-Term Investment", "green"
        elif score >= 50:
            verdict, vcolor = "Short-Term Speculation", "orange"
        else:
            verdict, vcolor = "Avoid / Wait", "red"

        dims = result.get("dimensions", [])
        cols = st.columns([2, 1])
        with cols[0]:
            st.markdown(f"### {ticker} — :{vcolor}[{verdict}]")
            st.metric("Composite Score", f"{score:.1f}", f"Sector: {result.get('sector', 'N/A')}")
            st.caption(f"Price: ${result.get('price', 0):.2f} — Pattern: {result.get('pattern', '')}")
        with cols[1]:
            st.metric("Wyckoff", _dim_score(dims, "wyckoff"))
            st.metric("Volume Profile", _dim_score(dims, "volume"))
            st.metric("Sentiment", _dim_score(dims, "sentiment"))

        st.markdown("#### Dimensions")
        dim_df = pd.DataFrame([
            {"Dimension": d["name"], "Score": d["score"], "Detail": d.get("detail", "")[:120]}
            for d in dims
        ])
        st.dataframe(dim_df, hide_index=True, use_container_width=True,
                     column_config={"Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f")})

        mods = result.get("modifiers", {})
        if mods:
            st.markdown("#### Modifiers")
            mdf = pd.DataFrame([
                {"Name": n, "Score": v.get("score") if isinstance(v, dict) else v,
                 "Detail": (v.get("detail", "") if isinstance(v, dict) else "")[:100]}
                for n, v in mods.items()
            ])
            st.dataframe(mdf, hide_index=True, use_container_width=True)

        inds = result.get("indicators", {})
        if inds:
            st.markdown("#### Indicators")
            cols_i = st.columns(len(inds))
            for i, (name, val) in enumerate(inds.items()):
                cols_i[i % len(cols_i)].metric(name.replace("_", " ").title(), val if val else "\u2014")

        if st.button("Add to Report", key="add_stock_report"):
            st.session_state.report_sections.append({
                "type": "stock",
                "title": ticker,
                "data": result,
            })
            st.session_state.report_count += 1
            st.success(f"{ticker} added to report ({len(st.session_state.report_sections)} sections total)")


# ── TAB 4: OPTIONS ──
def tab_options():
    ticker = st.text_input("Ticker", "DRAM", key="opt_ticker").upper()
    expiry = st.text_input("Expiry (YYYY-MM-DD, optional)", "")
    st.markdown("**Legs** (type | strike | qty | entry_premium)")
    legs_data = st.text_area(
        "One leg per line:  call 59 1 14.90",
        "put 45 -2 7.90\ncall 59 1 14.90",
        height=80,
    )

    if st.button("Analyze Options", type="primary"):
        legs = []
        for line in legs_data.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) == 4:
                legs.append({"type": parts[0], "strike": float(parts[1]),
                            "qty": int(parts[2]), "entry_premium": float(parts[3])})
        if not legs:
            st.error("Invalid legs format.")
            return

        exp = expiry if expiry.strip() else None
        result = analyze_options_position(ticker, legs, exp)
        if "error" in result:
            st.error(result["error"])
            return

        st.markdown(f"### {result['strategy_classification']}")
        st.caption(f"Spot: ${result['underlying_price']:.2f} — DTE: {result['dte']} — Expiry: {result['expiry']}")

        col_l, col_r = st.columns(2)
        with col_l:
            g = result["position_greeks"]
            st.metric("Delta", f"{g['total_delta']:.4f}")
            st.metric("Gamma", f"{g['total_gamma']:.4f}")
            st.metric("Theta", f"{g['total_theta']:.4f}")
            st.metric("Vega", f"{g['total_vega']:.4f}")
        with col_r:
            pnl = result["pnl"]
            st.metric("P&L", f"${pnl['total_pnl']:.2f}", f"{pnl['total_pnl_pct']:.1f}%")
            st.metric("Cost Basis", f"${pnl['cost_basis']:.2f}")
            st.metric("Breakevens", ", ".join(f"${b:.2f}" for b in result.get("breakevens", [])))

        st.markdown("#### Legs")
        st.dataframe(pd.DataFrame(result["legs"]), hide_index=True, use_container_width=True)

        payoff = result.get("payoff_scenarios", [])
        if payoff:
            spot = result["underlying_price"]
            prices = [p["price"] for p in payoff]
            pnls = [p["pnl"] for p in payoff]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=prices, y=pnls, mode="lines", name="P&L"))
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            fig.add_vline(x=spot, line_dash="dot", line_color="blue", annotation_text=f"Spot {spot}")
            fig.update_layout(title="Payoff Diagram", xaxis_title="Price at Expiry", yaxis_title="P&L ($)")
            st.plotly_chart(fig, use_container_width=True)

        recs = result.get("recommendations", [])
        if recs:
            st.markdown("#### Recommendations")
            for rec in recs:
                st.info(f"**{rec['type']}**: {rec['reason']}")

        if st.button("Add to Report", key="add_opt_report"):
            st.session_state.report_sections.append({
                "type": "options",
                "title": f"{ticker} Options",
                "data": result,
            })
            st.session_state.report_count += 1
            st.success(f"Options analysis added to report")


# ── TAB 5: REPORTS ──
def tab_reports():
    st.markdown("### Report Builder")
    st.caption("Add data from Scanner, Stock Analyzer, or Options tabs. Then preview and export here.")

    report_title = st.text_input("Report Title", st.session_state.report_title)
    st.session_state.report_title = report_title

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("Clear All Sections", type="secondary", use_container_width=True):
            st.session_state.report_sections = []
            st.session_state.report_count = 0
            st.rerun()
    with col_b:
        st.metric("Sections", len(st.session_state.report_sections))
    with col_c:
        if st.button("Append Macro Snapshot", use_container_width=True):
            st.session_state.macro_snapshot = cached_macro()
            st.success("Macro snapshot refreshed")

    if st.session_state.report_sections:
        st.markdown("#### Sections in report")
        for i, section in enumerate(st.session_state.report_sections):
            stype = section.get("type", "?").upper()
            title = section.get("title", "")
            col_x, col_y = st.columns([8, 1])
            with col_x:
                st.text(f"{i+1}. [{stype}] {title}")
            with col_y:
                if st.button("X", key=f"del_{i}"):
                    st.session_state.report_sections.pop(i)
                    st.session_state.report_count = max(0, st.session_state.report_count - 1)
                    st.rerun()

    if not st.session_state.report_sections:
        st.info("No sections yet. Go to Scanner/Stock/Options tabs and click 'Add to Report'.")
        return

    html = generate_report_html()
    st.markdown("---")
    st.markdown("### Preview")
    st.components.v1.html(html, height=600, scrolling=True)

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            "Download HTML Report",
            html,
            f"market_report_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
            "text/html",
            use_container_width=True,
        )
    with col_dl2:
        md_report = html.replace("<br>", "\n").replace("<p", "\n<p").replace("<h", "\n<h").replace("<table", "\n<table")
        import re
        md_report = re.sub(r"<[^>]+>", "", md_report)
        st.download_button(
            "Download as Text",
            md_report,
            f"market_report_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            "text/plain",
            use_container_width=True,
        )


# ── MAIN ──
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Macro Dashboard", "Market Scanner", "Stock Analyzer",
    "Options Analyzer", "Reports",
])
with tab1:
    tab_macro()
with tab2:
    tab_scanner()
with tab3:
    tab_stock()
with tab4:
    tab_options()
with tab5:
    tab_reports()
