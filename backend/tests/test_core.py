"""Offline tests for the parts that do math. Run:  cd backend && pytest -q"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app import indicators as ind
from app.metrics import METRICS, METRIC_KEYS, PRESETS
from app.regime import read_regime
from app.screener import apply_filters
from app.snapshot import build_row, financial_extras, fundamentals_from_info


def prices(values) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)), dtype=float)


def test_rsi_extremes_and_midpoint():
    assert ind.rsi(prices(range(1, 40))) == 100.0
    assert ind.rsi(prices(range(40, 1, -1))) == pytest.approx(0.0, abs=1e-9)
    zigzag = prices([10, 11] * 30)
    assert 40 < ind.rsi(zigzag) < 60
    assert ind.rsi(prices([1, 2, 3])) is None  # not enough data


def test_moving_average_distance_and_high():
    s = prices([100.0] * 199 + [110.0])
    assert ind.pct_from_sma(s, 200) == pytest.approx(110 / 100.05 * 100 - 100, rel=1e-6)
    assert ind.pct_from_high(prices([50, 100, 80])) == pytest.approx(-20.0)


def test_returns_volatility_volume():
    s = prices(np.linspace(100, 200, 300))
    assert ind.period_return(s, 21) == pytest.approx((s.iloc[-1] / s.iloc[-22] - 1) * 100)
    assert ind.volatility(prices([100.0] * 100)) == 0.0
    vol = pd.Series([100] * 60 + [300] * 5, dtype=float)
    assert ind.relative_volume(vol) == pytest.approx(300 / ((58 * 100 + 5 * 300) / 63))


def test_cagr_and_percentile():
    assert ind.cagr(100, 133.1, 3) == pytest.approx(10.0)
    assert ind.cagr(-5, 10, 3) is None
    assert ind.percentile_rank(pd.Series([1, 2, 3, 4])) == 100.0
    assert ind.percentile_rank(pd.Series([4, 3, 2, 1])) == 25.0


def test_info_mapping_units():
    info = {
        "shortName": "Acme", "sector": "Technology", "currentPrice": 50.0, "marketCap": 2e10,
        "trailingPE": 25.0, "returnOnEquity": 0.21, "debtToEquity": 150.0, "dividendRate": 1.0,
        "freeCashflow": 1e9, "averageVolume": 2e6, "shortPercentOfFloat": 0.031,
    }
    f = fundamentals_from_info(info)
    assert f["roe"] == pytest.approx(21.0)
    assert f["debt_to_equity"] == pytest.approx(1.5)
    assert f["dividend_yield"] == pytest.approx(2.0)
    assert f["fcf_yield"] == pytest.approx(5.0)
    assert f["market_cap"] == pytest.approx(20.0)
    assert f["avg_dollar_volume"] == pytest.approx(100.0)
    assert f["short_float"] == pytest.approx(3.1)
    assert fundamentals_from_info({"currentPrice": 10.0})["dividend_yield"] == 0.0


def test_financial_extras():
    cols = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"])
    income = pd.DataFrame(
        [[133.1, 121.0, 110.0, 100.0], [30.0, 20, 20, 20], [-3.0, -3, -3, -3]],
        index=["Total Revenue", "EBIT", "Interest Expense"],
        columns=cols,
    )
    extras = financial_extras(income[income.columns[::-1]])  # order should not matter
    assert extras["revenue_cagr_3y"] == pytest.approx(10.0)
    assert extras["interest_coverage"] == pytest.approx(10.0)


def test_build_row_covers_every_metric():
    hist = pd.DataFrame({"Close": np.linspace(50, 80, 300), "Volume": [1e6] * 300},
                        index=pd.bdate_range("2024-01-01", periods=300))
    row = build_row("ACME", hist, {"currentPrice": 80.0, "marketCap": 1e10}, pd.DataFrame())
    missing = METRIC_KEYS - set(row)
    assert not missing, f"metrics not produced by build_row: {missing}"


def test_filters_ranges_sectors_query():
    df = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "name": ["Alpha", "Beta Corp", "Gamma", "Delta"],
            "sector": ["Technology", "Energy", "Technology", "Utilities"],
            "pe": [10.0, 30.0, None, 15.0],
            "roe": [25.0, 5.0, 30.0, 12.0],
        }
    )
    assert list(apply_filters(df, {"pe": [None, 20]})["symbol"]) == ["AAA", "DDD"]
    assert list(apply_filters(df, {"roe": [20, None]}, ["Technology"])["symbol"]) == ["AAA", "CCC"]
    assert list(apply_filters(df, {"pe": [None, None]})["symbol"]) == ["AAA", "BBB", "CCC", "DDD"]
    assert list(apply_filters(df, {"unknown": [1, 2]}, query="beta")["symbol"]) == ["BBB"]


def test_catalog_consistency():
    keys = [m.key for m in METRICS]
    assert len(keys) == len(set(keys))
    for m in METRICS:
        assert m.slider_min < m.slider_max and m.description and m.label
    for preset in PRESETS:
        assert set(preset["filters"]) <= METRIC_KEYS


def test_regime_reads_inversion_and_stress():
    out = read_regime({"vix": {"value": 32.0}, "curve": {"value": -0.4}, "spx": {"dist_sma200": -5.0}})
    tones = {s["label"]: s["tone"] for s in out}
    assert tones == {"변동성": "stress", "금리 곡선": "stress", "추세": "stress"}


def test_pick_constituents_handles_footnotes_and_classes():
    from app.universe import pick_constituents

    noise = pd.DataFrame({"Date": ["x"] * 60, "Added": ["y"] * 60})
    names = [f"Co {i}" for i in range(60)]
    table = pd.DataFrame({"Ticker[3]": ["BRK.B", "aapl"] + [f"T{i}" for i in range(58)], "Company": names})
    out = pick_constituents([noise, table])
    assert out["ticker"].tolist()[:2] == ["BRK-B", "AAPL"] and len(out) == 60


def test_load_universe_adds_extra(tmp_path, monkeypatch):
    from app import universe

    csv = tmp_path / "universe.csv"
    pd.DataFrame({"ticker": ["AAPL", "MSFT"], "name": ["a", "m"], "index": ["S&P 500", "S&P 400, S&P 600"]}).to_csv(csv, index=False)
    extra = tmp_path / "universe_extra.txt"
    extra.write_text("# comment\nionq   # quantum\nAAPL\n\n")
    monkeypatch.setattr(universe, "UNIVERSE_CSV", csv)
    monkeypatch.setattr(universe, "EXTRA", extra)
    monkeypatch.setattr(universe, "OVERRIDE", tmp_path / "missing.txt")
    assert universe.load_universe() == ["AAPL", "IONQ", "MSFT"]
    assert "extra 1 (IONQ)" in universe.describe_universe(["AAPL", "IONQ", "MSFT"])


def test_pick_constituents_header_in_first_row():
    from app.universe import pick_constituents

    rows = [["Ticker", "Company", "ICB Industry"]] + [[f"T{i}", f"Co {i}", "Tech"] for i in range(101)]
    out = pick_constituents([pd.DataFrame(rows)])
    assert len(out) == 101 and out["ticker"].iloc[0] == "T0"
