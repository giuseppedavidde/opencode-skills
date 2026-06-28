"""Market scanner orchestrator: multi-dimensional ticker scoring engine."""

from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from trading_mcp.analysis.wyckoff import compute_wyckoff, compute_6clue_test
from trading_mcp.analysis.volume_profile import compute_volume_profile
from trading_mcp.analysis.price_action import compute_price_action, compute_multiframe_trend
from trading_mcp.analysis.sentiment import compute_sentiment
from trading_mcp.analysis.fundamentals import compute_fundamentals, compute_competitive_positioning
from trading_mcp.analysis.weis_wave import compute_sot_weis_wave
from trading_mcp.analysis.squeeze_play import compute_squeeze_play
from trading_mcp.analysis.earnings import compute_earnings_surprise
from trading_mcp.analysis.indicators import (
    compute_bollinger,
    compute_candlestick_advanced,
    compute_candlestick_patterns,
    compute_fibonacci,
    compute_ichimoku,
    compute_obv,
    compute_point_figure,
    compute_psychology_advanced,
    compute_psychology_score,
    compute_risk_reward,
    compute_support_resistance,
)
from trading_mcp.analysis.sentiment_6d import compute_sentiment_6d, earnings_proximity_adjustment


_SPX_HIST: pd.DataFrame | None = None
_WSB_HOTLIST: dict | None = None
_FETCH_NEWS: bool = False


def set_fetch_news(enabled: bool) -> None:
    global _FETCH_NEWS
    _FETCH_NEWS = enabled


def load_universe(name: str, tickers_dir: str) -> list[dict[str, str]]:
    """Load ticker universe from CSV files.

    Args:
        name: Universe name (us_large, us_tech, italy, germany, france, uk, spain, all, crypto).
        tickers_dir: Path to directory containing ticker CSV files.
    """
    data_dir = Path(tickers_dir)

    def _load_csv(path: Path, market: str | None = None) -> list[dict[str, str]]:
        rows = []
        if not path.exists():
            return rows
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if market and row.get("market", "") != market:
                    continue
                rows.append(dict(row))
        return rows

    if name == "crypto":
        return _load_crypto_csv(data_dir)
    if name == "all":
        us_list = _load_csv(data_dir / "us_tickers.csv")
        eu_list = _load_all_european(data_dir)
        return us_list + eu_list
    if name == "italy":
        return _load_csv(data_dir / "italy_tickers.csv", "Italy") or _load_csv(data_dir / "europe_tickers.csv", "Italy")
    if name == "germany":
        return _load_csv(data_dir / "germany_tickers.csv", "Germany") or _load_csv(data_dir / "europe_tickers.csv", "Germany")
    if name == "france":
        return _load_csv(data_dir / "france_tickers.csv", "France") or _load_csv(data_dir / "europe_tickers.csv", "France")
    if name == "uk":
        return _load_csv(data_dir / "uk_tickers.csv", "UK") or _load_csv(data_dir / "europe_tickers.csv", "UK")
    if name == "spain":
        return _load_csv(data_dir / "spain_tickers.csv", "Spain") or _load_csv(data_dir / "europe_tickers.csv", "Spain")
    if name == "us_tech":
        tech = _load_csv(data_dir / "us_tech_tickers.csv")
        if tech:
            return tech
        return _load_csv(data_dir / "us_tickers.csv", "Information Technology")
    return _load_csv(data_dir / "us_tickers.csv")


