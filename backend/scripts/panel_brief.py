"""Collect one stock's data from the running API into a Markdown brief for /panel.

    cd backend
    python -m scripts.panel_brief NVDA            # writes data/panel/NVDA-<date>.md
    python -m scripts.panel_brief NVDA --api http://localhost:8000

Every perspective agent reads the same brief, so they argue from the same numbers.
The server must be running (uvicorn app.main:app --port 8000). Sections whose
endpoint fails are listed at the end instead of stopping the brief.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "panel"
TIMEOUT = 120  # filings and news can be slow on a cold cache


def fetch(base: str, path: str):
    req = urllib.request.Request(base + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return json.load(res)


def num(v, unit: str = "", digits: int = 1) -> str:
    if v is None:
        return "—"
    if unit == "$B":
        return f"${v:,.1f}B"
    if unit == "$M":
        return f"${v:,.0f}M"
    suffix = {"%": "%", "%p": "%p", "x": "배", "mo": "개월"}.get(unit, "")
    return f"{v:,.{digits}f}{suffix}"


def money(v) -> str:
    if v is None:
        return "—"
    for size, label in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(v) >= size:
            return f"${v / size:,.1f}{label}"
    return f"${v:,.0f}"


def overview(d: dict) -> list[str]:
    summary = (d.get("summary") or "").strip()
    return [
        f"# {d['symbol']} · {d.get('name') or ''}",
        "",
        f"- 섹터·산업: {d.get('sector_label') or '—'} / {d.get('industry_label') or '—'} ({d.get('industry_about') or ''})",
        f"- 현재가: {num(d.get('price'), digits=2)} {d.get('currency', 'USD')} (전일 대비 {num(d.get('change_pct'), '%', 2)})",
        f"- 매출(최근 12개월): {money(d.get('revenue'))} · 직원 {d.get('employees') or '—'}명",
        f"- 섹터 비교 대상: 스냅샷 안 같은 섹터 {d.get('peer_count', 0)}개 회사",
        "",
        "## 사업 설명 (Yahoo, 영어 원문)",
        "",
        summary or "—",
    ]


def metric_table(d: dict, catalog: dict) -> list[str]:
    groups = {g["key"]: g["label"] for g in catalog["groups"]}
    dist = catalog.get("distribution", {})
    prefer = {"low": "낮을수록", "high": "높을수록"}
    lines = [
        "## 지표 (카드 값은 이 종목만 방금 새로 계산, 섹터·전체 분포는 스냅샷 기준)",
        "",
        "섹터 백분위: 같은 섹터 안 0 = 가장 낮은 값, 100 = 가장 높은 값. "
        "'보통 유리하게 읽는 쪽'은 읽는 방향일 뿐 판정이 아니에요.",
    ]
    current = None
    for m in catalog["metrics"]:
        if m["group"] != current:
            current = m["group"]
            lines += [
                "",
                f"### {groups.get(current, current)}",
                "",
                "| 지표 | 값 | 섹터 중앙값 | 섹터 백분위 | 전체 10%·50%·90% | 보통 유리하게 읽는 쪽 |",
                "|---|---|---|---|---|---|",
            ]
        k, unit = m["key"], m["unit"]
        v = d["metrics"].get(k)
        shown = "음수(손실·자본잠식)" if m.get("positive_only") and v is not None and v <= 0 else num(v, unit)
        pct = d.get("sector_percentile", {}).get(k)
        q = dist.get(k)
        spread = f"{num(q['p10'], unit)} · {num(q['p50'], unit)} · {num(q['p90'], unit)}" if q else "—"
        lines.append(
            f"| {m['label']} | {shown} | {num(d['sector_median'].get(k), unit)} | "
            f"{'—' if pct is None else f'{pct:.0f}'} | {spread} | {prefer.get(m.get('prefer') or '', '—')} |"
        )
    return lines


def own_past(v: dict) -> list[str]:
    lines = ["## 자기 과거 대비 밸류에이션 (직전 회계연도 실적 기준이라 위 PER과 다를 수 있어요)", ""]
    for key, label in (("pe", "PER"), ("ps", "PSR")):
        r = v.get(key)
        if not r:
            lines.append(f"- {label}: 계산할 수 없어요")
            continue
        lines.append(
            f"- {label} 지금 {num(r['current'], 'x')}: 최근 {r['years']}년({r['since']}~) "
            f"최저 {num(r['low'], 'x')} · 중앙값 {num(r['median'], 'x')} · 최고 {num(r['high'], 'x')}, "
            f"그 기간 중 하위 {r['percentile']:.0f}% 위치"
        )
    return lines


def price_path(h: dict) -> list[str]:
    closes = [c for c in h["close"] if c is not None]
    if not closes:
        return ["## 가격 흐름 (1년)", "", "가격 데이터가 없어요."]
    hi, lo, last = max(closes), min(closes), closes[-1]
    sma50 = next((v for v in reversed(h["sma_short"]) if v is not None), None)
    sma200 = next((v for v in reversed(h["sma_long"]) if v is not None), None)
    vols = [v for v in h["volume"] if v]
    vol20 = sum(vols[-20:]) / max(len(vols[-20:]), 1)
    vol_all = sum(vols) / max(len(vols), 1)
    # Monthly closes so the agents can see the path, not just the endpoints.
    monthly, seen = [], set()
    for d, c in zip(reversed(h["dates"]), reversed(h["close"])):
        if c is not None and d[:7] not in seen:
            seen.add(d[:7])
            monthly.append(f"{d[:7]} {c:,.2f}")
    return [
        "## 가격 흐름 (1년, 일봉)",
        "",
        f"- 마지막 종가: {h['dates'][-1]} {last:,.2f}",
        f"- 1년 범위: {lo:,.2f} ~ {hi:,.2f} (고점 대비 {num((last / hi - 1) * 100, '%')}, 저점 대비 {num((last / lo - 1) * 100, '%')})",
        f"- 50일선 {num(sma50, digits=2)} · 200일선 {num(sma200, digits=2)}"
        + (f" (50일선이 200일선 {'위' if sma50 > sma200 else '아래'})" if sma50 and sma200 else ""),
        f"- 최근 20일 평균 거래량은 1년 평균의 {num(vol20 / vol_all if vol_all else None, 'x', 2)}",
        f"- 월별 마지막 종가(최근→과거): {' / '.join(monthly[:13])}",
    ]


def flows(o: dict) -> list[str]:
    lines = [
        "## 수급·보유",
        "",
        f"- 공매도 비율(유통주식 대비) {num(o.get('short_float'), '%')} · 공매도 잔고 소진일 {num(o.get('short_ratio'), digits=1)}일",
        f"- 내부자 보유 {num(o.get('insider_pct'), '%')} · 기관 보유 {num(o.get('institution_pct'), '%')}",
        "",
        "### 최근 내부자 거래 (Yahoo, 최신순 최대 12건)",
        "",
    ]
    rows = o.get("insider_transactions") or []
    for r in rows[:12]:
        detail = f" {r['detail_ko']}" if r.get("detail_ko") else ""
        lines.append(
            f"- {r.get('Start Date', '')} {r.get('name_ko') or r.get('Insider')} ({r.get('role_ko') or r.get('Position')}) · "
            f"{r.get('kind_ko') or r.get('Text')} {r.get('Shares') or 0:,}주{detail} · {money(r.get('Value'))}"
        )
    if not rows:
        lines.append("- 기록이 없어요")
    lines += ["", "### 상위 기관 보유자", ""]
    for r in (o.get("institutional_holders") or [])[:5]:
        change = r.get("pctChange")
        lines.append(
            f"- {r.get('Holder')}: {num((r.get('pctHeld') or 0) * 100, '%', 2)}"
            + (f" (직전 보고 대비 {num(change * 100, '%')})" if change is not None else "")
            + f", {str(r.get('Date Reported', ''))[:10]} 보고"
        )
    return lines


def filings(f: dict) -> list[str]:
    lines = ["## 최근 SEC 공시 (최신순 최대 15건)", ""]
    for r in (f.get("filings") or [])[:15]:
        s = r.get("summary") or {}
        text = s.get("text") or r.get("description") or ""
        note = f" — {s['note']}" if s.get("note") else ""
        lines.append(f"- {r['date']} {r['form']} {r.get('label', '')}: {text}{note}")
    return lines if len(lines) > 2 else lines + ["- 공시가 없어요"]


def news(n: dict) -> list[str]:
    lines = ["## 최근 뉴스 제목 (최신순 최대 15건, 본문은 읽지 않았어요)", "", "이 종목 피드에도 시장 전체 기사가 섞여 와요. 종목과 관계없는 제목은 무시하세요.", ""]
    for a in (n.get("articles") or [])[:15]:
        lines.append(f"- {str(a.get('published', ''))[:10]} [{a.get('source', '')}] {a.get('title', '')}")
    return lines if len(lines) > 2 else lines + ["- 뉴스가 없어요"]


def market(ind: dict, sectors: dict, cal: dict, sector_key: str | None) -> list[str]:
    lines = ["## 시장 배경", "", "### 주요 지표", ""]
    for i in ind.get("indicators", []):
        change = f"{i['change_1m']:+.2f}{'%' if i.get('change_kind') == 'pct' else i.get('unit', '')}" if i.get("change_1m") is not None else "—"
        pct = i.get("percentile_5y")
        lines.append(
            f"- {i['label']} {'$' if i.get('unit') == '$' else ''}{num(i.get('value'), digits=2)}{i.get('unit', '') if i.get('unit') not in ('pt', '$') else ''} "
            f"({i.get('as_of')}, 한 달 변화 {change}, 5년 중 {'—' if pct is None else f'{pct:.0f}'}% 위치)"
        )
    fg = ind.get("fear_greed")
    if fg:
        lines.append(f"- CNN 공포·탐욕 지수 {fg['value']:.0f} ({fg['rating']}, 1주 전 {fg['previous_week']:.0f}, 1달 전 {fg['previous_month']:.0f})")
    lines += ["", "### 시장 상태 (고정 규칙으로 쓴 설명)", ""]
    lines += [f"- {r['label']}: {r['text']}" for r in ind.get("regime", [])]
    lines += [
        "",
        f"### 섹터 ETF 수익률 (S&P 500 한 달 {num(sectors.get('spy_1m'), '%')})",
        "",
        "| 섹터 | 1주 | 1개월 | 3개월 | 1개월 S&P 대비 |",
        "|---|---|---|---|---|",
    ]
    for s in sectors.get("sectors", []):
        mark = " ← 이 종목" if s.get("sector") == sector_key else ""
        lines.append(
            f"| {s['label']} ({s['etf']}){mark} | {num(s.get('ret_1w'), '%')} | {num(s.get('ret_1m'), '%')} | "
            f"{num(s.get('ret_3m'), '%')} | {num(s.get('vs_spy_1m'), '%p')} |"
        )
    lines += ["", "### 앞으로 30일 일정", ""]
    lines += [f"- {e['date']} {e['title']}" for e in (cal.get("events") or [])[:15]] or ["- 일정이 없어요"]
    lines += [f"- (참고) {s}" for s in cal.get("setup") or []]
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("symbol")
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    sym = args.symbol.upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", sym):
        sys.exit(f"종목 코드 형식이 올바르지 않아요: {args.symbol}")
    base = args.api.rstrip("/") + "/api"

    paths = {
        "detail": f"/stocks/{sym}",
        "catalog": "/screener/metrics",
        "valuation": f"/stocks/{sym}/valuation",
        "history": f"/stocks/{sym}/history?range=1y",
        "ownership": f"/stocks/{sym}/ownership",
        "filings": f"/stocks/{sym}/filings",
        "news": f"/stocks/{sym}/news",
        "indicators": "/dashboard/indicators",
        "sectors": "/dashboard/sectors",
        "calendar": f"/macro/calendar?days=30&symbols={sym}",
    }
    data, failed = {}, []
    with ThreadPoolExecutor(max_workers=len(paths)) as pool:
        futures = {k: pool.submit(fetch, base, p) for k, p in paths.items()}
        for k, fut in futures.items():
            try:
                data[k] = fut.result()
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                failed.append(f"{paths[k]}: {e}")

    if "detail" not in data or "catalog" not in data:
        sys.exit("종목 기본 정보를 못 가져왔어요. backend 서버(uvicorn)가 켜져 있는지 확인하세요.\n" + "\n".join(failed))

    d = data["detail"]
    sections = [overview(d), metric_table(d, data["catalog"])]
    builders = [
        ("valuation", own_past),
        ("history", price_path),
        ("ownership", flows),
        ("filings", filings),
        ("news", news),
    ]
    sections += [build(data[k]) for k, build in builders if k in data]
    if {"indicators", "sectors", "calendar"} <= data.keys():
        sections.append(market(data["indicators"], data["sectors"], data["calendar"], d.get("sector")))
    sections.append(
        ["## 못 가져온 데이터", ""] + ([f"- {f}" for f in failed] or ["- 없음"])
        + ["", f"_작성 {date.today().isoformat()} · stock-scout API 기준. 투자 권유가 아니라 판단 재료예요._"]
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{sym}-{date.today().isoformat()}.md"
    out.write_text("\n\n".join("\n".join(s) for s in sections) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
