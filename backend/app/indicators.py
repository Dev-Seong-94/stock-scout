"""Price-based indicators. Pure pandas, no network, so they are easy to test."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _clean(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def rsi(close: pd.Series, period: int = 14) -> float | None:
    """Wilder's RSI on the latest bar."""
    close = close.dropna()
    if len(close) <= period:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    last_gain, last_loss = avg_gain.iloc[-1], avg_loss.iloc[-1]
    if last_loss == 0:
        return 100.0 if last_gain > 0 else 50.0
    rs = last_gain / last_loss
    return _clean(100 - 100 / (1 + rs))


def pct_from_sma(close: pd.Series, window: int) -> float | None:
    """How far the last close is above (+) or below (-) its moving average, in %."""
    close = close.dropna()
    if len(close) < window:
        return None
    sma = close.rolling(window).mean().iloc[-1]
    return _clean((close.iloc[-1] / sma - 1) * 100)


def pct_from_high(close: pd.Series, window: int = TRADING_DAYS) -> float | None:
    """Distance from the highest close of the window, in % (0 or negative)."""
    close = close.dropna().iloc[-window:]
    if close.empty:
        return None
    return _clean((close.iloc[-1] / close.max() - 1) * 100)


def period_return(close: pd.Series, days: int) -> float | None:
    close = close.dropna()
    if len(close) <= days:
        return None
    return _clean((close.iloc[-1] / close.iloc[-1 - days] - 1) * 100)


def volatility(close: pd.Series, days: int = 63) -> float | None:
    """Annualised standard deviation of daily returns, in %."""
    returns = close.dropna().pct_change().dropna().iloc[-days:]
    if len(returns) < max(10, days // 3):
        return None
    return _clean(returns.std() * math.sqrt(TRADING_DAYS) * 100)


def relative_volume(volume: pd.Series, short: int = 5, long: int = 63) -> float | None:
    """Recent average volume divided by the longer average (1.0 = normal)."""
    volume = volume.dropna()
    if len(volume) < long:
        return None
    base = volume.iloc[-long:].mean()
    if not base:
        return None
    return _clean(volume.iloc[-short:].mean() / base)


def percentile_rank(series: pd.Series, value: float | None = None) -> float | None:
    """Where the latest (or given) value sits within the series history, 0–100."""
    s = series.dropna()
    if s.empty:
        return None
    v = s.iloc[-1] if value is None else value
    return _clean((s <= v).mean() * 100)


def cagr(first: float | None, last: float | None, years: float) -> float | None:
    """Compound annual growth in %. None when it is not meaningful (e.g. negative base)."""
    first, last = _clean(first), _clean(last)
    if first is None or last is None or years <= 0 or first <= 0 or last <= 0:
        return None
    return _clean(((last / first) ** (1 / years) - 1) * 100)


def price_indicators(history: pd.DataFrame) -> dict[str, float | None]:
    """All price-derived screener metrics from an OHLCV frame (index = dates)."""
    close = history["Close"] if "Close" in history else pd.Series(dtype=float)
    volume = history["Volume"] if "Volume" in history else pd.Series(dtype=float)
    return {
        "rsi14": rsi(close),
        "dist_sma50": pct_from_sma(close, 50),
        "dist_sma200": pct_from_sma(close, 200),
        "from_52w_high": pct_from_high(close),
        "ret_1m": period_return(close, 21),
        "ret_3m": period_return(close, 63),
        "ret_6m": period_return(close, 126),
        "ret_1y": period_return(close, 251),
        "volatility_3m": volatility(close),
        "rel_volume": relative_volume(volume),
    }


def sparkline(series: pd.Series, points: int = 60) -> list[float]:
    """Down-sample a series for small inline charts."""
    s = series.dropna()
    if s.empty:
        return []
    if len(s) > points:
        idx = np.linspace(0, len(s) - 1, points).round().astype(int)
        s = s.iloc[idx]
    return [round(float(v), 4) for v in s.tolist()]