def _load_all_european(data_dir: Path) -> list[dict[str, str]]:
    eu_files = ["italy_tickers.csv", "germany_tickers.csv", "france_tickers.csv", "uk_tickers.csv", "spain_tickers.csv"]
    rows: list[dict[str, str]] = []
    for filename in eu_files:
        filepath = data_dir / filename
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows.extend(dict(row) for row in reader)
    if not rows and (data_dir / "europe_tickers.csv").exists():
        with open(data_dir / "europe_tickers.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows.extend(dict(row) for row in reader)
    return rows


def _load_crypto_csv(data_dir: Path) -> list[dict[str, str]]:
    path = data_dir / "crypto_tickers.csv"
    rows = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = str(row["symbol"]).strip()
            if not symbol.endswith("-USD"):
                symbol = f"{symbol}-USD"
            rows.append({
                "symbol": symbol,
                "name": str(row.get("name", "")).strip(),
                "market": "CRYPTO",
            })
    return rows


def parse_custom_tickers(ticker_str: str) -> list[dict[str, str]]:
    """Parse comma-separated ticker list."""
    symbols = [t.strip().upper() for t in ticker_str.split(",") if t.strip()]
    return [{"symbol": s, "name": s, "market": "CUSTOM"} for s in symbols]


def _get_spx_hist() -> pd.DataFrame:
    global _SPX_HIST
    if _SPX_HIST is None:
        try:
            spx = yf.Ticker("^GSPC")
            _SPX_HIST = spx.history(period="1y")
        except Exception:
            _SPX_HIST = pd.DataFrame()
    if _SPX_HIST is not None and not _SPX_HIST.empty:
        return _SPX_HIST.copy()
    return pd.DataFrame()


def compute_crypto_analysis(ticker_obj: yf.Ticker, hist: pd.DataFrame) -> tuple[int, str]:
    """Alert-Predict-Confirm framework for crypto."""
    if hist.empty or len(hist) < 50:
        return 50, "Insufficient crypto data"

    score = 50
    details = []
    close = hist["Close"]
    volume = hist["Volume"]

    alert_bullish = alert_bearish = False
    predict_bullish = predict_bearish = False
    confirm_bullish = confirm_bearish = False

    if len(close) >= 15:
        delta = close.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ma_up = up.ewm(com=13).mean()
        ma_down = down.ewm(com=13).mean()
        rsi = 100.0 - (100.0 / (1.0 + ma_up / ma_down))
        rsi_now = float(rsi.iloc[-1])
        rsi_prev = float(rsi.iloc[-5])
        if rsi_now < 30 and rsi_prev < 35:
            alert_bullish = True
            details.append(f"ALERT: RSI {rsi_now:.0f} oversold")
        elif rsi_now > 70 and rsi_prev > 65:
            alert_bearish = True
            details.append(f"ALERT: RSI {rsi_now:.0f} overbought")

    if len(close) >= 26:
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
            predict_bullish = True
            details.append("PREDICT: MACD bullish crossover")
        elif macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] >= signal.iloc[-2]:
            predict_bearish = True
            details.append("PREDICT: MACD bearish crossover")

    if len(volume) >= 20:
        vol_ma = volume.rolling(20).mean()
        vol_now = float(volume.iloc[-1])
        vol_avg = float(vol_ma.iloc[-1])
        if vol_now > vol_avg * 1.5 and close.iloc[-1] > close.iloc[-2]:
            confirm_bullish = True
            details.append(f"CONFIRM: Volume {vol_now/vol_avg:.1f}x + price up")
        elif vol_now > vol_avg * 1.5 and close.iloc[-1] < close.iloc[-2]:
            confirm_bearish = True
            details.append(f"CONFIRM: Volume {vol_now/vol_avg:.1f}x + price down")

    bullish_count = sum([alert_bullish, predict_bullish, confirm_bullish])
    bearish_count = sum([alert_bearish, predict_bearish, confirm_bearish])

    if bullish_count == 3:
        score += 35
        details.append("ALL BULLISH (+35)")
    elif bullish_count == 2:
        score += 20
        details.append("2/3 bullish (+20)")
    elif bearish_count == 3:
        score -= 30
        details.append("ALL BEARISH (-30)")
    elif bearish_count == 2:
        score -= 15
        details.append("2/3 bearish (-15)")
    else:
        details.append(f"Mixed ({bullish_count}B/{bearish_count}S)")

    return min(100, max(0, score)), " | ".join(details)


