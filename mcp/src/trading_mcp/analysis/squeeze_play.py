"""Squeeze Play System (Trading Against the Crowd - Summa)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf


def compute_squeeze_play(
    ticker: yf.Ticker, info: dict[str, Any], hist: pd.DataFrame
) -> tuple[int, str]:
    """Squeeze Play scoring: P/C ratio EMA + price trigger + smart money divergence.

    Args:
        ticker: yfinance Ticker.
        info: yfinance info dict.
        hist: OHLCV DataFrame.
    """
    if hist.empty or len(hist) < 50:
        return 50, "Insufficient data for Squeeze Play"

    score = 50
    details = []

    try:
        exps = ticker.options
        if exps and len(exps) >= 2:
            pc_ratios: list[float] = []
            for exp in exps[:4]:
                try:
                    chain = ticker.option_chain(exp)
                    calls = chain.calls
                    puts = chain.puts
                    if not calls.empty and not puts.empty:
                        c_vol = int(calls["volume"].sum()) if "volume" in calls.columns else 0
                        p_vol = int(puts["volume"].sum()) if "volume" in puts.columns else 0
                        if c_vol > 0:
                            pc_ratios.append(p_vol / c_vol)
                except Exception:
                    continue

            if len(pc_ratios) >= 2:
                pc_series = pd.Series(pc_ratios)
                ema_fast = float(pc_series.ewm(span=2).mean().iloc[-1])
                ema_slow = float(pc_series.ewm(span=4).mean().iloc[-1])
                if ema_slow > 0:
                    if ema_fast < ema_slow * 0.8:
                        score += 20
                        details.append("Squeeze I: P/C EMA fast < slow (bullish divergence +20)")
                    elif ema_fast > ema_slow * 1.2:
                        score -= 15
                        details.append("Squeeze I: P/C EMA fast > slow (bearish divergence -15)")
    except Exception:
        pass

    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values

    if len(close) >= 5:
        prev_high = float(max(high[-5:-1])) if len(high[-5:-1]) > 0 else 0.0
        prev_low = float(min(low[-5:-1])) if len(low[-5:-1]) > 0 else 0.0
        current_close = float(close[-1])

        if current_close > prev_high:
            score += 15
            details.append(f"Price trigger: close ${current_close:.2f} > 5d high ${prev_high:.2f} (bullish +15)")
        elif current_close < prev_low:
            score -= 15
            details.append(f"Price trigger: close ${current_close:.2f} < 5d low ${prev_low:.2f} (bearish -15)")

    si = info.get("shortPercentOfFloat")
    dtc = info.get("shortRatio")
    if si is not None and float(si) > 0.15 and dtc is not None and float(dtc) > 5:
        score += 10
        details.append(f"Smart Money divergence: SI {float(si):.1%} + DTC {float(dtc):.1f} (contrarian +10)")

    return min(100, max(0, score)), " | ".join(details)
