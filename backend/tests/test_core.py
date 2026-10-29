"""Offline tests for the parts that do math. Run:  cd backend && pytest -q"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app import indicators as ind
from app.metrics import METRICS, METRIC_KEYS, PRESETS, SECTOR_SUFFIX
from app.regime import read_regime
from app import screener
from app.screener import apply_filters, with_sector_percentiles
from app.snapshot import build_row, cash_runway_months, financial_extras, fundamentals_from_info
from app.valuation import valuation_ranges


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
        assert {k.removesuffix(SECTOR_SUFFIX) for k in preset["filters"]} <= METRIC_KEYS
        for key, (lo, hi) in preset["filters"].items():
            if key.endswith(SECTOR_SUFFIX):
                assert all(v is None or 0 <= v <= 100 for v in (lo, hi))


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


def test_net_margin_recomputed_when_yahoo_reports_zero():
    f = fundamentals_from_info({"profitMargins": 0.0, "netIncomeToCommon": -50.0, "totalRevenue": 200.0})
    assert f["net_margin"] == pytest.approx(-25.0)
    assert fundamentals_from_info({"profitMargins": 0.0})["net_margin"] == 0.0


def test_cash_runway():
    assert cash_runway_months(1200.0, -600.0, -300.0) == pytest.approx(24.0)  # worse burn wins
    assert cash_runway_months(1200.0, None, -1200.0) == pytest.approx(12.0)
    assert cash_runway_months(1200.0, 100.0, 50.0) is None  # not burning cash
    assert cash_runway_months(None, -100.0, None) is None


def test_share_and_gross_margin_change():
    cols = pd.to_datetime(["2025-12-31", "2024-12-31"])
    income = pd.DataFrame(
        [[110.0, 100.0], [200.0, 100.0], [100.0, 40.0]],
        index=["Diluted Average Shares", "Total Revenue", "Gross Profit"],
        columns=cols,
    )
    extras = financial_extras(income)
    assert extras["share_change_1y"] == pytest.approx(10.0)
    assert extras["gross_margin_change"] == pytest.approx(10.0)  # 50% vs 40%


def test_positive_only_multiples_and_sector_percentiles():
    df = pd.DataFrame(
        {
            "symbol": list("ABCDEFG"),
            "name": list("abcdefg"),
            "sector": ["Tech"] * 5 + ["Energy"] * 2,
            "forward_pe": [10.0, 20.0, 30.0, 40.0, -5.0, 8.0, 9.0],
            "roe": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        }
    )
    # A negative forward PER is a loss, not "cheap": it must not pass a max filter.
    assert list(apply_filters(df, {"forward_pe": [None, 15]})["symbol"]) == ["A", "F", "G"]

    df = with_sector_percentiles(df)
    # Only 4 usable Tech forward PERs (< 5 peers) → no percentile at all.
    assert df["forward_pe@sector"].isna().all()
    assert df.loc[df.symbol == "E", "roe@sector"].item() == pytest.approx(100.0)
    assert df.loc[df.symbol == "A", "roe@sector"].item() == pytest.approx(20.0)
    assert df.loc[df.symbol == "F", "roe@sector"].isna().item()  # Energy has 2 peers
    assert list(apply_filters(df, {"roe@sector": [None, 40]})["symbol"]) == ["A", "B"]


def test_share_classes_counted_once(monkeypatch):
    df = pd.DataFrame(
        {
            "symbol": ["GOOG", "GOOGL", "A", "B", "C", "D"],
            "name": ["Alphabet Inc.", "Alphabet Inc.", "a", "b", "c", "d"],
            "sector": ["Tech"] * 6,
            "avg_dollar_volume": [1.0, 2.0, 1.0, 1.0, 1.0, 1.0],
            "roe": [30.0, 30.0, 1.0, 2.0, 3.0, 4.0],
            "market_cap": [100.0, 100.0, 1.0, 2.0, 3.0, 4.0],
        }
    )
    monkeypatch.setattr(screener, "frame", lambda: screener._frame)
    screener.set_frame(df)
    result = screener.run()
    symbols = [r["symbol"] for r in result["rows"]]
    assert result["total"] == 5 and "GOOG" not in symbols  # the more traded class stays
    assert result["rows"][0]["other_classes"] == "GOOG"
    # Percentiles among 5 companies, not 6; the secondary class gets the same value.
    assert screener.sector_percentiles("GOOGL")["roe"] == pytest.approx(100.0)
    assert screener.sector_percentiles("GOOG")["roe"] == pytest.approx(100.0)
    assert screener.sector_percentiles("A")["roe"] == pytest.approx(20.0)
    assert screener.run(query="goog")["total"] == 2  # searching by ticker finds both classes
    screener.set_frame(None)


def test_valuation_ranges_use_published_annual_figures():
    dates = pd.date_range("2022-01-07", "2025-12-26", freq="W-FRI")
    close = pd.Series(100.0, index=dates)
    fy = pd.to_datetime(["2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31"])
    income = pd.DataFrame(
        [[5.0, 4.0, 2.0, -1.0], [1000.0, 800.0, 500.0, 400.0], [100.0, 100.0, 100.0, 100.0]],
        index=["Diluted EPS", "Total Revenue", "Diluted Average Shares"],
        columns=fy,  # FY2021 … FY2024, oldest first
    )
    out = valuation_ranges(close, income)
    pe = out["pe"]
    # EPS goes 5 → 4 → 2 → −1: PER 20 → 25 → 50, then a loss year has no PER.
    assert pe["low"] == pytest.approx(20.0) and pe["high"] == pytest.approx(50.0)
    assert pe["current"] is None and pe["percentile"] is None
    ps = out["ps"]
    assert ps["current"] == pytest.approx(100 / 4.0)  # FY2024 sales/share = 400/100
    assert ps["low"] == pytest.approx(10.0)
    assert valuation_ranges(close, pd.DataFrame()) == {"pe": None, "ps": None}


def test_performance_since():
    idx = pd.bdate_range("2026-01-01", periods=5)
    stock = pd.Series([10, 11, 12, 13, 15], index=idx, dtype=float)
    spy = pd.Series([100, 100, 101, 102, 110], index=idx, dtype=float)
    r = ind.performance_since(stock, spy, pd.Timestamp("2026-01-02"))
    assert r["base_price"] == 11 and r["change_pct"] == pytest.approx(15 / 11 * 100 - 100)
    assert r["excess_pct"] == pytest.approx(r["change_pct"] - 10.0)
    assert ind.performance_since(stock, spy, pd.Timestamp("2026-02-01")) is None