def identify_pattern(
    wyckoff_score: int,
    volprof_score: int,
    pa_score: int,
    sentiment_score: int,
    fundamentals_score: int,
    info: dict[str, Any],
    wyckoff_detail: str,
    sentiment_subs: dict | None = None,
) -> str:
    """Identify dominant accumulation/distribution pattern."""
    si = float(info.get("shortPercentOfFloat", 0) or 0)
    web_news = sentiment_subs.get("web_news") if sentiment_subs else None
    social = sentiment_subs.get("social_media") if sentiment_subs else None

    if wyckoff_score >= 70 and "Spring" in wyckoff_detail:
        return "Accumulation Spring"
    if volprof_score >= 70 and fundamentals_score >= 60:
        return "D-Profile Value Zone"
    if volprof_score >= 70 and pa_score >= 70 and social is not None and social >= 60:
        return "P-Profile Breakout"
    if social is not None and social >= 70 and pa_score >= 50:
        return "WSB Hype Confirmation"
    if web_news is not None and web_news >= 80 and wyckoff_score <= 70 and 40 <= pa_score <= 60:
        return "News Catalyst Buildup"
    if pa_score >= 70 and sentiment_score >= 50:
        return "P-Profile Breakout"
    if sentiment_score >= 70 and si > 0.20:
        return "Squeeze Setup"
    if wyckoff_score >= 65 and fundamentals_score >= 60:
        return "Golden Cross Accumulation"
    if volprof_score < 30:
        return "b-Profile Trap"
    return "Mixed / No dominant pattern"


def apply_macro_regime(results: list[dict], regime: str = "NORMAL") -> list[dict]:
    """Apply post-aggregation macro regime multiplier with sector awareness."""
    defensive_sectors = {"Utilities", "Consumer Defensive", "Healthcare", "Real Estate"}
    cyclical_sectors = {"Energy", "Financial Services", "Consumer Cyclical",
                        "Industrials", "Basic Materials", "Communication Services"}

    regime_upper = regime.upper()
    for r in results:
        sector = r.get("sector", "")
        base = r["final_score"]

        if regime_upper == "FULL":
            r["final_score"] = min(100.0, round(base * 1.08, 1))
        elif regime_upper == "SELECTIVE":
            if sector in defensive_sectors:
                r["final_score"] = min(100.0, round(base * 1.05, 1))
            elif sector in cyclical_sectors:
                r["final_score"] = round(base * 0.90, 1)
        elif regime_upper == "DEFENSIVE":
            r["final_score"] = min(60.0, round(base * 0.85, 1))

    return results


