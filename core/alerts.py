"""
가격 알림 관리.
- _sync_alerts_to_github  : GitHub 저장
- _load_alerts_from_github: GitHub 로드
- _get_price_fdr          : FDR/yfinance 지연 가격 (5분 캐시)
- get_quick_price          : KIS 우선 → FDR fallback
- _check_price_alerts      : 30초마다 알림 체크
"""
import streamlit as st

from utils.github_sync import _gh_put_file, _gh_get_file, _GH_ALERTS_PATH
from utils.kis_api     import kis_get_token, kis_price, KIS_APP_KEY, KIS_APP_SECRET
from utils.kakao       import get_valid_kakao_token, send_kakao_message

import time

_KIS_REAL = "https://openapi.koreainvestment.com:9443"


# ── GitHub 동기화 ──────────────────────────────────────────────────────────────
def _sync_alerts_to_github(alerts: dict) -> bool:
    pat = st.secrets.get("github_pat", "")
    if not pat:
        return False
    return _gh_put_file(_GH_ALERTS_PATH, pat, {
        "alerts":     alerts,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    })


def _load_alerts_from_github() -> dict:
    pat = st.secrets.get("github_pat", "")
    if not pat:
        return {}
    data = _gh_get_file(_GH_ALERTS_PATH, pat)
    return data.get("alerts", {}) if data else {}


# ── 가격 조회 ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _get_price_fdr(code: str) -> dict | None:
    """FDR / yfinance 지연가격 조회 (5분 캐시). KIS fallback 전용."""
    from datetime import datetime, timedelta
    end   = datetime.today()
    start = end - timedelta(days=7)
    s, e  = start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')

    try:
        import FinanceDataReader as fdr
        df = fdr.DataReader(code, s, e)
        if df is not None and not df.empty and len(df) >= 2:
            df.columns = [c.capitalize() for c in df.columns]
            last = float(df['Close'].iloc[-1])
            prev = float(df['Close'].iloc[-2])
            return {'price': last, 'chg_pct': (last / prev - 1) * 100, 'source': 'FDR'}
    except Exception:
        pass

    try:
        import yfinance as yf
        for suffix in ['.KS', '.KQ']:
            hist = yf.Ticker(f'{code}{suffix}').history(period='5d')
            if hist is not None and not hist.empty and len(hist) >= 2:
                last = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2])
                return {'price': last, 'chg_pct': (last / prev - 1) * 100, 'source': 'YF'}
    except Exception:
        pass

    return None


def get_quick_price(code: str) -> dict | None:
    """현재가·등락률 반환 — KIS 실시간(30초) 우선, 실패 시 FDR/yfinance(5분) fallback."""
    token = kis_get_token()
    if token:
        base = st.session_state.get('_kis_base_url', _KIS_REAL)
        kp   = kis_price(code, token, base)
        if kp:
            return kp
    return _get_price_fdr(code)


# ── 알림 체크 ─────────────────────────────────────────────────────────────────
def _check_price_alerts():
    """관심종목 알림 가격 도달 여부 체크 — 30초마다 호출."""
    alerts = st.session_state.get('price_alerts', {})
    if not alerts:
        return
    tok = get_valid_kakao_token()
    for code, cfg in alerts.items():
        target = cfg.get('target')
        stop   = cfg.get('stop')
        if not target and not stop:
            continue
        pinfo = get_quick_price(code)
        if not pinfo:
            continue
        price     = pinfo.get('price', 0)
        name      = cfg.get('name', code)
        triggered = cfg.get('last_triggered', '')

        if target and price >= target and triggered != f'target_{target}':
            msg = (f"🔔 [{name}] 목표가 도달!\n"
                   f"현재가 {price:,}원 ≥ 목표가 {int(target):,}원")
            st.toast(msg, icon="🎯")
            if tok:
                try:
                    send_kakao_message(tok, msg)
                except Exception:
                    pass
            alerts[code]['last_triggered'] = f'target_{target}'

        elif stop and price <= stop and triggered != f'stop_{stop}':
            msg = (f"🚨 [{name}] 손절가 도달!\n"
                   f"현재가 {price:,}원 ≤ 손절가 {int(stop):,}원")
            st.toast(msg, icon="🚨")
            if tok:
                try:
                    send_kakao_message(tok, msg)
                except Exception:
                    pass
            alerts[code]['last_triggered'] = f'stop_{stop}'

        elif target and stop and stop < price < target:
            alerts[code]['last_triggered'] = ''

    st.session_state['price_alerts'] = alerts
