"""Squeeze Play System (Trading Against the Crowd - Summa)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf

from trading_mcp.data.provider import data_provider


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
        # fix R1: opzioni via DataProvider (cache condivisa con sentiment_6d)
        symbol = getattr(ticker, "ticker", "")
        exps = data_provider.get_options_expirations(symbol)
        if exps and len(exps) >= 2:
            pc_ratios: list[float] = []
            for exp in exps[:4]:
                try:
                    chain = data_provider.get_options_chain(symbol, exp)
                    if chain is None:
                        continue
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
                # The ratios come from different expiries of the SAME snapshot:
                # that is a term structure, not a time series. An EMA over four
                # points is degenerate (span > sample), so compare the near end
                # of the curve against the far end instead.
                pc_near = float(pd.Series(pc_ratios[:2]).mean())
                pc_far = float(pd.Series(pc_ratios[2:]).mean()) if len(pc_ratios) > 2 else pc_near
                if pc_near > 0:
                    ratio = pc_far / pc_near
                    if ratio > 1.15:
                        score -= 15
                        details.append(
                            f"Squeeze I: P/C term structure rising (near {pc_near:.2f} -> "
                            f"far {pc_far:.2f}), hedging demand on long expiries (-15)"
                        )
                    elif ratio < 0.85:
                        score += 20
                        details.append(
                            f"Squeeze I: P/C term structure falling (near {pc_near:.2f} -> "
                            f"far {pc_far:.2f}), complacency on long expiries (+20)"
                        )
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
