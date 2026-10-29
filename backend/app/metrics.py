"""Screener metric definitions.

This is the single source of truth for which metrics exist, how they are
labelled in Korean, and the explanation shown next to each filter. The
frontend fetches it from /api/screener/metrics, so adding a metric here (and
computing it in snapshot.py) is all that is needed to make it filterable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    group: str
    unit: str  # "x" (배), "%", "$B", "$M", "" (plain number)
    description: str  # 무엇을 재는지
    reading: str  # 어떻게 읽는지
    caveat: str = ""  # 함정, 주의할 점
    slider_min: float = 0
    slider_max: float = 100
    step: float = 1
    # Multiples like PER are meaningless when ≤ 0 (losses, negative equity):
    # such values are left out of filters, percentiles and medians.
    positive_only: bool = False


GROUPS = [
    ("valuation", "밸류에이션"),
    ("profitability", "수익성"),
    ("growth", "성장성"),
    ("health", "재무 건전성"),
    ("technical", "가격·기술적"),
    ("size", "규모·수급"),
    ("speculative", "적자 성장주 점검"),
]

METRICS: list[Metric] = [
    # ---------- 밸류에이션 ----------
    Metric(
        "pe", "PER", "valuation", "x",
        "주가 ÷ 주당순이익(최근 12개월). 회사가 1년에 버는 이익의 몇 배에 거래되는지.",
        "같은 업종 안에서 비교해야 의미가 있어요. 낮으면 이익 대비 싸고, 높으면 시장이 미래 성장을 크게 기대한다는 뜻이에요.",
        "적자 기업은 값이 없어요. 일회성 이익이 크면 일시적으로 낮아 보일 수 있어요.",
        0, 100, 1, positive_only=True,
    ),
    Metric(
        "forward_pe", "선행 PER", "valuation", "x",
        "주가 ÷ 애널리스트가 예상한 향후 12개월 주당순이익.",
        "PER보다 낮으면 이익이 늘 것으로 예상된다는 뜻이에요.",
        "예상치라서 틀릴 수 있고, 커버하는 애널리스트가 적은 종목은 부정확해요. 적자가 예상되면(음수) 필터에서 빠져요.",
        0, 100, 1, positive_only=True,
    ),
    Metric(
        "peg", "PEG", "valuation", "x",
        "PER ÷ 이익 성장률. 성장 속도를 감안한 PER.",
        "1 안팎이면 성장률만큼의 가격, 1보다 많이 낮으면 성장 대비 싸다고 보는 경우가 많아요.",
        "성장률 추정에 따라 크게 달라져요. 이익이 줄어드는 중이면(음수) 필터에서 빠져요.",
        0, 5, 0.1, positive_only=True,
    ),
    Metric(
        "pb", "PBR", "valuation", "x",
        "주가 ÷ 주당순자산. 장부상 순자산의 몇 배에 거래되는지.",
        "은행·보험·제조업처럼 자산이 중요한 업종에서 쓸모가 커요. 1 미만이면 장부가보다 싸게 거래되는 중이에요.",
        "소프트웨어처럼 무형자산 중심 기업은 높게 나오는 게 정상이에요. 자사주 매입이 많으면 음수가 되는데, 음수는 필터에서 빠져요.",
        0, 20, 0.1, positive_only=True,
    ),
    Metric(
        "ps", "PSR", "valuation", "x",
        "시가총액 ÷ 최근 12개월 매출.",
        "아직 이익이 안 나는 성장 기업을 비교할 때 유용해요.",
        "이익률이 낮은 업종(유통 등)은 원래 낮게 나와요.",
        0, 30, 0.5, positive_only=True,
    ),
    Metric(
        "ev_ebitda", "EV/EBITDA", "valuation", "x",
        "기업가치(시총 + 순부채) ÷ 감가상각 전 영업이익.",
        "부채까지 포함한 몸값이라 부채 수준이 다른 기업끼리 비교하기 좋아요.",
        "설비 투자가 큰 업종은 감가상각이 실제 비용이라 낮아 보일 수 있어요. EBITDA가 적자(음수)면 필터에서 빠져요.",
        0, 50, 0.5, positive_only=True,
    ),
    Metric(
        "fcf_yield", "FCF 수익률", "valuation", "%",
        "잉여현금흐름 ÷ 시가총액. 지금 가격에 사면 현금이 연 몇 % 남는지.",
        "높을수록 현금 창출력 대비 싸요. 배당·자사주 여력의 근거가 돼요.",
        "한 해 실적만 보기 때문에 투자 시기에 따라 출렁여요.",
        -10, 20, 0.5,
    ),
    Metric(
        "dividend_yield", "배당수익률", "valuation", "%",
        "연간 주당 배당금 ÷ 주가.",
        "현금 수익을 원할 때 보는 지표예요.",
        "주가가 급락해서 높아진 경우가 많아요. 배당 성향과 함께 보세요.",
        0, 10, 0.1,
    ),
    # ---------- 수익성 ----------
    Metric(
        "roe", "ROE", "profitability", "%",
        "순이익 ÷ 자기자본. 주주 돈으로 1년에 몇 %를 벌었는지.",
        "꾸준히 15% 이상이면 자본을 효율적으로 쓰는 편으로 봐요.",
        "부채가 많거나 자기자본이 작으면 부풀려져요. 부채비율과 같이 보세요.",
        -50, 100, 1,
    ),
    Metric(
        "roa", "ROA", "profitability", "%",
        "순이익 ÷ 총자산. 가진 자산 전체로 얼마나 버는지.",
        "부채 효과를 뺀 수익성이라 ROE의 착시를 걸러줘요.",
        "금융업은 원래 낮게 나와요.",
        -20, 40, 0.5,
    ),
    Metric(
        "gross_margin", "매출총이익률", "profitability", "%",
        "(매출 − 매출원가) ÷ 매출.",
        "높을수록 가격 결정력이나 제품 경쟁력이 있다는 신호예요.",
        "업종 차이가 커서 같은 업종끼리 비교하세요.",
        0, 100, 1,
    ),
    Metric(
        "operating_margin", "영업이익률", "profitability", "%",
        "영업이익 ÷ 매출. 본업에서 남기는 비율.",
        "추세가 오르고 있는지가 중요해요.",
        "", -50, 60, 1,
    ),
    Metric(
        "net_margin", "순이익률", "profitability", "%",
        "순이익 ÷ 매출.",
        "영업이익률과 차이가 크면 이자·세금·일회성 손익을 확인하세요.",
        "", -50, 60, 1,
    ),
    # ---------- 성장성 ----------
    Metric(
        "revenue_growth", "매출 성장률", "growth", "%",
        "최근 분기 매출의 전년 같은 분기 대비 증가율.",
        "회사가 커지고 있는지를 가장 직접적으로 보여줘요.",
        "인수합병으로 늘어난 경우도 포함돼요.",
        -50, 100, 1,
    ),
    Metric(
        "earnings_growth", "이익 성장률", "growth", "%",
        "최근 분기 순이익의 전년 같은 분기 대비 증가율.",
        "매출보다 빠르게 늘면 이익률이 개선 중이라는 뜻이에요.",
        "작년 이익이 매우 작았으면 수백 %로 튈 수 있어요.",
        -100, 200, 5,
    ),
    Metric(
        "revenue_cagr_3y", "매출 3년 CAGR", "growth", "%",
        "최근 3개 회계연도 매출의 연평균 성장률.",
        "분기 성장률보다 덜 출렁여서 꾸준함을 보기 좋아요.",
        "연간 재무제표가 4년치 이상 있어야 계산돼요.",
        -30, 80, 1,
    ),
    # ---------- 재무 건전성 ----------
    Metric(
        "debt_to_equity", "부채비율(D/E)", "health", "x",
        "총차입금 ÷ 자기자본.",
        "낮을수록 금리 상승이나 불황에 버티기 쉬워요. 1 이하면 보수적인 편이에요.",
        "자사주 매입으로 자기자본이 작아진 기업은 크게 나와요.",
        0, 5, 0.1,
    ),
    Metric(
        "current_ratio", "유동비율", "health", "x",
        "유동자산 ÷ 유동부채. 1년 안에 갚을 빚을 감당할 수 있는지.",
        "1.5 이상이면 단기 지급 능력이 여유 있는 편이에요.",
        "", 0, 5, 0.1,
    ),
    Metric(
        "interest_coverage", "이자보상배율", "health", "x",
        "영업이익(EBIT) ÷ 이자비용.",
        "1 미만이면 영업으로 이자도 못 내는 상태예요. 고금리 환경에서 중요해요.",
        "차입금이 거의 없으면 아주 크게 나와요.",
        0, 50, 1,
    ),
    # ---------- 가격·기술적 ----------
    Metric(
        "rsi14", "RSI(14)", "technical", "",
        "최근 14거래일 상승폭과 하락폭의 비율로 만든 0–100 지수.",
        "70 이상은 단기 과열, 30 이하는 단기 과매도로 많이 해석해요.",
        "강한 추세에서는 오래 70 이상(또는 30 이하)에 머물기도 해요.",
        0, 100, 1,
    ),
    Metric(
        "dist_sma50", "50일선 대비", "technical", "%",
        "현재가가 50일 이동평균보다 몇 % 위(+)·아래(−)에 있는지.",
        "중기 추세 안에서 위치를 봐요.",
        "", -50, 50, 1,
    ),
    Metric(
        "dist_sma200", "200일선 대비", "technical", "%",
        "현재가가 200일 이동평균보다 몇 % 위(+)·아래(−)에 있는지.",
        "200일선 위면 장기 상승 추세로 보는 경우가 많아요.",
        "", -60, 80, 1,
    ),
    Metric(
        "from_52w_high", "52주 고점 대비", "technical", "%",
        "최근 1년 최고 종가보다 몇 % 아래인지(0이면 신고가).",
        "0에 가까우면 신고가 근처, 크게 음수면 많이 빠진 상태예요.",
        "", -90, 0, 1,
    ),
    Metric("ret_1m", "1개월 수익률", "technical", "%", "최근 약 21거래일 주가 변화율.", "단기 흐름.", "", -50, 50, 1),
    Metric("ret_3m", "3개월 수익률", "technical", "%", "최근 약 63거래일 주가 변화율.", "", "", -60, 100, 1),
    Metric("ret_6m", "6개월 수익률", "technical", "%", "최근 약 126거래일 주가 변화율.", "모멘텀 전략에서 자주 쓰는 기간이에요.", "", -70, 150, 1),
    Metric("ret_1y", "1년 수익률", "technical", "%", "최근 약 1년 주가 변화율.", "", "", -80, 300, 5),
    Metric(
        "volatility_3m", "변동성(3개월)", "technical", "%",
        "최근 3개월 일간 수익률의 표준편차를 연율화한 값.",
        "높을수록 주가가 크게 출렁여요. 대형 우량주는 보통 20–30% 안팎이에요.",
        "", 0, 150, 1,
    ),
    Metric(
        "beta", "베타", "technical", "",
        "시장(S&P 500)이 1% 움직일 때 이 종목이 평균 몇 % 움직였는지.",
        "1보다 크면 시장보다 민감하고, 작으면 덜 민감해요.",
        "과거 5년 월간 데이터 기준이라 사업이 바뀐 회사는 맞지 않을 수 있어요.",
        -1, 4, 0.1,
    ),
    Metric(
        "rel_volume", "상대 거래량", "technical", "x",
        "최근 5일 평균 거래량 ÷ 3개월 평균 거래량.",
        "1.5 이상이면 평소보다 관심이 몰리는 중이에요. 뉴스나 공시를 확인해 보세요.",
        "", 0, 5, 0.1,
    ),
    # ---------- 규모·수급 ----------
    Metric(
        "market_cap", "시가총액", "size", "$B",
        "주가 × 발행주식수, 단위는 10억 달러.",
        "2 미만 소형주, 2–10 중형주, 10 이상 대형주로 흔히 나눠요.",
        "", 0, 4000, 10,
    ),
    Metric(
        "avg_dollar_volume", "평균 거래대금", "size", "$M",
        "3개월 평균 거래량 × 주가, 단위는 100만 달러.",
        "작으면 사고팔 때 가격이 쉽게 움직여요(유동성 위험).",
        "", 0, 5000, 10,
    ),
    Metric(
        "short_float", "공매도 비율", "size", "%",
        "유통주식 중 공매도된 주식의 비율.",
        "높으면 하락에 베팅한 투자자가 많다는 뜻이에요. 반대로 숏스퀴즈 가능성으로 보기도 해요.",
        "보고 주기가 2주라서 최신 상황과 다를 수 있어요.",
        0, 40, 0.5,
    ),
    Metric(
        "insider_pct", "내부자 보유율", "size", "%",
        "경영진·대주주 등 내부자가 가진 지분 비율.",
        "높으면 경영진과 주주의 이해관계가 비슷하다고 보기도 해요.",
        "", 0, 80, 1,
    ),
    Metric(
        "institution_pct", "기관 보유율", "size", "%",
        "펀드·연기금 등 기관투자자 보유 비율.",
        "너무 낮으면 관심 밖, 아주 높으면 이미 많이 알려진 종목이에요.",
        "", 0, 100, 1,
    ),
    # ---------- 적자 성장주 점검 ----------
    Metric(
        "cash_runway", "현금 런웨이", "speculative", "mo",
        "보유 현금 ÷ 1년간 현금 소진액 × 12. 지금 속도로 돈을 쓰면 몇 개월 버티는지.",
        "적자 기업에서 가장 먼저 볼 숫자예요. 24개월 이상이면 당장 돈을 구할 필요는 적은 편이고, 12개월 미만이면 증자나 차입 가능성이 커요.",
        "현금흐름이 흑자인 회사는 돈이 줄지 않으니 값이 없어요. 영업현금흐름과 잉여현금흐름 중 더 많이 쓴 쪽으로 보수적으로 계산해요.",
        0, 120, 1,
    ),
    Metric(
        "share_change_1y", "주식 수 증가율", "speculative", "%",
        "최근 회계연도 희석 주식 수가 1년 전보다 몇 % 늘었는지.",
        "늘어난 만큼 기존 주주의 몫이 줄어요(희석). 연 5% 이하면 무난, 10%를 넘으면 증자·주식보상이 많다는 신호예요. 음수면 자사주 매입으로 줄어든 거예요.",
        "인수합병 대금을 주식으로 낸 해에는 크게 튈 수 있어요.",
        -20, 50, 1,
    ),
    Metric(
        "gross_margin_change", "매출총이익률 변화", "speculative", "%p",
        "최근 회계연도 매출총이익률 − 1년 전 매출총이익률.",
        "적자 기업이 흑자로 가는 길은 보통 매출총이익률 개선에서 시작돼요. 플러스면 팔수록 남는 구조로 가는 중이에요.",
        "매출이 아주 작은 초기 기업은 크게 출렁여요.",
        -30, 30, 1,
    ),
]

METRIC_KEYS = {m.key for m in METRICS}

SECTORS = {
    "Technology": "정보기술",
    "Healthcare": "헬스케어",
    "Financial Services": "금융",
    "Consumer Cyclical": "경기소비재",
    "Communication Services": "커뮤니케이션",
    "Industrials": "산업재",
    "Consumer Defensive": "필수소비재",
    "Energy": "에너지",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
    "Basic Materials": "소재",
}

# Filter keys ending in this suffix filter on the stock's percentile (0–100)
# within its own sector instead of the raw value: "pe@sector": [None, 30]
# means "PER in the cheapest 30% of its sector".
SECTOR_SUFFIX = "@sector"

# Starting points for filter combinations. They show how metrics combine;
# they are not recommendations. "checklist" is what to verify by hand before
# trusting anything the combination finds.
PRESETS = [
    {
        "id": "quality-value",
        "name": "수익성 좋은데 덜 비싼",
        "note": "ROE·영업이익률은 섹터 상위 40%, PER은 섹터 하위 40%인 종목",
        "filters": {"roe@sector": [60, None], "operating_margin@sector": [60, None], "pe@sector": [None, 40]},
        "checklist": [
            "이익이 일회성(자산 매각, 세금 환급 등)으로 부풀지 않았는지 순이익률과 영업이익률을 비교해 보세요.",
            "ROE가 높은 이유가 빚 때문은 아닌지 부채비율을 함께 보세요.",
        ],
    },
    {
        "id": "growth-momentum",
        "name": "성장 + 상승 추세",
        "note": "매출이 20% 이상 늘고 주가가 200일선 위에 있는 종목",
        "filters": {"revenue_growth": [20, None], "dist_sma200": [0, None]},
        "checklist": [
            "성장이 인수합병 덕분인지 회사 자체 성장인지 실적 발표(8-K)에서 확인하세요.",
            "이미 많이 오른 종목은 기대가 가격에 반영돼 있어요. 종목 화면의 PER·PSR 범위 막대를 보세요.",
        ],
    },
    {
        "id": "oversold-large",
        "name": "많이 빠진 대형주",
        "note": "시총 50B 이상, RSI 35 이하, 52주 고점 대비 −20% 이하",
        "filters": {"market_cap": [50, None], "rsi14": [None, 35], "from_52w_high": [None, -20]},
        "checklist": [
            "왜 빠졌는지부터 확인하세요: 최근 실적 발표와 가이던스(종목 화면 → 공시의 8-K, 뉴스).",
            "실적 전망이 계속 낮아지는 중이면 '싸 보여도 더 싸지는' 가치 함정일 수 있어요.",
            "섹터 전체가 빠졌는지(대시보드 섹터 표), 이 회사만 빠졌는지 구분하세요.",
        ],
    },
    {
        "id": "steady-income",
        "name": "안정적인 배당",
        "note": "배당수익률 3% 이상, 부채비율은 같은 섹터 안에서 낮은 편(하위 50%), 변동성 낮음",
        "filters": {"dividend_yield": [3, None], "debt_to_equity@sector": [None, 50], "volatility_3m": [None, 30]},
        "checklist": [
            "배당수익률이 높은 이유가 주가 급락이 아닌지 52주 고점 대비를 보세요.",
            "FCF 수익률이 배당수익률보다 낮으면 번 돈보다 많이 나눠주는 중일 수 있어요.",
            "유틸리티·리츠는 원래 부채가 많아서 섹터 안에서 비교하도록 해뒀어요.",
        ],
    },
    {
        "id": "funded-growth",
        "name": "적자지만 버틸 체력 있는 성장주",
        "note": "아직 적자(순이익률 0 미만)이고, 매출 25% 이상 성장, 현금 런웨이 24개월 이상, 주식 수 증가 10% 이하",
        "filters": {"net_margin": [None, 0], "revenue_growth": [25, None], "cash_runway": [24, None], "share_change_1y": [None, 10]},
        "checklist": [
            "PER·ROE는 적자라 의미가 없어요. PSR과 매출총이익률 변화를 보세요.",
            "런웨이는 지금 소진 속도 기준이에요. 투자를 늘리는 중이면 더 짧아질 수 있어요.",
            "변동성이 큰 종목들이라 하루에 ±10% 움직이는 일도 흔해요.",
        ],
    },
]


def metric_catalog() -> dict:
    return {
        "groups": [{"key": k, "label": v} for k, v in GROUPS],
        "metrics": [asdict(m) for m in METRICS],
        "sectors": [{"key": k, "label": v} for k, v in SECTORS.items()],
        "presets": PRESETS,
    }