def process_ticker(ticker_dict: dict[str, str]) -> dict[str, Any] | None:
    """Process a single stock ticker through all analysis dimensions."""
    symbol = ticker_dict["symbol"]
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        hist = t.history(period="1y")
        if hist.empty:
            return None

        price = info.get("currentPrice") or (float(hist["Close"].iloc[-1]) if not hist.empty else None)
        if price is None or float(price) < 1.0:
            return None
        price = float(price)

        wyckoff_score, wyckoff_d = compute_wyckoff(hist, info)
        volprof_score, volprof_d = compute_volume_profile(hist)
        pa_score, pa_d = compute_price_action(hist)
        fundamentals_score, fundamentals_d = compute_fundamentals(info)
        competitive_score, competitive_d = compute_competitive_positioning(info)

        mtf_score, mtf_d = compute_multiframe_trend(hist)
        sot_score, sot_d = compute_sot_weis_wave(hist)
        squeeze_score, squeeze_d = compute_squeeze_play(t, info, hist)
        es_tuple = compute_earnings_surprise(t)
        earnings_surprise_score = es_tuple[0] if es_tuple else None
        earnings_surprise_d = es_tuple[1] if es_tuple else "N/A"
        clue6_score, clue6_d = compute_6clue_test(hist, info)

        candle_score, candle_d = compute_candlestick_patterns(hist)
        fib_score, fib_d = compute_fibonacci(hist)
        bb_score, bb_d = compute_bollinger(hist)
        obv_score, obv_d = compute_obv(hist)
        sr_score, sr_d = compute_support_resistance(hist)
        psych_score, psych_d = compute_psychology_score(hist)

        ichi_score, ichi_d = compute_ichimoku(hist)
        candle_adv_score, candle_adv_d = compute_candlestick_advanced(hist)
        risk_reward_score, risk_reward_d = compute_risk_reward(hist, price)
        psych_adv_score, psych_adv_d = compute_psychology_advanced(hist)
        pf_score, pf_d = compute_point_figure(hist)

        spx_hist = _get_spx_hist()
        sentiment_score, sentiment_d, sentiment_subs = compute_sentiment_6d(
            t, info, hist, spx_hist,
            wsb_hotlist=_WSB_HOTLIST,
            fetch_news=_FETCH_NEWS,
        )

        earnings_adj = None
        earnings_dates = info.get("earningsDate")
        if earnings_dates:
            try:
                next_earn = earnings_dates[0] if isinstance(earnings_dates, list) else earnings_dates
                if hasattr(next_earn, "timestamp"):
                    days_to = int((next_earn.timestamp() - time.time()) / 86400)
                else:
                    days_to = None
                iv_rank_val = info.get("impliedVolatility")
                if iv_rank_val is not None:
                    iv_rank_val = min(100.0, max(0.0, float(iv_rank_val) * 100))
                earnings_adj = earnings_proximity_adjustment(symbol, days_to, iv_rank_val)
            except Exception:
                pass

        mtf_mod = (mtf_score - 50) * 0.2
        sot_mod = (sot_score - 50) * 0.2
        squeeze_mod = (squeeze_score - 50) * 0.2
        es_mod = (earnings_surprise_score - 50) * 0.2 if earnings_surprise_score is not None else 0
        clue6_mod = (clue6_score - 50) * 0.2

        wyckoff_adj = min(100.0, max(0.0, wyckoff_score + sot_mod + clue6_mod))
        pa_adj = min(100.0, max(0.0, pa_score + mtf_mod))
        sentiment_adj = min(100.0, max(0.0, sentiment_score + squeeze_mod))
        fundamentals_adj = min(100.0, max(0.0, fundamentals_score + es_mod))

        new_mod = (
            (candle_score - 50) * 0.10
            + (fib_score - 50) * 0.10
            + (bb_score - 50) * 0.10
            + (obv_score - 50) * 0.10
            + (sr_score - 50) * 0.10
            + (psych_score - 50) * 0.10
            + (ichi_score - 50) * 0.06
            + (candle_adv_score - 50) * 0.06
            + (risk_reward_score - 50) * 0.06
            + (psych_adv_score - 50) * 0.06
            + (pf_score - 50) * 0.06
        )

        final = (
            wyckoff_adj * 0.20
            + volprof_score * 0.20
            + pa_adj * 0.15
            + sentiment_adj * 0.20
            + fundamentals_adj * 0.25
            + new_mod
        )
        final = min(100.0, max(0.0, round(final, 1)))

        pattern = identify_pattern(
            int(wyckoff_score), int(volprof_score), int(pa_score),
            int(sentiment_score), int(fundamentals_score), info, wyckoff_d,
            sentiment_subs,
        )

        flags = []
        if pattern == "Squeeze Setup":
            flags.append("squeeze_candidate")
        if earnings_adj is not None and earnings_adj > 0:
            flags.append(f"earnings_in_{int(earnings_adj*100)}d")

        return {
            "symbol": symbol,
            "name": ticker_dict.get("name", symbol),
            "market": ticker_dict.get("market", "US"),
            "sector": str(info.get("sector", "")),
            "price": round(price, 2),
            "final_score": round(final, 1),
            "dimensions": [
                {"name": "Wyckoff Phase", "weight": 0.20, "score": wyckoff_score, "detail": wyckoff_d},
                {"name": "Volume Profile", "weight": 0.20, "score": volprof_score, "detail": volprof_d},
                {"name": "Price Action", "weight": 0.15, "score": pa_score, "detail": pa_d},
                {"name": "Sentiment", "weight": 0.20, "score": sentiment_score, "detail": sentiment_d},
                {"name": "Fundamentals", "weight": 0.25, "score": fundamentals_score, "detail": fundamentals_d},
            ],
            "sentiment_breakdown": sentiment_subs,
            "modifiers": {
                "multi_timeframe": {"score": mtf_score, "detail": mtf_d},
                "sot_weis_wave": {"score": sot_score, "detail": sot_d},
                "squeeze_play": {"score": squeeze_score, "detail": squeeze_d},
                "earnings_surprise": {"score": earnings_surprise_score, "detail": earnings_surprise_d},
                "clue6_test": {"score": clue6_score, "detail": clue6_d},
            },
            "indicators": {
                "candlestick": candle_score, "fibonacci": fib_score,
                "bollinger": bb_score, "obv": obv_score,
                "support_resistance": sr_score, "psychology": psych_score,
                "ichimoku": ichi_score, "risk_reward": risk_reward_score,
                "point_figure": pf_score,
            },
            "flags": flags,
            "pattern": pattern,
            "competitive_score": competitive_score,
            "competitive_detail": competitive_d,
            "earnings_proximity": earnings_adj,
        }
    except Exception:
        return None


