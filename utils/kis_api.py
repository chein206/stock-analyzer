"""
KIS Developers API 연동.
- 액세스 토큰 발급 (24시간 캐시)
- 국내주식 현재가 조회 (30초 캐시)
"""
import streamlit as st
import requests
import time

# ── 설정 ──────────────────────────────────────────────────────────────────────
KIS_APP_KEY    = st.secrets.get("kis_app_key",    "")
KIS_APP_SECRET = st.secrets.get("kis_app_secret", "")
_KIS_REAL = "https://openapi.koreainvestment.com:9443"
_KIS_MOCK = "https://openapivts.koreainvestment.com:29443"
KIS_BASE  = _KIS_MOCK if st.secrets.get("kis_is_mock", False) else _KIS_REAL


def kis_available() -> bool:
    return bool(KIS_APP_KEY and KIS_APP_SECRET)


def kis_get_token() -> str | None:
    """KIS OAuth2 액세스 토큰 (세션당 24시간 캐시). 실전→모의 순 자동 fallback."""
    if not kis_available():
        return None
    cache = st.session_state.get('_kis_token_cache', {})
    if cache.get('expires_at', 0) > time.time() + 60:
        return cache.get('token')

    prev_base  = st.session_state.get('_kis_base_url')
    candidates = [prev_base] if prev_base else []
    for url in [_KIS_REAL, _KIS_MOCK]:
        if url not in candidates:
            candidates.append(url)

    last_err = ""
    for base_url in candidates:
        try:
            r = requests.post(
                f"{base_url}/oauth2/tokenP",
                json={
                    "grant_type": "client_credentials",
                    "appkey":     KIS_APP_KEY,
                    "appsecret":  KIS_APP_SECRET,
                },
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            data  = r.json()
            token = data.get('access_token')
            if r.status_code == 200 and token:
                expires_in = int(data.get('expires_in', 86400))
                st.session_state['_kis_base_url']    = base_url
                st.session_state['_kis_token_cache'] = {
                    'token':      token,
                    'expires_at': time.time() + expires_in,
                }
                st.session_state.pop('_kis_last_error', None)
                return token
            else:
                msg      = data.get('msg1') or data.get('message') or r.text[:120]
                last_err = f"[{base_url.split(':')[1][2:]}] HTTP {r.status_code} — {msg}"
        except Exception as e:
            last_err = f"[연결 오류] {str(e)[:100]}"

    st.session_state['_kis_last_error']  = last_err
    st.session_state['_kis_token_cache'] = {
        'token': None, 'expires_at': time.time() + 60
    }
    return None


def _safe_float(val, default=None):
    """문자열/숫자를 float로 안전 변환. 0이면 default 반환."""
    try:
        v = float(str(val).replace(',', '').strip())
        return v if v != 0.0 else default
    except Exception:
        return default


@st.cache_data(ttl=30)
def kis_price(code: str, _token: str, _base_url: str = _KIS_REAL) -> dict | None:
    """KIS 국내주식 현재가 조회 (30초 캐시)."""
    try:
        r = requests.get(
            f"{_base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers={
                "Authorization": f"Bearer {_token}",
                "appkey":        KIS_APP_KEY,
                "appsecret":     KIS_APP_SECRET,
                "tr_id":         "FHKST01010100",
                "Content-Type":  "application/json; charset=utf-8",
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD":         code,
            },
            timeout=10,
        )
        if r.status_code != 200:
            return None
        out = r.json().get('output', {})
        if not out:
            return None
        price = _safe_float(out.get('stck_prpr'))
        if not price:
            return None
        chg_pct = _safe_float(out.get('prdy_ctrt'), 0.0)
        w52_h   = (_safe_float(out.get('w52_hgpr'))
                   or _safe_float(out.get('stck_dryy_hgpr')))
        w52_l   = (_safe_float(out.get('w52_lwpr'))
                   or _safe_float(out.get('stck_dryy_lwpr')))
        mktcap_raw = _safe_float(out.get('hts_avls'))
        return {
            'price':      price,
            'chg_pct':    chg_pct,
            'per':        _safe_float(out.get('per')),
            'pbr':        _safe_float(out.get('pbr')),
            'w52_high':   w52_h,
            'w52_low':    w52_l,
            'market_cap': mktcap_raw * 1e8 if mktcap_raw else None,
            'source':     'KIS',
        }
    except Exception:
        return None
