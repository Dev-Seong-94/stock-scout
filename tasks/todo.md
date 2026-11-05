# 작업 목록: 싸 보이는 후보 찾기 → 근거 확인

스펙: `docs/specs/value-evidence.md` · 계획: `tasks/plan.md`

공통 확인 명령:

```
cd backend && .venv/bin/python -m pytest -q
cd frontend && npm run typecheck && npm run build
```

## 작업 1: 조건 계산 함수 (S)

세 조건과 현금 기준 계산값을 네트워크 없는 순수 함수로 만들어요.

**완료 기준**
- [x] FCF 배수가 11.4, 16.4, 23.7이고, 시나리오 3개의 계산값이 나와요.
- [x] 조건마다 충족, 불충족, 확인 불가와 이유를 돌려줘요.
- [x] 적자, 금융, 부동산, FCF 음수, 짧은 상장 기간이 스펙대로 확인 불가가 돼요.

**확인:** `pytest -q`

**의존:** 없음

**파일:** `backend/app/cheapness.py`, `backend/tests/test_core.py`

## 작업 2: 스냅샷에 자기 과거 PER 저장 (M)

전체 빌드에서 5년 가격을 받아 자기 과거 PER과 새 지표 2개를 계산해요.

**완료 기준**
- [x] `pe_own_current`, `pe_own_median`, `pe_own_since`, `pe_vs_own`, `cash_value_gap`이 행에 들어가요.
- [x] `price_indicators` 결과가 2년과 5년 입력에서 같아요.
- [x] 새 지표 2개에 한국어 설명(뜻, 읽는 법, 함정)이 있어요.

**확인:** `pytest -q`, 파일을 쓰지 않는 `build_row` 호출로 AAPL과 IONQ 값 확인

**의존:** 작업 1

**파일:** `backend/app/snapshot.py`, `backend/app/metrics.py`, `backend/tests/test_core.py`

## 작업 3: 종목 페이지 "싼가?" (M)

API와 화면을 연결해 세 줄을 "한눈에 보기" 아래에 보여 줘요.

**완료 기준**
- [x] 세 줄에 숫자, 비교 대상, 기준 날짜, 표시("낮은 쪽" 등)가 있어요.
- [x] 확인할 수 없는 줄에 이유가 있어요. 새 열이 없는 스냅샷에서도 화면이 깨지지 않아요.
- [x] 계산값 옆에 가정과 "목표가가 아니에요" 문구가 있어요.

**확인:** `pytest -q`, 타입체크, 빌드, 브라우저에서 NVDA(흑자), IONQ(적자), JPM(금융), O(부동산) 확인

**의존:** 작업 1, 2

**파일:** `backend/app/routers/stocks.py`, `backend/app/screener.py`, `frontend/app/stocks/[symbol]/page.tsx`, `frontend/lib/types.ts`, `frontend/app/globals.css`

## 중간 점검 A
- [x] 테스트와 빌드 통과
- [ ] 스냅샷 재생성 여부를 사용자에게 확인
- [ ] 화면을 사용자와 검토

## 작업 4: 스크리너 개수와 정렬 (M)

결과에 개수를 넣고, 충족 개수 → 확인 가능 수 → 시가총액 순으로 정렬해요.

**완료 기준**
- [x] 결과 표에 `2 / 3` 형식의 열이 있어요.
- [x] 정렬에서 확인 가능한 조건이 적은 종목이 앞서지 않아요.
- [x] 같은 종목의 개수와 "싼가?" 세 줄이 일치해요.

**확인:** `pytest -q`, 타입체크, 브라우저에서 표와 종목 페이지 대조

**의존:** 작업 3

**파일:** `backend/app/screener.py`, `backend/tests/test_core.py`, `frontend/components/screener/ResultsTable.tsx`, `frontend/app/screener/page.tsx`, `frontend/lib/types.ts`

## 작업 5: 시작 버튼과 안내 (S)

시작 화면 맨 앞에 버튼을 두고, 결과 표 위에 안내와 충족 수를 보여 줘요.

**완료 기준**
- [x] 버튼 한 번으로 조건 충족 순서의 목록이 나와요.
- [x] "개수는 점수가 아니라 먼저 확인해 볼 순서예요" 안내와 "3개 모두 충족 N개"가 있어요.
- [x] URL에 상태가 남아, 종목 페이지에서 돌아와도 같은 목록이에요. 기존 예시 조합은 그대로예요.

**확인:** 타입체크, 빌드, 브라우저에서 버튼 → 종목 → 뒤로 가기 흐름 확인

**의존:** 작업 4

**파일:** `frontend/components/screener/StartHere.tsx`, `frontend/app/screener/page.tsx`, `frontend/app/globals.css`

## 중간 점검 B
- [x] 테스트와 빌드 통과
- [ ] 후보 찾기 → 근거 확인 흐름을 사용자와 검토
- [ ] 후보 수가 너무 많지 않은지 확인

## 작업 6: "왜 떨어졌나?" 수익률 비교 (M)

종목, 섹터 ETF, S&P 500의 4개 기간 수익률과 고정 규칙 문장을 보여 줘요.

**완료 기준**
- [x] 4개 기간 표가 나오고, 섹터 ETF 이름이 보여요.
- [x] 문장이 사실만 말해요. "이 기간에는 떨어지지 않았어요"도 처리해요.
- [x] 금지 표현 테스트를 통과해요. 표 일부가 없어도 화면이 유지돼요.

**확인:** `pytest -q`, 타입체크, 브라우저에서 IONQ와 오른 종목 확인

**의존:** 작업 3

**파일:** `backend/app/decline.py`, `backend/app/routers/stocks.py`, `backend/tests/test_core.py`, `frontend/app/stocks/[symbol]/page.tsx`, `frontend/lib/types.ts`

## 작업 7: "왜 떨어졌나?" 분기 실적 (M)

최근 분기를 전년 같은 분기와 비교해 매출, 영업이익률, 희석 주식 수를 보여 줘요.

**완료 기준**
- [x] 세 항목이 전년 같은 분기와 함께 나와요. 없는 항목은 "데이터 없음"이에요.
- [x] 실적이 나빠졌을 때만 사실 문장이 붙고, 판정 문장은 없어요.
- [x] 끝에 10-Q·8-K 공시로 가는 링크가 있고, 공시 탭이 열려요.

**확인:** `pytest -q`, 타입체크, 브라우저에서 2개 이상 종목 확인

**의존:** 작업 6

**파일:** `backend/app/services/market.py`, `backend/app/decline.py`, `backend/app/routers/stocks.py`, `backend/tests/test_core.py`, `frontend/app/stocks/[symbol]/page.tsx`

## 작업 8: 전체 재생성과 최종 확인 (S)

스냅샷을 백업하고 다시 만들어 스펙의 성공 기준을 전부 확인해요.

**완료 기준**
- [ ] 재생성 전후의 `no_prices`, `failed`를 비교해 큰 증가가 없어요.
- [ ] 스펙의 성공 기준 1~7을 모두 통과해요. 모바일(375px)도 포함해요.
- [ ] `CLAUDE.md`에 결정 사항과 지표 수가 반영돼요.

**확인:** `pytest -q`, 타입체크, 빌드, 브라우저 전체 흐름

**의존:** 작업 2~7

**파일:** `CLAUDE.md`, `backend/data/`(git 제외)

## 최종 점검
- [ ] 스펙 성공 기준 전체 통과
- [ ] 사용자 검토