def process_crypto_ticker(ticker_dict: dict[str, str]) -> dict[str, Any] | None:
    """Process a single crypto ticker through analysis dimensions."""
    symbol = ticker_dict["symbol"]
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 20:
            return None

        price = float(hist["Close"].iloc[-1])
        if price < 0.01:
            return None

        wyckoff_score, wyckoff_d = compute_wyckoff(hist, {})
        volprof_score, volprof_d = compute_volume_profile(hist)
        pa_score, pa_d = compute_price_action(hist)
        crypto_score, crypto_d = compute_crypto_analysis(t, hist)
        mtf_score, mtf_d = compute_multiframe_trend(hist)
        sot_score, sot_d = compute_sot_weis_wave(hist)

        candle_score, candle_d = compute_candlestick_patterns(hist)
        fib_score, fib_d = compute_fibonacci(hist)
        bb_score, bb_d = compute_bollinger(hist)
        obv_score, obv_d = compute_obv(hist)
        sr_score, sr_d = compute_support_resistance(hist)
        psych_score, psych_d = compute_psychology_score(hist)
        ichi_score, ichi_d = compute_ichimoku(hist)
        candle_adv_score, candle_adv_d = compute_candlestick_advanced(hist)
        risk_reward_score, risk_reward_d = compute_risk_reward(hist, price)
        psych_adv_score, psych_adv_d = compute_psychology_advanced(hist)
        pf_score, pf_d = compute_point_figure(hist)

        mtf_mod = (mtf_score - 50) * 0.2
        sot_mod = (sot_score - 50) * 0.2
        wyckoff_adj = min(100.0, max(0.0, wyckoff_score + sot_mod))
        pa_adj = min(100.0, max(0.0, pa_score + mtf_mod))

        new_mod = (
            (candle_score - 50) * 0.10
            + (fib_score - 50) * 0.10
            + (bb_score - 50) * 0.10
            + (obv_score - 50) * 0.10
            + (sr_score - 50) * 0.10
            + (psych_score - 50) * 0.10
            + (ichi_score - 50) * 0.06
            + (candle_adv_score - 50) * 0.06
            + (risk_reward_score - 50) * 0.06
            + (psych_adv_score - 50) * 0.06
            + (pf_score - 50) * 0.06
        )

        final = (
            wyckoff_adj * 0.25
            + volprof_score * 0.25
            + pa_adj * 0.20
            + crypto_score * 0.30
            + new_mod
        )
        final = min(100.0, max(0.0, round(final, 1)))

        return {
            "symbol": symbol,
            "name": ticker_dict["name"],
            "market": "CRYPTO",
            "sector": "Cryptocurrency",
            "price": round(price, 4),
            "final_score": round(final, 1),
            "dimensions": [
                {"name": "Wyckoff Phase", "weight": 0.25, "score": wyckoff_score, "detail": wyckoff_d},
                {"name": "Volume Profile", "weight": 0.25, "score": volprof_score, "detail": volprof_d},
                {"name": "Price Action", "weight": 0.20, "score": pa_score, "detail": pa_d},
                {"name": "Crypto APC", "weight": 0.30, "score": crypto_score, "detail": crypto_d},
            ],
            "sentiment_breakdown": None,
            "modifiers": {
                "multi_timeframe": {"score": mtf_score, "detail": mtf_d},
                "sot_weis_wave": {"score": sot_score, "detail": sot_d},
            },
            "indicators": {
                "candlestick": candle_score, "fibonacci": fib_score,
                "bollinger": bb_score, "obv": obv_score,
                "support_resistance": sr_score, "psychology": psych_score,
                "ichimoku": ichi_score, "risk_reward": risk_reward_score,
                "point_figure": pf_score,
            },
            "flags": [],
            "pattern": "Crypto APC",
        }
    except Exception:
        return None
