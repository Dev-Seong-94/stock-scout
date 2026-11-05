"""Offline tests for the parts that do math. Run:  cd backend && pytest -q"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app import indicators as ind
from app.metrics import METRICS, METRIC_KEYS, PRESETS, SECTOR_SUFFIX
from app.regime import read_regime
from app import cheapness, decline, filing_summary, screener, snapshot
from app.screener import apply_filters, with_sector_percentiles
from app.snapshot import build_row, cash_runway_months, fcf_from_statement, financial_extras, fundamentals_from_info
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
    assert all(m.prefer in ("", "high", "low") for m in METRICS)
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


def test_fcf_yield_prefers_cash_flow_statement():
    col = pd.to_datetime(["2026-07-31"])
    stmt = pd.DataFrame([[127e9], [134e9], [-7e9]], index=["Free Cash Flow", "Operating Cash Flow", "Capital Expenditure"], columns=col)
    assert fcf_from_statement(stmt) == pytest.approx(127e9)
    # No FCF line: operating cash flow plus (negative) capex.
    assert fcf_from_statement(stmt.drop("Free Cash Flow")) == pytest.approx(127e9)
    assert fcf_from_statement(pd.DataFrame()) is None

    info = {"currentPrice": 200.0, "marketCap": 5e12, "freeCashflow": 42e9, "sector": "Technology"}
    assert fundamentals_from_info(info, fcf=127e9)["fcf_yield"] == pytest.approx(2.54)
    assert fundamentals_from_info(info)["fcf_yield"] == pytest.approx(0.84)  # fallback: Yahoo's estimate
    row = build_row("ACME", pd.DataFrame(), info, None, stmt)
    assert row["fcf_yield"] == pytest.approx(2.54)


def test_no_fcf_for_banks():
    info = {"currentPrice": 300.0, "marketCap": 8e11, "sector": "Financial Services",
            "totalCash": 1e11, "operatingCashflow": -1.4e11}
    out = fundamentals_from_info(info, fcf=-1.48e11)
    assert out["fcf_yield"] is None and out["cash_runway"] is None


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



def test_compare_keeps_order_and_gives_sector_medians(monkeypatch):
    df = pd.DataFrame(
        {
            "symbol": ["A", "B", "C", "D", "E"],
            "name": list("abcde"),
            "sector": ["Tech"] * 5,
            "avg_dollar_volume": [1.0] * 5,
            "pe": [10.0, 20.0, -5.0, 40.0, 30.0],
            "roe": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    monkeypatch.setattr(screener, "frame", lambda: screener._frame)
    screener.set_frame(df)
    out = screener.compare(["d", "A", "ZZZ"])
    assert [r["symbol"] for r in out["rows"]] == ["D", "A"]
    assert out["missing"] == ["ZZZ"]
    assert out["medians"]["Tech"]["pe"] == pytest.approx(25.0)  # the negative PER is left out
    assert out["rows"][0]["roe@sector"] == pytest.approx(80.0)
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


FORM4 = """<?xml version="1.0"?><ownershipDocument>
<reportingOwner><reportingOwnerId><rptOwnerName>KRESS COLETTE</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer><officerTitle>CFO</officerTitle></reportingOwnerRelationship></reportingOwner>
<aff10b5One>1</aff10b5One>
<nonDerivativeTable>
<nonDerivativeTransaction><transactionCoding><transactionCode>F</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>500</value></transactionShares><transactionPricePerShare><value>100</value></transactionPricePerShare></transactionAmounts></nonDerivativeTransaction>
<nonDerivativeTransaction><transactionCoding><transactionCode>S</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>1000</value></transactionShares><transactionPricePerShare><value>200</value></transactionPricePerShare></transactionAmounts></nonDerivativeTransaction>
<nonDerivativeTransaction><transactionCoding><transactionCode>S</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>1000</value></transactionShares><transactionPricePerShare><value>210</value></transactionPricePerShare></transactionAmounts></nonDerivativeTransaction>
</nonDerivativeTable></ownershipDocument>"""


def test_form4_summary():
    s = filing_summary.summarize_form4(FORM4)
    # Open-market sales lead even when listed second; shares and value are summed.
    assert s["text"] == "Colette Kress (CFO) · 장내 매도 2,000주 (평균 $205.00, 약 $410K) · 세금용 주식 반납 500주"
    assert s["kind"] == "sell" and "10b5-1" in s["note"]
    assert filing_summary.summarize_form4("not xml") is None


def test_8k_items_and_names():
    assert filing_summary.summarize_8k("2.02,9.01")["text"] == "실적 발표"
    assert filing_summary.summarize_8k("9.01") is None  # exhibits only
    assert filing_summary.person_name("TETER TIMOTHY S.") == "Timothy S. Teter"
    assert filing_summary.person_name("VANGUARD GROUP INC") == "Vanguard Group Inc"


def test_insider_weekly_counts_only_open_market_trades():
    from app.services import insiders

    tx = pd.DataFrame(
        {
            "accession": ["a", "a", "b", "c", "d", "e"],
            "filed": ["2026-10-19", "2026-10-19", "2026-10-21", "2026-10-23", "2026-10-26", "2026-10-26"],
            "ticker": ["X", "X", "Y", "X", "Z", "Z"],
            "code": ["S", "S", "P", "F", "S", "G"],
            "shares": [100.0, 50.0, 10.0, 999.0, 20.0, 5.0],
            "price": [10.0, 12.0, 5.0, 10.0, 3.0, 0.0],
        }
    )
    w = insiders.weekly(tx)
    assert list(w["week"].dt.strftime("%Y-%m-%d")) == ["2026-10-19", "2026-10-26"]
    first = w.iloc[0]
    # Two sell rows in one filing count once; tax withholding (F) is not a sale.
    assert (first.buy_filings, first.sell_filings, first.buy_value, first.sell_value) == (1, 1, 50.0, 1600.0)
    assert w.iloc[1].sell_filings == 1 and w.iloc[1].buy_filings == 0
    assert insiders.ratio(30, 4) == 7.5 and insiders.ratio(3, 0) is None
    assert insiders.top_names(tx, "S")[0] == {"ticker": "X", "value": 1600, "filings": 1}


def test_margin_summary():
    from app.services import finra

    months = pd.period_range("2020-01", "2026-09", freq="M").strftime("%Y-%m")
    df = pd.DataFrame({"Year-Month": months[::-1], finra.DEBIT: [1000.0 + i for i in range(len(months))][::-1]})
    m = finra.margin_summary(df)
    assert m["as_of"] == "2026-09" and m["value"] == round((1000 + len(months) - 1) / 1000, 1)
    assert m["change_1m"] == pytest.approx(round(100 / (1000 + len(months) - 2), 1))
    assert m["low_5y"] <= m["value"] <= m["high_5y"]


def test_industry_names_are_complete():
    from app.industries import INDUSTRIES, industry_ko

    assert all(ko and about.endswith("요.") for ko, about in INDUSTRIES.values())
    assert industry_ko("Semiconductors")[0] == "반도체"
    assert industry_ko("Something New") == (None, None)


def test_yahoo_insider_rows_in_korean():
    row = filing_summary.yahoo_insider_row(
        {"Insider": "TETER TIMOTHY S", "Position": "General Counsel", "Text": "Sale at price 222.19 - 223.75 per share."}
    )
    assert row == {
        "kind_ko": "장내 매도",
        "detail_ko": "주당 $222.19–$223.75",
        "help_ko": "시장에서 판 거래예요.",
        "role_ko": "법무 책임자",
        "name_ko": "Timothy S Teter",
    }
    award = filing_summary.yahoo_insider_row({"Position": "Officer", "Text": "Stock Award(Grant) at price 0.00 per share."})
    assert (award["kind_ko"], award["detail_ko"], award["role_ko"]) == ("보상으로 주식 받음", "", "임원")
    assert filing_summary.yahoo_insider_row({"Text": "Purchase at price 10.50 per share."})["detail_ko"] == "주당 $10.50"
    # Unknown wording is kept as-is rather than dropped.
    assert filing_summary.yahoo_insider_row({"Text": "Something New", "Position": "Trustee"})["kind_ko"] == "Something New"


def test_form_labels_use_longest_prefix():
    from app.services.sec import _label

    assert _label("424B5") == "증권 발행 설명서"
    assert _label("4/A") == "내부자 거래 보고"
    assert _label("S-3ASR") == "증권 발행 신고"


def test_cash_value_multiples_and_values():
    assert [round(cheapness.cash_value_multiple(g), 1) for g in (0.0, 0.05, 0.10)] == [11.4, 16.4, 23.7]
    values = cheapness.cash_values(price=100, fcf_yield=5.0)
    assert values["low"] < values["base"] < values["high"]
    assert values["base"] == pytest.approx(100 * cheapness.cash_value_multiple(0.05) * 5 / 100, abs=0.01)
    assert cheapness.cash_values(price=100, fcf_yield=-1.0) is None
    assert cheapness.cash_values(price=None, fcf_yield=5.0) is None
    # Price equals the base value at a yield of 100 / multiple.
    assert cheapness.cash_value_gap(100 / cheapness.cash_value_multiple(0.05)) == pytest.approx(0, abs=1e-9)
    assert cheapness.cash_value_gap(10.0) < 0 < cheapness.cash_value_gap(3.0)
    assert cheapness.cash_value_gap(None) is None


def _cheap_row(**over) -> dict:
    row = {
        "sector": "Technology", "price": 100.0, "pe": 14.0, "pe@sector": 18.0,
        "pe_own_current": 14.0, "pe_own_median": 19.0, "pe_own_since": "2022-01-01", "fcf_yield": 8.0,
    }
    return row | over


def _by_key(row: dict) -> dict:
    return {c["key"]: c for c in cheapness.evaluate(row)["conditions"]}


def test_cheapness_counts_met_and_checkable():
    result = cheapness.evaluate(_cheap_row())
    assert (result["met"], result["checkable"]) == (3, 3)
    assert [c["key"] for c in result["conditions"]] == ["sector", "own_past", "cash"]
    result = cheapness.evaluate(_cheap_row(**{"pe@sector": 41.0, "pe_own_current": 20.0, "fcf_yield": 3.0}))
    assert (result["met"], result["checkable"]) == (0, 3)
    assert all(c["status"] == "unmet" and c["reason"] is None for c in result["conditions"])
    assert _by_key(_cheap_row(**{"pe@sector": 40.0}))["sector"]["status"] == "met"


@pytest.mark.parametrize(
    ("over", "key", "phrase"),
    [
        ({"pe": -3.0}, "sector", "적자"),
        ({"pe": None}, "sector", "적자"),
        ({"sector": "Real Estate"}, "sector", "리츠"),
        ({"pe@sector": None}, "sector", "5개"),
        ({"pe_own_current": None}, "own_past", "적자"),
        ({"pe_own_current": None, "pe_own_median": None}, "own_past", "과거"),
        ({"fcf_yield": -2.0}, "cash", "음수"),
        ({"fcf_yield": None}, "cash", "없어요"),
        ({"sector": "Financial Services", "fcf_yield": 8.0}, "cash", "금융"),
    ],
)
def test_cheapness_says_why_it_cannot_check(over, key, phrase):
    condition = _by_key(_cheap_row(**over))[key]
    assert condition["status"] == "na"
    assert phrase in condition["reason"]


def test_cheapness_with_an_older_snapshot_asks_for_a_rebuild():
    row = _cheap_row()
    for key in ("pe_own_current", "pe_own_median", "pe_own_since"):
        del row[key]
    result = cheapness.evaluate(row)
    assert (result["met"], result["checkable"]) == (2, 2)
    assert "다시 만들" in _by_key(row)["own_past"]["reason"]


def test_cheapness_treats_nan_as_missing():
    assert _by_key(_cheap_row(fcf_yield=float("nan")))["cash"]["status"] == "na"


def _two_lengths() -> tuple[pd.DataFrame, pd.DataFrame]:
    days = pd.bdate_range(end="2026-11-03", periods=1300)
    rng = np.random.default_rng(1)
    close = pd.Series(100 + rng.normal(0, 1, len(days)).cumsum(), index=days).clip(lower=5)
    # The highest close is older than two years, where it must not count.
    close.iloc[100] = 900
    frame = pd.DataFrame({"Close": close, "Volume": 1_000_000.0})
    return frame, frame[frame.index >= days[-1] - pd.Timedelta(days=730)]


def test_price_metrics_do_not_change_with_more_history():
    five, two = _two_lengths()
    assert ind.price_indicators(snapshot.recent_prices(five)) == ind.price_indicators(snapshot.recent_prices(two))


def _annual_income() -> pd.DataFrame:
    years = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"])
    return pd.DataFrame({y: [e] for y, e in zip(years, (10.0, 8.0, 6.0, 5.0))}, index=["Diluted EPS"])


def test_own_past_pe_uses_weekly_prices_and_any_timezone():
    five, _ = _two_lengths()
    naive = snapshot.own_past_pe(five, _annual_income())
    assert naive["pe_own_current"] == pytest.approx(five["Close"].iloc[-1] / 10, rel=0.05)
    assert naive["pe_own_median"] is not None and naive["pe_own_since"][:2] == "20"
    aware = five.copy()
    aware.index = aware.index.tz_localize("America/New_York")
    assert snapshot.own_past_pe(aware, _annual_income()) == naive
    assert snapshot.own_past_pe(five, pd.DataFrame())["pe_own_median"] is None
    assert snapshot.own_past_pe(pd.DataFrame(), _annual_income())["pe_own_median"] is None


def test_build_row_has_cheapness_inputs():
    five, _ = _two_lengths()
    row = build_row("X", five, {"freeCashflow": 5e9, "marketCap": 100e9}, _annual_income())
    assert row["cash_value_gap"] == pytest.approx(cheapness.cash_value_gap(5.0))
    assert row["pe_vs_own"] == pytest.approx(cheapness.pe_vs_own(row["pe_own_current"], row["pe_own_median"]))
    assert cheapness.evaluate(row)["checkable"] >= 2


def test_cheapness_endpoint_shape(monkeypatch):
    from app.routers import stocks

    monkeypatch.setattr(screener, "row", lambda s: _cheap_row(symbol=s) if s == "AAA" else None)
    monkeypatch.setattr(screener, "sector_peers", lambda sector: pd.DataFrame({"pe": [10.0, 20.0, 30.0, 40.0, -5.0, 50.0]}))
    monkeypatch.setattr(stocks, "load_meta", lambda: {"built_at": "2026-11-05T00:00:00+00:00"})
    out = stocks.cheapness_conditions("AAA")
    assert out["sector_median_pe"] == 30.0  # the loss-making -5 is left out
    assert (out["met"], out["checkable"]) == (3, 3) and out["in_snapshot"] is True
    assert stocks.cheapness_conditions("ZZZ") == {"in_snapshot": False, "built_at": "2026-11-05T00:00:00+00:00"}


def _cheap_frame() -> pd.DataFrame:
    # AAA meets all three; BBB is loss-making, so only its cash condition can be checked.
    base = {"sector": "Technology", "price": 100.0, "pe_own_since": "2022-01-01"}
    rows = [
        {"symbol": "AAA", "pe": 10.0, "pe_own_current": 10.0, "pe_own_median": 20.0, "fcf_yield": 9.0, "market_cap": 1.0},
        {"symbol": "BBB", "pe": -1.0, "pe_own_current": None, "pe_own_median": None, "fcf_yield": 9.0, "market_cap": 900.0},
        {"symbol": "CCC", "pe": 90.0, "pe_own_current": 30.0, "pe_own_median": 20.0, "fcf_yield": 9.0, "market_cap": 2.0},
        {"symbol": "DDD", "pe": 95.0, "pe_own_current": 30.0, "pe_own_median": 20.0, "fcf_yield": 9.0, "market_cap": 3.0},
        {"symbol": "EEE", "pe": 99.0, "pe_own_current": 30.0, "pe_own_median": 20.0, "fcf_yield": 1.0, "market_cap": 4.0},
    ]
    rows += [{"symbol": f"P{i}", "pe": 50.0 + i, "pe_own_current": 30.0, "pe_own_median": 20.0, "fcf_yield": 1.0, "market_cap": 0.5} for i in range(5)]
    return pd.DataFrame([base | r | {"name": r["symbol"]} for r in rows])


@pytest.fixture
def cheap_screener(monkeypatch):
    df = _cheap_frame()
    screener.set_frame(df)
    monkeypatch.setattr(screener, "frame", lambda: screener._frame)
    yield screener
    screener.set_frame(None)


def test_screener_sort_by_conditions_met(cheap_screener):
    out = cheap_screener.run(sort="cheap_met", limit=6)
    # DDD, CCC, P0 and P1 meet one of three; BBB's one of one comes after them.
    assert [r["symbol"] for r in out["rows"]] == ["AAA", "DDD", "CCC", "P0", "P1", "BBB"]
    assert (out["rows"][0]["cheap_met"], out["rows"][0]["cheap_checkable"]) == (3, 3)
    assert (out["rows"][5]["cheap_met"], out["rows"][5]["cheap_checkable"]) == (1, 1)
    assert out["cheap_counts"][3] == 1 and out["cheap_counts"][1] == 5


def test_screener_count_matches_the_stock_page(cheap_screener):
    for symbol in ("AAA", "BBB", "CCC", "EEE"):
        row = cheap_screener.row(symbol)
        result = cheapness.evaluate(row)
        assert (row["cheap_met"], row["cheap_checkable"]) == (result["met"], result["checkable"])


BANNED_WORDS = ("문제없", "문제가 없", "시장 탓", "회사 탓", "때문", "싸다", "싸요", "저평가", "매수", "매도", "추천", "목표가")


def test_decline_returns_use_each_window():
    close = prices(np.linspace(200, 100, 300))
    out = decline.returns(close)
    assert out["1m"] == pytest.approx((close.iloc[-1] / close.iloc[-22] - 1) * 100)
    assert set(out) == {"1m", "3m", "6m", "1y"}
    assert decline.returns(None)["3m"] is None
    assert decline.returns(prices(np.linspace(10, 9, 30)))["3m"] is None


def test_decline_sentences_compare_without_naming_a_cause():
    stock = {"1m": -8.0, "3m": -25.0, "6m": -30.0, "1y": -35.0}
    lines = decline.return_facts(stock, {"3m": -18.0}, {"3m": -9.0}, "정보기술")
    assert lines == ["3개월 동안 25% 떨어졌어요.", "정보기술보다 7%p 더 떨어졌어요.", "S&P 500보다 16%p 더 떨어졌어요."]
    # About the same, a smaller fall, and a market that rose.
    assert "정보기술 수익률과 비슷해요." in decline.return_facts({"3m": -10.0}, {"3m": -9.0}, {"3m": 1.0}, "정보기술")
    assert "섹터보다 5%p 덜 떨어졌어요." in decline.return_facts({"3m": -10.0}, {"3m": -15.0}, {}, "섹터")
    assert "같은 기간 S&P 500 수익률은 +4.0%예요." in decline.return_facts({"3m": -10.0}, {}, {"3m": 4.0})
    # Three months up: talk about the window where it did fall.
    assert decline.return_facts({"3m": 5.0, "1y": -20.0}, {}, {})[0] == "1년 동안 20% 떨어졌어요."
    assert decline.return_facts({"1m": 1.0, "3m": 5.0, "6m": 2.0, "1y": 9.0}, {}, {}) == ["이 기간에는 떨어지지 않았어요."]
    assert decline.return_facts(dict.fromkeys(("1m", "3m")), {}, {}) == []
    for line in lines:
        assert not any(word in line for word in BANNED_WORDS)


def _quarters(revenue, operating, shares, ends=("2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30")) -> pd.DataFrame:
    return pd.DataFrame(
        [revenue, operating, shares],
        index=["Total Revenue", "Operating Income", "Diluted Average Shares"],
        columns=pd.to_datetime(list(ends)),
    )


def test_quarterly_trend_compares_with_the_same_quarter_a_year_ago():
    income = _quarters([90, 80, 80, 80, 100], [9, 8, 8, 8, 20], [110, 100, 100, 100, 100])
    trend = decline.quarterly_trend(income)
    assert trend["quarter"] == "2026-06-30" and trend["has_year_ago"] is True
    assert trend["revenue_change"] == pytest.approx(-10)
    assert (trend["operating_margin"], trend["operating_margin_year_ago"]) == (pytest.approx(10), pytest.approx(20))
    assert trend["shares_change"] == pytest.approx(10)
    lines = decline.earnings_facts(trend)
    assert lines == ["매출이 전년 같은 분기보다 10% 줄었어요.", "영업이익률이 전년 같은 분기보다 10%p 낮아졌어요.", "희석 주식 수가 전년 같은 분기보다 10% 늘었어요."]
    for line in lines:
        assert not any(word in line for word in BANNED_WORDS)


def test_quarterly_trend_handles_gaps_and_good_results():
    # Results that held up produce numbers but no sentence.
    good = decline.quarterly_trend(_quarters([120, 1, 1, 1, 100], [24, 1, 1, 1, 20], [100, 1, 1, 1, 100]))
    assert decline.earnings_facts(good) == []
    # Only two recent quarters: no year-ago figures, and no crash.
    short = decline.quarterly_trend(_quarters([90, 80], [9, 8], [10, 10], ends=("2026-06-30", "2026-03-31")))
    assert short["has_year_ago"] is False and short["revenue_change"] is None and short["operating_margin"] == pytest.approx(10)
    assert decline.earnings_facts(short) == []
    assert decline.earnings_facts({"revenue_change": -0.4}) == []  # not "fell 0%"
    assert decline.quarterly_trend(pd.DataFrame()) is None
    assert decline.earnings_facts(None) == []
