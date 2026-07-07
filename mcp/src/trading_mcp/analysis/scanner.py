"""Market scanner orchestrator: multi-dimensional ticker scoring engine."""

from __future__ import annotations

import csv
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreaker:
    """Simple circuit breaker for yfinance rate limiting protection."""
    failure_count: int = 0
    failure_threshold: int = 10
    reset_timeout: float = 60.0
    last_failure_time: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def is_open(self) -> bool:
        """Check if circuit is open (blocking calls)."""
        with self._lock:
            if self.failure_count >= self.failure_threshold:
                elapsed = time.time() - self.last_failure_time
                if elapsed < self.reset_timeout:
                    return True
                self.failure_count = 0
            return False

    def record_success(self) -> None:
        with self._lock:
            self.failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()


_yfinance_breaker = CircuitBreaker()

import numpy as np
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
from trading_mcp.weights_config import get_weights


_SPX_HIST: pd.DataFrame | None = None
_SPX_HIST_TIME: float = 0.0
_SPX_HIST_TTL: float = 3600.0  # 1 hour

_WSB_HOTLIST: dict | None = None
_WSB_HOTLIST_TIME: float = 0.0
_WSB_HOTLIST_TTL: float = 1800.0  # 30 minutes


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
    """Get S&P 500 history with 1-hour TTL cache."""
    global _SPX_HIST, _SPX_HIST_TIME
    now = time.time()
    if _SPX_HIST is None or (now - _SPX_HIST_TIME) > _SPX_HIST_TTL:
        try:
            spx = yf.Ticker("^GSPC")
            _SPX_HIST = spx.history(period="1y")
            _SPX_HIST_TIME = now
            logger.debug("SPX history refreshed")
        except Exception as e:
            logger.warning("Failed to fetch SPX history: %s: %s", type(e).__name__, e)
            if _SPX_HIST is None:
                _SPX_HIST = pd.DataFrame()
    if _SPX_HIST is not None and not _SPX_HIST.empty:
        return _SPX_HIST.copy()
    return pd.DataFrame()


def _get_wsb_hotlist() -> dict | None:
    """Get WSB hotlist with 30-min TTL cache. Currently not implemented — returns None."""
    global _WSB_HOTLIST, _WSB_HOTLIST_TIME
    now = time.time()
    if _WSB_HOTLIST is not None and (now - _WSB_HOTLIST_TIME) <= _WSB_HOTLIST_TTL:
        return _WSB_HOTLIST
    return None


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
    thresholds: dict[str, int] | None = None,
) -> str:
    """Identify dominant accumulation/distribution pattern.

    Uses dynamic thresholds when provided (computed from universe distribution),
    otherwise falls back to hardcoded defaults.
    """
    si = float(info.get("shortPercentOfFloat", 0) or 0)
    web_news = sentiment_subs.get("web_news") if sentiment_subs else None
    social = sentiment_subs.get("social_media") if sentiment_subs else None

    if thresholds is None:
        thresholds = {
            "wyckoff_strong": 70, "volprof_strong": 70,
            "pa_strong": 70, "sentiment_strong": 70,
            "fundamentals_moderate": 60, "wyckoff_moderate": 65,
            "volprof_low": 30, "social_signal": 60,
            "web_news_strong": 80, "sentiment_short_pct": 20,
        }

    t = thresholds

    if wyckoff_score >= t["wyckoff_strong"] and "Spring" in wyckoff_detail:
        return "Accumulation Spring"
    if volprof_score >= t["volprof_strong"] and fundamentals_score >= t["fundamentals_moderate"]:
        return "D-Profile Value Zone"
    if volprof_score >= t["volprof_strong"] and pa_score >= t["pa_strong"] and social is not None and social >= t["social_signal"]:
        return "P-Profile Breakout"
    if social is not None and social >= t["sentiment_strong"] and pa_score >= 50:
        return "WSB Hype Confirmation"
    if web_news is not None and web_news >= t["web_news_strong"] and wyckoff_score <= t["wyckoff_strong"] and 40 <= pa_score <= t["fundamentals_moderate"]:
        return "News Catalyst Buildup"
    if pa_score >= t["pa_strong"] and sentiment_score >= 50:
        return "P-Profile Breakout"
    if sentiment_score >= t["sentiment_strong"] and si > (t["sentiment_short_pct"] / 100.0):
        return "Squeeze Setup"
    if wyckoff_score >= t["wyckoff_moderate"] and fundamentals_score >= t["fundamentals_moderate"]:
        return "Golden Cross Accumulation"
    if volprof_score < t["volprof_low"]:
        return "b-Profile Trap"
    return "Mixed / No dominant pattern"


