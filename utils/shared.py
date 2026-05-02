"""
공유 상태 모듈.

CookieController(_ctrl)는 Streamlit 재실행마다 새로 생성해야 하므로
주식앱.py(메인 스크립트)에서 매 rerun마다 shared.ctrl 을 갱신한다.
다른 모든 모듈은 이 객체를 통해 ctrl·QE를 접근한다.
"""


class _SharedState:
    # 쿠키 컨트롤러 — 주식앱.py에서 매 rerun마다 갱신
    ctrl = None

    # Quant Engine 플래그 + 클래스 (최초 1회 import)
    QE            = False
    MarketRegime  = None
    SignalEngine  = None
    Backtester    = None
    Recommender   = None
    AlertMonitor  = None


shared = _SharedState()

# ── Quant Engine 선택적 import (앱 시작 시 1회 실행) ──────────────────────────
try:
    from quant_engine import (MarketRegime, SignalEngine,
                               Backtester, Recommender, AlertMonitor)
    shared.QE           = True
    shared.MarketRegime = MarketRegime
    shared.SignalEngine = SignalEngine
    shared.Backtester   = Backtester
    shared.Recommender  = Recommender
    shared.AlertMonitor = AlertMonitor
except Exception:
    pass
