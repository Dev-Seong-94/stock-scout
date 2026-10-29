# Stock Scout

시장 환경(거시)을 보면서 지표 필터로 종목을 좁혀 가는 개인 리서치 도구예요.
투자 추천은 하지 않아요. 숫자와 설명만 보여주고, 판단은 직접 해요.

| 화면 | 내용 |
| --- | --- |
| 대시보드 | 시장 상태 요약, VIX · Fear & Greed · 미국채 10년 · 장단기 금리차 · 달러 인덱스 · WTI · 하이일드 스프레드 · S&P 500 (각 지표가 지난 5년 범위에서 어디쯤인지 표시), 섹터 흐름, 이번 주 일정, 헤드라인 |
| 스크리너 | 35개 지표 필터(밸류에이션 · 수익성 · 성장성 · 재무 건전성 · 가격·기술적 · 규모·수급)와 섹터 필터, 지표마다 설명과 현재 분포, 예시 프리셋과 내 프리셋 저장, CSV 저장 |
| 종목 상세 | 주가 차트(50·200일선), 지표 카드(섹터 중앙값 비교), 수급(공매도 · 내부자 거래 · 기관 보유), 뉴스, SEC 공시 |
| 거시·정세 | 금리 · 물가 · 고용 · 신용 추이, 30일 이벤트 캘린더(FOMC · 주요 지표 · 관심종목 실적), 지정학 이슈 |
| 관심종목 | 저장, 관심 사유와 메모, 추가 이후 수익률, JSON 내보내기·가져오기 |

## 구조

```
stock-scout/
├── backend/            FastAPI (Python)
│   ├── app/
│   │   ├── metrics.py      스크리너 지표 정의와 한국어 설명 (지표 추가는 여기서)
│   │   ├── indicators.py   RSI, 이동평균, 수익률, 변동성 계산
│   │   ├── snapshot.py     하루 한 번 전 종목 지표를 계산해 data/snapshot.parquet에 저장
│   │   ├── screener.py     스냅샷 필터링
│   │   ├── regime.py       대시보드의 시장 상태 요약 규칙
│   │   ├── services/       FRED, yfinance, SEC EDGAR, GDELT·RSS, CNN Fear & Greed, 캘린더
│   │   └── routers/        API 엔드포인트
│   ├── scripts/build_snapshot.py
│   ├── data/fomc.json      FOMC 일정 (연준 발표 기준, 매년 갱신)
│   └── tests/
└── frontend/           Next.js (App Router)
    ├── app/            화면 5개
    ├── components/     차트, 설명 툴팁 등
    └── lib/            API 호출, 포맷, localStorage(관심종목·프리셋)
```

데이터베이스는 없어요. 개인 데이터(관심종목, 메모, 프리셋)는 브라우저 localStorage에만 있고,
서버는 공개 시장 데이터를 메모리에 잠깐 캐시하고 스크리너용 스냅샷 파일만 만들어요.

## 시작하기

### 1. API 키

```bash
cp .env.example backend/.env
```

`backend/.env`에 채워 주세요. `.env`는 `.gitignore`에 들어 있어서 커밋되지 않아요.

| 변수 | 필수 | 받는 곳 |
| --- | --- | --- |
| `FRED_API_KEY` | 예 | https://fred.stlouisfed.org/docs/api/api_key.html (무료) |
| `SEC_USER_AGENT` | 예 | 키가 아니라 `"이름 이메일"` 형식 문자열. SEC가 요구해요 |
| `FINNHUB_API_KEY` | 아니요 | https://finnhub.io/register (무료). 실적 발표 일정용 |

### 2. 백엔드

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

pytest -q                                   # 계산 로직 테스트 (네트워크 불필요)
python -m scripts.build_snapshot --limit 30 # 먼저 30종목으로 빠르게 확인
python -m scripts.build_snapshot            # 전체 (S&P 1500 + 나스닥 100 + 추가 종목, 45–60분)

uvicorn app.main:app --reload --port 8000
```

http://localhost:8000/docs 에서 API를 직접 눌러볼 수 있어요. `/api/health`에서 키 설정 여부를 확인하세요.

스냅샷은 하루 한 번 다시 만들면 돼요. 스크리너 화면의 버튼이나 `POST /api/screener/refresh`로도 만들 수 있어요.
**스크리너 대상 종목**은 S&P 500 · S&P 400(중형주) · S&P 600(소형주) · 나스닥 100(약 1,500개)이에요.

- `backend/data/universe_extra.txt`: 여기에 적은 티커가 기본 목록에 **추가**돼요. S&P 지수는 흑자 기업만 편입하기 때문에 IonQ 같은 적자 성장주는 여기에 적어 주세요.
- `backend/data/universe.txt`: 이 파일이 있으면 기본 목록 **대신** 여기 적힌 종목만 써요.

중간에 멈춰도 25종목마다 저장되니 다시 실행하면 이어서 진행해요.

### 3. 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

http://localhost:3000 을 열면 돼요. API 주소가 다르면 `frontend/.env.local`에 `NEXT_PUBLIC_API_BASE`를 적어 주세요.

## 데이터 소스

| 용도 | 소스 | 비고 |
| --- | --- | --- |
| 금리·물가·고용·신용, 지표 발표일 | FRED | 공식 API, 무료 키 |
| 주가, 재무 요약, 내부자 거래, 기관 보유, 공매도 | Yahoo Finance (yfinance) | 비공식. 개인 용도로만 쓰세요. 가끔 요청 제한이 걸려요 |
| 공시 | SEC EDGAR | 공식, 키 없음. User-Agent 필수, 초당 10회 이하 |
| 지정학·종목 뉴스 | GDELT DOC API | 공식, 키 없음 |
| 시장 헤드라인 | RSS (연준, CNBC, MarketWatch) | `services/news.py`의 `RSS_FEEDS`에서 바꿀 수 있어요 |
| Fear & Greed | CNN 페이지 내부 JSON | 비공식. 막히면 화면에 "불러올 수 없음"으로 나와요 |
| 실적 발표일 | Finnhub | 선택 |
| FOMC 일정 | 연준 웹사이트 → `data/fomc.json` | 연 1회 직접 갱신 |

### 더 붙여볼 만한 소스

- **SEC companyfacts API**: XBRL 재무제표 원본. 10년치 성장률이나 분기 추세를 직접 계산할 때
- **BLS API**: 고용·물가 세부 항목 (FRED보다 세분화)
- **EIA API**: 원유·천연가스 재고. 에너지 섹터를 볼 때
- **CFTC COT 보고서**: 선물 시장 투기 포지션
- **Treasury Fiscal Data**: 국채 발행, 재정 적자

## 한계

- 수급: 미국은 한국처럼 외국인·기관 일별 순매수가 공개되지 않아요. 내부자 거래, 13F 기관 보유(분기), 공매도 잔고(2주마다)로 대신해요.
- 지표 값은 Yahoo가 제공하는 TTM·최근 분기 기준이라 회사 IR 자료와 조금 다를 수 있어요.
- 시장 상태 요약은 고정된 규칙으로 만든 설명이고 예측이 아니에요.
