# 주식 분석기 — 파일 구조 설계서

## 분리 현황 (v4.0 완료)
- 분리 전: `주식앱_legacy.py` **3,573줄** (단일 파일 → 백업)
- 분리 후: `주식앱.py` **~120줄** (엔트리포인트) + 15개 모듈 파일

## 분리 후 구조

```
stock-analyzer/
├── 주식앱.py                  ← 엔트리포인트 (main + 초기화만, ~120줄)
│
├── utils/                     ← 외부 API · 공통 유틸
│   ├── __init__.py
│   ├── shared.py              ← 공유 상태 (CookieController, QuantEngine)
│   ├── kis_api.py             ← KIS Developers API (토큰·현재가)
│   ├── kakao.py               ← 카카오 인증·전송·OAuth
│   ├── github_sync.py         ← GitHub 파일 R/W (watchlist·alerts 동기화)
│   └── stock_data.py          ← KRX 종목 로드, 검색, OHLCV·뉴스·수급 수집
│
├── core/                      ← 비즈니스 로직
│   ├── __init__.py
│   ├── watchlist.py           ← 관심종목 상태관리 (GitHub+쿠키 persistence)
│   ├── alerts.py              ← 가격 알림 체크 (30초 폴링)
│   └── indicators.py          ← 기술지표·매매구간·신호 계산
│
└── ui/                        ← Streamlit UI 렌더링
    ├── __init__.py
    ├── styles.py              ← page_config + 전체 CSS 주입
    ├── sidebar.py             ← 사이드바 전체 (관심종목 미니판·알림·카카오·KIS)
    ├── chart.py               ← 캔들차트·수급·실적·백테스트 렌더
    ├── ai_chat.py             ← AI 투자상담 채팅 + 뉴스탭
    ├── analysis.py            ← 메인 분석 결과 렌더 (render_analysis)
    ├── portfolio.py           ← 포트폴리오 탭
    └── screener.py            ← 스크리너 탭 (SCREEN_UNIVERSE 포함)
```

---

## 파일별 상세

| 파일 | 주요 함수/클래스 | 줄수 |
|------|----------------|------|
| `utils/shared.py` | `shared` 객체 (ctrl, QE, MarketRegime...) | ~25줄 |
| `utils/kis_api.py` | `kis_available`, `kis_get_token`, `kis_price`, `_safe_float` | ~130줄 |
| `utils/kakao.py` | `init_kakao`, `handle_kakao_callback`, `get_valid_kakao_token`, `send_kakao_message`, `format_kakao_message`, OAuth helpers | ~310줄 |
| `utils/github_sync.py` | `_gh_get_sha`, `_gh_put_file`, `_gh_get_file` | ~60줄 |
| `utils/stock_data.py` | `KNOWN_NAMES`, `load_krx_stocks`, `search_stocks`, `_naver_search`, `get_stock_data`, `get_stock_info`, `get_stock_news`, `get_investor_flow`, `get_quarterly_earnings`, `get_kospi_regime` | ~430줄 |
| `core/watchlist.py` | `init_watchlist`, `_save_watchlist`, `add/remove/in_watchlist`, `_sync/load_watchlist_to/from_github` | ~170줄 |
| `core/alerts.py` | `_check_price_alerts`, `_sync/load_alerts_from_github`, `_get_price_fdr`, `get_quick_price` | ~160줄 |
| `core/indicators.py` | `calc_indicators`, `calc_zones`, `calc_signal`, `build_signal_detail`, `find_sr`, `price_position` | ~280줄 |
| `ui/styles.py` | `inject_styles()` — CSS + page_config | ~140줄 |
| `ui/sidebar.py` | `render_sidebar()` | ~370줄 |
| `ui/chart.py` | `build_chart`, `render_investor_flow`, `render_quarterly_earnings`, `_render_backtest`, `_cached_backtest`, `_render_top5`, `_render_regime_badge` | ~360줄 |
| `ui/ai_chat.py` | `render_ai_chat`, `ask_ai_advisor`, `render_news_tab`, `_clipboard_btn`, `_kakao_send_btn`, `_scenario_card` | ~290줄 |
| `ui/analysis.py` | `render_analysis()` | ~340줄 |
| `ui/portfolio.py` | `init_portfolio`, `save_portfolio`, `render_portfolio_tab` | ~130줄 |
| `ui/screener.py` | `SCREEN_UNIVERSE`, `_TIER_*`, `_scan_one`, `run_screen`, `render_screener_tab` | ~470줄 |
| `주식앱.py` | `main()` + import + 초기화 | ~120줄 |

**총 예상: ~3,300줄 (15개 파일 분산)**

---

## 의존성 그래프

```
주식앱.py
  ├── utils/shared.py          ← 최초 초기화
  ├── utils/stock_data.py
  ├── core/watchlist.py
  ├── core/alerts.py
  ├── utils/kakao.py
  └── ui/ (모든 렌더 함수)
        ├── ui/styles.py
        ├── ui/sidebar.py      → core/watchlist, core/alerts, utils/kakao, utils/kis_api
        ├── ui/analysis.py     → core/indicators, ui/chart, ui/ai_chat
        ├── ui/chart.py        → core/indicators, utils/stock_data
        ├── ui/ai_chat.py      → utils/kakao
        ├── ui/portfolio.py    → utils/stock_data, core/watchlist
        └── ui/screener.py     → core/indicators, utils/stock_data
```

**순환 의존성 없음** ✅

---

## 공유 상태 처리 (`_ctrl` 문제)

`CookieController()`는 Streamlit 재실행마다 새로 생성해야 함.  
메인 스크립트(`주식앱.py`)는 재실행마다 전체 실행되므로 여기서 생성 후 `shared.ctrl`에 저장.  
다른 모듈은 `from utils.shared import shared` 후 `shared.ctrl`로 접근.

```python
# 주식앱.py (매 rerun마다 실행)
from utils.shared import shared
try:
    from streamlit_cookies_controller import CookieController
    shared.ctrl = CookieController()
except Exception:
    shared.ctrl = None
```

---

## 실행 방법 (변경 없음)
```bash
streamlit run 주식앱.py
```