def compute_dynamic_thresholds(results: list[dict]) -> dict[str, int]:
    """Compute 75th percentile thresholds from scan score distribution."""
    defaults: dict[str, int] = {
        "wyckoff_strong": 70, "volprof_strong": 70,
        "pa_strong": 70, "sentiment_strong": 70,
        "fundamentals_moderate": 60, "wyckoff_moderate": 65,
        "volprof_low": 30, "social_signal": 60,
        "web_news_strong": 80, "sentiment_short_pct": 20,
    }
    if len(results) < 5:
        return defaults

    def _extract_dim(res_list: list[dict], idx: int) -> list[float]:
        scores: list[float] = []
        for r in res_list:
            dims = r.get("dimensions", [])
            if len(dims) > idx:
                scores.append(float(dims[idx].get("score", 50)))
        return scores

    try:
        wyckoff_scores = _extract_dim(results, 0)
        volprof_scores = _extract_dim(results, 1)
        pa_scores = _extract_dim(results, 2)
        sentiment_scores = _extract_dim(results, 3)
        fundamentals_scores = _extract_dim(results, 4)

        wyckoff_75 = int(np.percentile(wyckoff_scores, 75))
        volprof_75 = int(np.percentile(volprof_scores, 75))
        pa_75 = int(np.percentile(pa_scores, 75))
        sentiment_75 = int(np.percentile(sentiment_scores, 75))
        fundamentals_65 = int(np.percentile(fundamentals_scores, 65))
        wyckoff_65 = int(np.percentile(wyckoff_scores, 65))
        volprof_25 = int(np.percentile(volprof_scores, 25))
    except Exception:
        logger.warning("Failed to compute dynamic thresholds", exc_info=True)
        return defaults

    return {
        "wyckoff_strong": max(60, min(85, wyckoff_75)),
        "volprof_strong": max(60, min(85, volprof_75)),
        "pa_strong": max(60, min(85, pa_75)),
        "sentiment_strong": max(60, min(85, sentiment_75)),
        "fundamentals_moderate": max(50, min(80, fundamentals_65)),
        "wyckoff_moderate": max(55, min(80, wyckoff_65)),
        "volprof_low": min(40, max(15, volprof_25)),
        "social_signal": 60,
        "web_news_strong": 80,
        "sentiment_short_pct": 20,
    }


def recompute_patterns(results: list[dict], thresholds: dict[str, int]) -> None:
    """Recompute pattern labels for all results using dynamic thresholds."""
    for r in results:
        dims = r.get("dimensions", [])
        w_s = int(dims[0]["score"]) if len(dims) > 0 else 50
        vp_s = int(dims[1]["score"]) if len(dims) > 1 else 50
        pa_s = int(dims[2]["score"]) if len(dims) > 2 else 50
        sent_s = int(dims[3]["score"]) if len(dims) > 3 else 50
        fund_s = int(dims[4]["score"]) if len(dims) > 4 else 50
        w_d = dims[0].get("detail", "") if len(dims) > 0 else ""
        s_subs = r.get("sentiment_breakdown")
        info = {"shortPercentOfFloat": r.get("_si", 0)}
        r["pattern"] = identify_pattern(
            w_s, vp_s, pa_s, sent_s, fund_s,
            info, w_d, s_subs, thresholds=thresholds,
        )


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


def _fetch_with_retry(symbol: str, max_retries: int = 2) -> tuple:
    """Fetch ticker data with retry, circuit breaker, and jittered backoff."""
    if _yfinance_breaker.is_open():
        logger.warning("Circuit breaker OPEN for %s — skipping fetch (rate limit protection)", symbol)
        return None, {}, None

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            hist = t.history(period="1y")
            if hist is not None and not hist.empty:
                _yfinance_breaker.record_success()
                return t, info, hist
            if attempt < max_retries:
                jitter = random.uniform(0, 1)
                time.sleep((2 ** attempt) + jitter)
        except Exception as e:
            last_err = e
            _yfinance_breaker.record_failure()
            logger.warning("Fetch failed for %s (attempt %d/%d): %s: %s",
                           symbol, attempt + 1, max_retries + 1,
                           type(e).__name__, e)
            if attempt < max_retries:
                jitter = random.uniform(0, 1)
                time.sleep((3 ** attempt) + jitter)
    logger.error("All %d retries exhausted for %s. Last error: %s: %s",
                 max_retries + 1, symbol,
                 type(last_err).__name__ if last_err else "None",
                 last_err or "No data returned")
    return None, {}, None


