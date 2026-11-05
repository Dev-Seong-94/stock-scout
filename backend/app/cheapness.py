"""The three "is it cheap?" conditions shown in the screener and on the stock page.

Pure functions over one snapshot row, so both places always agree. They state
how a number compares; they never say a stock is cheap or worth buying.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.indicators import _clean

MAX_SECTOR_PERCENTILE = 40  # same bar as the "수익성 좋은데 덜 비싼" example combination

DISCOUNT = 0.10
TERMINAL_GROWTH = 0.025
YEARS = 10
# Fixed for every company: the point is what you would have to believe, not a forecast.
SCENARIOS = {"low": 0.0, "base": 0.05, "high": 0.10}

# Banks' and insurers' operating cash flow includes lending and deposits, so
# "free cash flow" says nothing about them.
NO_FCF_SECTORS = {"Financial Services"}
# Depreciation makes REIT earnings a poor measure, so PER comparisons across them mislead.
NO_PE_SECTORS = {"Real Estate"}

REBUILD_REASON = "스냅샷을 다시 만들면 볼 수 있어요."


def cash_value_multiple(growth: float, discount: float = DISCOUNT, terminal: float = TERMINAL_GROWTH, years: int = YEARS) -> float:
    """Value of a stream of free cash flow, as a multiple of today's FCF."""
    near = sum(((1 + growth) / (1 + discount)) ** t for t in range(1, years + 1))
    far = (1 + growth) ** years * (1 + terminal) / (discount - terminal) / (1 + discount) ** years
    return near + far


def cash_values(price: float | None, fcf_yield: float | None) -> dict[str, float] | None:
    """Value per share under each scenario, or None when FCF isn't positive."""
    price, fcf_yield = _clean(price), _clean(fcf_yield)
    if price is None or fcf_yield is None or price <= 0 or fcf_yield <= 0:
        return None
    return {name: round(price * cash_value_multiple(g) * fcf_yield / 100, 2) for name, g in SCENARIOS.items()}


def cash_value_gap(fcf_yield: float | None) -> float | None:
    """Price vs the base scenario's value in %: below 0 means the price is lower."""
    fcf_yield = _clean(fcf_yield)
    if fcf_yield is None or fcf_yield <= 0:
        return None
    return (100 / (cash_value_multiple(SCENARIOS["base"]) * fcf_yield) - 1) * 100


def pe_vs_own(current: float | None, median: float | None) -> float | None:
    """Current PER vs its own past median in %: below 0 means lower than usual."""
    current, median = _clean(current), _clean(median)
    if current is None or median is None or current <= 0 or median <= 0:
        return None
    return (current / median - 1) * 100


def _condition(key: str, label: str, met: bool | None, reason: str | None = None, **values) -> dict:
    status = "na" if met is None else "met" if met else "unmet"
    return {"key": key, "label": label, "status": status, "reason": reason, **values}


def _other_currency(row: Mapping) -> str | None:
    """The statements' currency when it differs from the share price's, e.g. CNY for PDD."""
    currency = row.get("statement_currency")
    return currency if isinstance(currency, str) and currency else None


def _currency_reason(row: Mapping) -> str:
    return f"재무제표가 {_other_currency(row)} 기준이라 달러 주가와 바로 비교할 수 없어요."


def _sector_condition(row: Mapping) -> dict:
    pe, percentile = _clean(row.get("pe")), _clean(row.get("pe@sector"))
    facts = {"pe": pe, "percentile": percentile}
    reason = None
    if row.get("sector") in NO_PE_SECTORS:
        reason = "리츠는 감가상각 때문에 이익이 작게 잡혀서 PER로 비교하기 어려워요."
    elif pe is None or pe <= 0:
        reason = "PER이 없거나 음수라 비교할 수 없어요. 보통 최근 12개월이 적자일 때 그래요."
    elif percentile is None:
        reason = "같은 섹터에 비교할 값이 5개 미만이에요."
    if reason:
        return _condition("sector", "업종 대비", None, reason, **facts)
    return _condition("sector", "업종 대비", percentile <= MAX_SECTOR_PERCENTILE, **facts)


def _own_past_condition(row: Mapping) -> dict:
    current, median = _clean(row.get("pe_own_current")), _clean(row.get("pe_own_median"))
    since = row.get("pe_own_since")
    facts = {"current": current, "median": median, "since": since if isinstance(since, str) else None}
    reason = None
    if "pe_own_median" not in row:
        reason = REBUILD_REASON
    elif _other_currency(row):
        reason = _currency_reason(row)
    elif median is None:
        reason = "비교할 만한 과거 PER이 없어요. 상장한 지 얼마 안 됐거나 대부분 적자였을 수 있어요."
    elif current is None:
        reason = "최근 회계연도가 적자라 지금 PER이 없어요."
    if reason:
        return _condition("own_past", "자기 과거 대비", None, reason, **facts)
    return _condition("own_past", "자기 과거 대비", current < median, **facts)


def _cash_condition(row: Mapping) -> dict:
    price, fcf_yield = _clean(row.get("price")), _clean(row.get("fcf_yield"))
    values = None if row.get("sector") in NO_FCF_SECTORS or _other_currency(row) else cash_values(price, fcf_yield)
    facts = {"price": price, "fcf_yield": fcf_yield, "values": values}
    reason = None
    if row.get("sector") in NO_FCF_SECTORS:
        reason = "금융사는 영업현금흐름에 대출·예금 흐름이 섞여 있어서 계산하지 않아요."
    elif _other_currency(row):
        reason = _currency_reason(row)
    elif fcf_yield is None:
        reason = "잉여현금흐름(FCF) 데이터가 없어요."
    elif fcf_yield <= 0:
        reason = "최근 12개월 잉여현금흐름(FCF)이 음수라 이 계산이 의미가 없어요."
    elif values is None:
        reason = "가격 데이터가 없어요."
    if reason:
        return _condition("cash", "현금 기준", None, reason, **facts)
    return _condition("cash", "현금 기준", price < values["base"], **facts)


def evaluate(row: Mapping) -> dict:
    """All three conditions for one snapshot row, plus how many were met and could be checked."""
    conditions = [_sector_condition(row), _own_past_condition(row), _cash_condition(row)]
    return {
        "conditions": conditions,
        "met": sum(c["status"] == "met" for c in conditions),
        "checkable": sum(c["status"] != "na" for c in conditions),
    }
