#!/usr/bin/env python3
"""
Market Accumulation Scanner
Scans US/EU tickers through 5-dimension stock-crypto-analysis scoring.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import yfinance as yf

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"

# Import the 6-dimension sentiment engine
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from sentiment_engine import compute_sentiment as compute_sentiment_6d

# Cache SPX data for momentum comparison (shared across all tickers)
_SPX_HIST: pd.DataFrame | None = None

# Global flags for news and social sentiment
_FETCH_NEWS: bool = False
_WSB_HOTLIST: dict | None = None


def load_universe(name: str) -> list[dict]:
    if name == "us_large":
        return _load_csv(DATA_DIR / "us_tickers.csv", None)
    elif name == "us_tech":
        tech_tickers = {
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
            "AVGO", "QCOM", "TXN", "AMD", "INTC", "MU", "ADI", "NXPI",
            "MRVL", "ASML", "AMAT", "LRCX", "KLAC", "CRM", "NOW", "ADBE",
            "INTU", "NFLX", "DIS", "PYPL", "SQ", "SHOP", "SNOW", "DDOG",
            "CRWD", "PANW", "FTNT", "ZS", "NET", "OKTA", "ZM", "DOCU",
            "TEAM", "WDAY", "ADSK", "ROKU", "MRNA", "GILD", "REGN",
            "VRTX", "ILMN", "ISRG", "ALGN", "COST", "SBUX", "CMG",
            "BKNG", "ABNB", "UBER", "DASH", "NKE", "LULU", "ROST",
            "MELI", "JD", "BABA", "TCOM", "SPOT", "TTD", "PINS",
            "SNAP", "MTCH", "CRSP", "NTLA", "BEAM", "COIN",
            "MSTR", "RIOT", "MAR", "RCL", "CCL", "NCLH", "EXPE",
        }
        return _load_csv(DATA_DIR / "us_tickers.csv", tech_tickers)
    elif name == "italy":
        return _load_csv(DATA_DIR / "europe_tickers.csv", None, market="Italy")
    elif name == "germany":
        return _load_csv(DATA_DIR / "europe_tickers.csv", None, market="Germany")
    elif name == "france":
        return _load_csv(DATA_DIR / "europe_tickers.csv", None, market="France")
    elif name == "uk":
        return _load_csv(DATA_DIR / "europe_tickers.csv", None, market="UK")
    elif name == "spain":
        return _load_csv(DATA_DIR / "europe_tickers.csv", None, market="Spain")
    elif name == "all":
        us = _load_csv(DATA_DIR / "us_tickers.csv", None)
        eu = _load_csv(DATA_DIR / "europe_tickers.csv", None)
        return us + eu
    else:
        raise ValueError(f"Unknown universe: {name}")


def _load_csv(path: Path, allowed_symbols: set | None, market: str | None = None) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if allowed_symbols and row["symbol"] not in allowed_symbols:
                continue
            if market and row.get("market", "") != market:
                continue
            rows.append(row)
    return rows


def _get_spx_hist() -> pd.DataFrame:
    """Fetch SPX history once and cache globally."""
    global _SPX_HIST
    if _SPX_HIST is None:
        try:
            spx = yf.Ticker("^GSPC")
            _SPX_HIST = spx.history(period="1y")
        except Exception:
            _SPX_HIST = pd.DataFrame()
    return _SPX_HIST


def parse_custom_tickers(ticker_str: str) -> list[dict]:
    symbols = [t.strip().upper() for t in ticker_str.split(",") if t.strip()]
    return [{"symbol": s, "name": s, "suffix": "", "market": "CUSTOM"} for s in symbols]


def compute_wyckoff(hist, _info) -> tuple[int, str]:
    if hist.empty or len(hist) < 50:
        return 20, "Insufficient data"

    score = 20
    details = []
    price = float(hist["Close"].iloc[-1])
    high_1y = hist["High"].max()
    low_1y = hist["Low"].min()
    pos = ((price - low_1y) / (high_1y - low_1y)) * 100 if (high_1y - low_1y) > 0 else 50

    if pos < 30:
        score += 15
        details.append("Bottom 30% of 1Y range (+15)")
    elif pos < 60:
        score += 30
        details.append("Accumulation zone 30-60% of range (+30)")
    else:
        details.append("Upper 40% of range (+0)")

    recent = hist.tail(60)
    if len(recent) >= 20:
        highs = recent["High"].values
        lows = recent["Low"].values
        half = len(highs) // 2
        if highs[-1] > highs[half] and lows[-1] > lows[half]:
            score += 40
            details.append("HH/HL pattern (Markup) (+40)")
        elif highs[-1] < highs[half] and lows[-1] < lows[half]:
            score -= 20
            details.append("LH/LL pattern (Markdown) (-20)")

    if len(hist) >= 50:
        ma50 = float(hist["Close"].rolling(50).mean().iloc[-1])
        ma200_val = float(hist["Close"].rolling(200).mean().iloc[-1]) if len(hist) >= 200 else None
        if ma200_val and ma50 > ma200_val:
            score += 15
            details.append(f"MA50 > MA200 (+15)")

    if len(hist) >= 30:
        recent_30 = hist.tail(30)
        low_30 = recent_30["Low"].min()
        low_idx = recent_30["Low"].idxmin()
        if low_idx and low_idx < hist.index[-5]:
            if price > low_30 * 1.05:
                score += 30
                details.append("Spring detected (+30)")

    if len(hist) >= 90:
        vol_older = hist.tail(90).head(60)["Volume"].mean()
        vol_recent = hist.tail(30)["Volume"].mean()
        if vol_recent < vol_older * 0.8:
            score += 15
            details.append("Volume decreasing (absorption) (+15)")

    return min(score, 100), " | ".join(details)


def compute_volume_profile(hist) -> tuple[int, str]:
    if hist.empty or len(hist) < 20:
        return 10, "Insufficient data"

    score = 10
    details = []
    price = float(hist["Close"].iloc[-1])
    hist_range = hist["High"].max() - hist["Low"].min()
    n_bins = 20
    bin_w = hist_range / n_bins if hist_range > 0 else 1
    hist = hist.copy()
    hist["bin"] = ((hist["Close"] - hist["Low"].min()) / bin_w).astype(int).clip(0, n_bins - 1)
    vol_by_bin = hist.groupby("bin")["Volume"].sum()
    poc_bin = vol_by_bin.idxmax()
    poc_price = hist["Low"].min() + (poc_bin + 0.5) * bin_w
    total_vol = vol_by_bin.sum()
    cum, va_bins = 0, []
    for b, v in vol_by_bin.sort_values(ascending=False).items():
        cum += v
        va_bins.append(b)
        if cum / total_vol >= 0.7:
            break
    val = hist["Low"].min() + min(va_bins) * bin_w
    vah = hist["Low"].min() + (max(va_bins) + 1) * bin_w

    if val <= price <= vah:
        score += 20
        details.append(f"Price inside VA ({val:.2f}-{vah:.2f}) (+20)")
    elif price < val:
        score += 25
        details.append(f"Price below VAL ({val:.2f}) (+25)")
    else:
        score += 15
        details.append(f"Price above VAH ({vah:.2f}) (+15)")

    if abs(price - poc_price) / poc_price < 0.05:
        score += 10
        details.append(f"Near VPOC ${poc_price:.2f} (+10)")

    if len(hist) >= 21:
        vol_ratio = float(hist["Volume"].iloc[-1]) / float(hist["Volume"].iloc[-21:].mean())
        if vol_ratio > 2.0:
            score += 15
            details.append(f"Volume ratio {vol_ratio:.1f}x (+15)")
        elif vol_ratio > 1.0:
            score += 10
            details.append(f"Volume ratio {vol_ratio:.1f}x (+10)")

    pos_in_range = ((price - hist["Low"].min()) / hist_range) * 100 if hist_range > 0 else 50
    if 40 < pos_in_range < 60:
        score += 15
        details.append("D-Profile shape (balanced) (+15)")

    return min(score, 100), " | ".join(details)


def compute_price_action(hist) -> tuple[int, str]:
    if hist.empty or len(hist) < 20:
        return 10, "Insufficient data"

    score = 10
    details = []

    if len(hist) >= 15:
        delta = hist["Close"].diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ma_up = up.ewm(com=13).mean()
        ma_down = down.ewm(com=13).mean()
        rsi = 100 - (100 / (1 + ma_up / ma_down))
        rsi_val = float(rsi.iloc[-1])
        if 40 <= rsi_val <= 60:
            score += 10
            details.append(f"RSI {rsi_val:.0f} (neutral) (+10)")
        elif 30 <= rsi_val < 40:
            score += 20
            details.append(f"RSI {rsi_val:.0f} (oversold zone) (+20)")
        elif rsi_val < 30:
            score += 10
            details.append(f"RSI {rsi_val:.0f} (extreme) (+10)")
        else:
            details.append(f"RSI {rsi_val:.0f} (+0)")

    hist = hist.copy()
    hist["ema25"] = hist["Close"].ewm(span=25).mean()
    if len(hist) >= 30:
        slope = (hist["ema25"].iloc[-1] - hist["ema25"].iloc[-5]) / hist["ema25"].iloc[-5]
        if slope > 0:
            score += 15
            details.append("25ema rising (+15)")
        else:
            details.append("25ema flat/falling (+0)")

    last_20 = hist.tail(20)
    vpa_net = 0
    for i in range(1, len(last_20)):
        bar = last_20.iloc[i]
        prev = last_20.iloc[i - 1]
        vol = float(bar["Volume"])
        avg = float(last_20["Volume"].mean())
        vr = vol / avg if avg > 0 else 1
        up = float(bar["Close"]) > float(prev["Close"])
        wide = (float(bar["High"]) - float(bar["Low"])) > (float(prev["High"]) - float(prev["Low"])) * 1.2
        high_vol = vr > 1.5
        if up and high_vol:
            vpa_net += 1
        elif not up and high_vol:
            vpa_net -= 1
        if up and vr < 0.6 and wide:
            vpa_net -= 1
        elif not up and vr < 0.6 and wide:
            vpa_net += 1

    if vpa_net > 2:
        score += 20
        details.append(f"VPA bullish ({vpa_net}) (+20)")
    elif vpa_net > 0:
        details.append(f"VPA mildly bullish ({vpa_net}) (+0)")

    return min(score, 100), " | ".join(details)


def compute_sentiment(info) -> tuple[int, str]:
    score = 25
    details = []

    si = info.get("shortPercentOfFloat")
    if si is not None:
        if si > 0.20:
            score += 35
            details.append(f"SI {si*100:.1f}% > 20% (+35)")
        elif si > 0.10:
            score += 20
            details.append(f"SI {si*100:.1f}% 10-20% (+20)")
        else:
            details.append(f"SI {si*100:.1f}% < 10% (+0)")
    else:
        details.append("SI N/A (+0)")

    inst = info.get("heldPercentInstitutions")
    if inst is not None and inst > 0.50:
        score += 15
        details.append(f"Inst {inst*100:.0f}% > 50% (+15)")

    dtc = info.get("shortRatio")
    if dtc is not None:
        if dtc > 7:
            score += 25
            details.append(f"DTC {dtc:.1f} > 7 (+25)")
        elif dtc > 3:
            score += 15
            details.append(f"DTC {dtc:.1f} > 3 (+15)")

    return min(score, 100), " | ".join(details)


def compute_fundamentals(info) -> tuple[int, str]:
    score = 10
    details = []

    pe = info.get("trailingPE")
    if pe is not None and pe > 0:
        if pe < 15:
            score += 30
            details.append(f"P/E {pe:.1f} < 15 (+30)")
        elif pe < 25:
            score += 15
            details.append(f"P/E {pe:.1f} < 25 (+15)")
        else:
            details.append(f"P/E {pe:.1f} (+0)")
    else:
        details.append("P/E N/A (+0)")

    rev = info.get("revenueGrowth")
    if rev is not None and rev > 0:
        score += 20
        details.append(f"Rev growth {rev*100:.1f}% (+20)")
    elif rev is not None:
        details.append(f"Rev growth {rev*100:.1f}% (+0)")

    margins = info.get("profitMargins")
    if margins is not None and margins > 0:
        score += 20
        details.append(f"Margins {margins*100:.1f}% (+20)")

    de = info.get("debtToEquity")
    if de is not None:
        if de < 0.5:
            score += 25
            details.append(f"D/E {de:.2f} < 0.5 (+25)")
        elif de < 1.0:
            score += 15
            details.append(f"D/E {de:.2f} < 1.0 (+15)")

    mcap = info.get("marketCap")
    if mcap is not None and mcap > 10e9:
        score += 10
        details.append(f"MCap ${mcap/1e9:.1f}B > $10B (+10)")

    return min(score, 100), " | ".join(details)


def identify_pattern(wyckoff_score, volprof_score, pa_score, sentiment_score, fundamentals_score, info, wyckoff_detail: str):
    si = info.get("shortPercentOfFloat", 0) or 0
    if wyckoff_score >= 70 and "Spring" in wyckoff_detail:
        return "Accumulation Spring"
    if volprof_score >= 70 and fundamentals_score >= 60:
        return "D-Profile Value Zone"
    if pa_score >= 70 and sentiment_score >= 50:
        return "P-Profile Breakout"
    if sentiment_score >= 70 and si > 0.20:
        return "Squeeze Setup"
    if wyckoff_score >= 65 and fundamentals_score >= 60:
        return "Golden Cross Accumulation"
    if volprof_score < 30:
        return "b-Profile Trap"
    return "Mixed / No dominant pattern"


def process_ticker(ticker_dict: dict) -> dict | None:
    symbol = ticker_dict["symbol"]
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        hist = t.history(period="1y")
        if hist.empty:
            return None

        price = info.get("currentPrice") or float(hist["Close"].iloc[-1])
        if price is None or price < 1.0:
            return None

        wyckoff_score, wyckoff_d = compute_wyckoff(hist, info)
        volprof_score, volprof_d = compute_volume_profile(hist)
        pa_score, pa_d = compute_price_action(hist)
        fundamentals_score, fundamentals_d = compute_fundamentals(info)

        # 8-dimension sentiment engine (news + social + traditional)
        spx_hist = _get_spx_hist()
        sentiment_score, sentiment_d, sentiment_subs = compute_sentiment_6d(
            t, info, hist, spx_hist,
            wsb_hotlist=_WSB_HOTLIST,
            fetch_news=_FETCH_NEWS,
        )

        final = (
            wyckoff_score * 0.25 + volprof_score * 0.20 +
            pa_score * 0.20 + sentiment_score * 0.15 +
            fundamentals_score * 0.20
        )

        pattern = identify_pattern(
            wyckoff_score, volprof_score, pa_score,
            sentiment_score, fundamentals_score, info, wyckoff_d
        )

        return {
            "symbol": symbol,
            "name": ticker_dict["name"],
            "market": ticker_dict.get("market", "US"),
            "price": round(price, 2),
            "final_score": round(final, 1),
            "wyckoff": wyckoff_score,
            "volprof": volprof_score,
            "pa": pa_score,
            "sentiment": sentiment_score,
            "fundamentals": fundamentals_score,
            "pattern": pattern,
            "wyckoff_detail": wyckoff_d,
            "volprof_detail": volprof_d,
            "pa_detail": pa_d,
            "sentiment_detail": sentiment_d,
            "fundamentals_detail": fundamentals_d,
            # New: sub-dimension breakdown
            "sentiment_sub_si": sentiment_subs.get("short_interest"),
            "sentiment_sub_options": sentiment_subs.get("options"),
            "sentiment_sub_insider": sentiment_subs.get("insider"),
            "sentiment_sub_retail": sentiment_subs.get("retail"),
            "sentiment_sub_institutional": sentiment_subs.get("institutional"),
            "sentiment_sub_momentum": sentiment_subs.get("momentum"),
        }
    except Exception:
        return None


def print_table(results: list[dict], top_n: int):
    print(f"\n{'#' * 100}")
    print(f"  Top {top_n} Candidates")
    print(f"{'#' * 100}")
    print(f"{'#':<4} {'Ticker':<8} {'Name':<30} {'Score':<7} {'WYCK':<6} {'VP':<5} {'PA':<5} {'SENT':<6} {'FUND':<5} {'Pattern':<30}")
    print(f"{'─' * 4} {'─' * 8} {'─' * 30} {'─' * 7} {'─' * 6} {'─' * 5} {'─' * 5} {'─' * 6} {'─' * 5} {'─' * 30}")

    for i, r in enumerate(results[:top_n], 1):
        name = r["name"][:28]
        print(f"{i:<4} {r['symbol']:<8} {name:<30} {r['final_score']:<7} {r['wyckoff']:<6} {r['volprof']:<5} {r['pa']:<5} {r['sentiment']:<6} {r['fundamentals']:<5} {r['pattern']:<30}")


def generate_csv(results: list[dict], output_dir: str | Path) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(str(output_dir), f"scan_report_{ts}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "symbol", "name", "market", "price", "final_score",
                     "wyckoff", "volprof", "pa", "sentiment", "fundamentals", "pattern",
                     "sent_si", "sent_options", "sent_insider", "sent_retail",
                     "sent_institutional", "sent_momentum"])
        for i, r in enumerate(results, 1):
            w.writerow([i, r["symbol"], r["name"], r["market"], r["price"],
                        r["final_score"], r["wyckoff"], r["volprof"], r["pa"],
                        r["sentiment"], r["fundamentals"], r["pattern"],
                        r.get("sentiment_sub_si", ""), r.get("sentiment_sub_options", ""),
                        r.get("sentiment_sub_insider", ""), r.get("sentiment_sub_retail", ""),
                        r.get("sentiment_sub_institutional", ""), r.get("sentiment_sub_momentum", "")])
    return path


def generate_html(results: list[dict], output_dir: str | Path, universe_name: str, total_scanned: int) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(str(output_dir), f"scan_report_{ts}.html")

    def color(val, max_val=100):
        ratio = val / max_val
        if ratio >= 0.7:
            return f"hsl({120 * ratio}, 70%, 85%)"
        elif ratio >= 0.5:
            return f"hsl({120 * ratio}, 50%, 90%)"
        else:
            return f"hsl(0, 60%, 92%)"

    rows_html = ""
    for i, r in enumerate(results, 1):
        rows_html += f"""<tr>
            <td>{i}</td>
            <td><strong>{r['symbol']}</strong></td>
            <td>{r['name'][:30]}</td>
            <td style="background:{color(r['final_score'])}"><strong>{r['final_score']}</strong></td>
            <td style="background:{color(r['wyckoff'])}">{r['wyckoff']}</td>
            <td style="background:{color(r['volprof'])}">{r['volprof']}</td>
            <td style="background:{color(r['pa'])}">{r['pa']}</td>
            <td style="background:{color(r['sentiment'])}">{r['sentiment']}</td>
            <td style="background:{color(r['fundamentals'])}">{r['fundamentals']}</td>
            <td>{r['pattern']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Market Accumulation Scan - {ts}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; background: #f8f9fa; }}
h1 {{ color: #1a1a2e; }}
.subtitle {{ color: #666; margin-bottom: 20px; }}
table {{ border-collapse: collapse; width: 100%; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
th {{ background: #1a1a2e; color: white; padding: 12px 8px; text-align: left; font-size: 13px; }}
td {{ padding: 8px; border-bottom: 1px solid #eee; font-size: 13px; }}
tr:hover {{ opacity: 0.9; }}
.summary {{ background: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
.summary span {{ margin-right: 30px; }}
.score-dist {{ margin: 20px 0; height: 40px; display: flex; border-radius: 4px; overflow: hidden; }}
.dist-bar {{ display: flex; align-items: center; justify-content: center; color: white; font-size: 11px; font-weight: bold; }}
</style>
</head>
<body>
<h1>📊 Market Accumulation Scan</h1>
<div class="summary">
    <span><strong>Universe:</strong> {universe_name}</span>
    <span><strong>Scanned:</strong> {total_scanned}</span>
    <span><strong>Candidates:</strong> {len(results)}</span>
    <span><strong>Generated:</strong> {ts}</span>
</div>
<div class="score-dist">
    {''.join(f'<div class="dist-bar" style="width:{sum(1 for r in results if r["final_score"] >= (i*10))/max(len(results),1)*100:.1f}%;background:hsl({i*12},60%,50%)">{sum(1 for r in results if r["final_score"] >= (i*10))}</div>' for i in range(10, 0, -1)) if results else ''}
</div>
<table>
<tr>
    <th>#</th><th>Ticker</th><th>Name</th><th>Score</th><th>WYCK</th><th>VP</th><th>PA</th><th>SENT</th><th>FUND</th><th>Pattern</th>
</tr>
{rows_html}
</table>
<p style="color:#999;font-size:12px;margin-top:10px;">Generated by market-accumulation-scanner</p>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def main():
    parser = argparse.ArgumentParser(description="Market Accumulation Scanner")
    parser.add_argument("--universe", default="us_large", help="Universe name")
    parser.add_argument("--tickers", help="Custom comma-separated ticker list")
    parser.add_argument("--min-score", type=float, default=50, help="Minimum score")
    parser.add_argument("--top", type=int, default=15, help="Top N to show")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size")
    parser.add_argument("--batch-sleep", type=float, default=1.0, help="Seconds between batches")
    parser.add_argument("--list-tickers", action="store_true",
                        help="Output ticker symbols as JSON array and exit")
    parser.add_argument("--json-output", action="store_true",
                        help="Output results as JSON array to stdout")
    parser.add_argument("--fetch-news", action="store_true",
                        help="Fetch Finviz news headlines for web news sentiment (slower)")
    parser.add_argument("--wsb-hotlist",
                        help="Path to JSON file with WSB hotlist from wallstreetbets-pump-detect")
    args = parser.parse_args()

    # Set global flags for sentiment engine
    global _FETCH_NEWS, _WSB_HOTLIST
    _FETCH_NEWS = args.fetch_news
    if args.wsb_hotlist:
        try:
            with open(args.wsb_hotlist, "r") as f:
                _WSB_HOTLIST = json.load(f)
            log.info("Loaded WSB hotlist: %d tickers", len(_WSB_HOTLIST))
        except Exception as e:
            log.warning("Failed to load WSB hotlist: %s", e)

    if args.tickers:
        universe = parse_custom_tickers(args.tickers)
        universe_name = "custom"
    else:
        universe = load_universe(args.universe)
        universe_name = args.universe

    if args.list_tickers:
        tickers = [t["symbol"] for t in universe]
        print(json.dumps(tickers))
        return

    if args.output_dir == ".":
        output_dir = SKILL_DIR / "reports" / universe_name
    else:
        output_dir = Path(args.output_dir)

    total = len(universe)
    if not args.json_output:
        print(f"\n📋 Scanning {universe_name} — {total} tickers...")
        print(f"   Batch: {args.batch_size} | Sleep: {args.batch_sleep}s | Min score: {args.min_score}")

    results = []
    failures = 0
    t0 = time.time()

    for i in range(0, total, args.batch_size):
        batch = universe[i:i + args.batch_size]
        for t_dict in batch:
            result = process_ticker(t_dict)
            if result:
                results.append(result)
            else:
                failures += 1

        if not args.json_output:
            elapsed = time.time() - t0
            pct = min(100, (i + len(batch)) / total * 100)
            rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
            eta = (total - i - len(batch)) / rate if rate > 0 else 0
            sys.stdout.write(f"\r   Progress: {min(total, i + len(batch))}/{total} ({pct:.0f}%) | "
                             f"Found: {len(results)} | "
                            f"Rate: {rate:.1f} tickers/s | ETA: {eta:.0f}s   ")
            sys.stdout.flush()

        if i + len(batch) < total:
            time.sleep(args.batch_sleep)

    elapsed = time.time() - t0
    if not args.json_output:
        print(f"\n\n✅ Scan completed in {elapsed:.0f}s")
        print(f"   Tickers processed: {total} | Failures: {failures} | Candidates: {len(results)}")

    results.sort(key=lambda r: r["final_score"], reverse=True)
    filtered = [r for r in results if r["final_score"] >= args.min_score]

    if not filtered:
        if args.json_output:
            print("[]")
        else:
            print(f"\n⚠ No candidates found with score >= {args.min_score}")
            print("   Try lowering the threshold with --min-score")
        return

    if args.json_output:
        print(json.dumps(filtered, indent=2, default=str))
        return

    print(f"\n   Candidates with score >= {args.min_score}: {len(filtered)}")

    print_table(filtered, args.top)

    csv_path = generate_csv(filtered, output_dir)
    print(f"\n📄 CSV report: {csv_path}")

    html_path = generate_html(filtered, output_dir, universe_name, total)
    print(f"📄 HTML report: {html_path}")

    print(f"\n{'─' * 60}")
    print(f"  TOP {min(3, len(filtered))} CANDIDATES FOR DEEP DIVE")
    print(f"{'─' * 60}")
    for i, r in enumerate(filtered[:3], 1):
        si = r.get("sentiment_sub_si")
        op = r.get("sentiment_sub_options")
        ins = r.get("sentiment_sub_insider")
        sub_sent = f" SI={si}" if si else ""
        sub_sent += f" OPT={op}" if op else ""
        sub_sent += f" INS={ins}" if ins else ""
        print(f"\n  #{i}: {r['symbol']} ({r['name']}) — Score: {r['final_score']}")
        print(f"      Pattern: {r['pattern']}")
        print(f"      Wyckoff: {r['wyckoff']} | VP: {r['volprof']} | PA: {r['pa']} | Sent: {r['sentiment']}{sub_sent} | Fund: {r['fundamentals']}")
        print(f"      → Load stock-crypto-analysis on ${r['symbol']} for full verdict")


if __name__ == "__main__":
    main()