def process_ticker(ticker_dict: dict[str, str], fetch_news: bool = True) -> dict[str, Any] | None:
    """Process a single stock ticker through all analysis dimensions."""
    symbol = ticker_dict["symbol"]
    try:
        t, info, hist = _fetch_with_retry(symbol)
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
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
            wsb_hotlist=_get_wsb_hotlist(),
            fetch_news=fetch_news,
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

        wcfg = get_weights()
        ms = wcfg.modifier_scale
        mtf_mod = (mtf_score - 50) * ms.multi_timeframe
        sot_mod = (sot_score - 50) * ms.sot_weis_wave
        squeeze_mod = (squeeze_score - 50) * ms.squeeze_play
        es_mod = (earnings_surprise_score - 50) * ms.earnings_surprise if earnings_surprise_score is not None else 0
        clue6_mod = (clue6_score - 50) * ms.clue6_test

        wyckoff_adj = min(100.0, max(0.0, wyckoff_score + sot_mod + clue6_mod))
        pa_adj = min(100.0, max(0.0, pa_score + mtf_mod))
        sentiment_adj = min(100.0, max(0.0, sentiment_score + squeeze_mod))
        fundamentals_adj = min(100.0, max(0.0, fundamentals_score + es_mod))

        ind = wcfg.indicators
        new_mod = (
            (candle_score - 50) * ind.candlestick
            + (fib_score - 50) * ind.fibonacci
            + (bb_score - 50) * ind.bollinger
            + (obv_score - 50) * ind.obv
            + (sr_score - 50) * ind.support_resistance
            + (psych_score - 50) * ind.psychology
            + (ichi_score - 50) * ind.ichimoku
            + (candle_adv_score - 50) * ind.candlestick_advanced
            + (risk_reward_score - 50) * ind.risk_reward
            + (psych_adv_score - 50) * ind.psychology_advanced
            + (pf_score - 50) * ind.point_figure
        )

        sw = wcfg.stocks
        final = (
            wyckoff_adj * sw.wyckoff
            + volprof_score * sw.volume_profile
            + pa_adj * sw.price_action
            + sentiment_adj * sw.sentiment
            + fundamentals_adj * sw.fundamentals
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
            "_si": float(info.get("shortPercentOfFloat", 0) or 0),
            "earnings_proximity": earnings_adj,
        }
    except Exception as e:
        logger.error("process_ticker failed for %s: %s: %s", symbol, type(e).__name__, e)
        return None
def process_crypto_ticker(ticker_dict: dict[str, str], fetch_news: bool = True) -> dict[str, Any] | None:
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

        wcfg = get_weights()
        ms = wcfg.modifier_scale
        mtf_mod = (mtf_score - 50) * ms.multi_timeframe
        sot_mod = (sot_score - 50) * ms.sot_weis_wave
        wyckoff_adj = min(100.0, max(0.0, wyckoff_score + sot_mod))
        pa_adj = min(100.0, max(0.0, pa_score + mtf_mod))

        ind = wcfg.indicators
        new_mod = (
            (candle_score - 50) * ind.candlestick
            + (fib_score - 50) * ind.fibonacci
            + (bb_score - 50) * ind.bollinger
            + (obv_score - 50) * ind.obv
            + (sr_score - 50) * ind.support_resistance
            + (psych_score - 50) * ind.psychology
            + (ichi_score - 50) * ind.ichimoku
            + (candle_adv_score - 50) * ind.candlestick_advanced
            + (risk_reward_score - 50) * ind.risk_reward
            + (psych_adv_score - 50) * ind.psychology_advanced
            + (pf_score - 50) * ind.point_figure
        )

        cw = wcfg.crypto
        final = (
            wyckoff_adj * cw.wyckoff
            + volprof_score * cw.volume_profile
            + pa_adj * cw.price_action
            + crypto_score * cw.crypto_apc
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
    except Exception as e:
        logger.error("process_crypto_ticker failed for %s: %s: %s", symbol, type(e).__name__, e)
        return None
