"""
주식 분석기 v3.0
- 종목명/코드 검색
- 관심종목 저장 (쿠키 기반, 브라우저 재시작 후에도 유지)
- 사이드바 미니 신호판 (현재가 + 등락 실시간 표시)
- 기관/외국인 수급 분석
- 분기 실적 추이
- 카카오톡 분석 결과 전송
실행: streamlit run 주식앱.py
"""
import streamlit as st
import pandas as pd
import numpy as np
import json
import time
import requests
import warnings
warnings.filterwarnings('ignore')

# ── Quant Engine (선택적 import — 없어도 앱 동작) ─────────────────────────────
try:
    from quant_engine import (MarketRegime, SignalEngine,
                               Backtester, Recommender, AlertMonitor)
    _QE = True
except Exception:
    _QE = False

st.set_page_config(
    page_title="📈 주식 분석기",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* ── CSS 변수: 라이트/다크 자동 전환 ─────────────────────────────────────── */
:root {
    --card-bg:      #F8F8F8;
    --card-bg2:     #F4F4F4;
    --card-bg3:     #F6F6F6;
    --card-border:  #E8E8E8;
    --text-muted:   #888888;
    --text-sub:     #999999;
    --text-label:   #666666;
    --divider:      #DDDDDD;
    --summary-bg:   #F8F8F8;
}
[data-theme="dark"] {
    --card-bg:      #262730;
    --card-bg2:     #1E1E2E;
    --card-bg3:     #2D2D3D;
    --card-border:  #3A3A4A;
    --text-muted:   #AAAAAA;
    --text-sub:     #888888;
    --text-label:   #BBBBBB;
    --divider:      #444455;
    --summary-bg:   #262730;
}

html, body, [class*="css"] {
    font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}

/* ── 신호 박스 ────────────────────────────────────────────────────────────── */
.signal-box {
    border-radius: 16px; padding: 22px 16px;
    text-align: center; margin: 8px 0 12px;
}
.signal-emoji  { font-size: 44px; line-height: 1.2; }
.signal-label  { font-size: 24px; font-weight: 800; margin: 6px 0 3px; }
.signal-score  { font-size: 13px; opacity: 0.75; }
.signal-desc   { font-size: 14px; margin-top: 8px; word-break: keep-all; line-height: 1.7; }

/* ── 가격 바 ──────────────────────────────────────────────────────────────── */
.price-bar {
    border-radius: 10px; padding: 11px 14px;
    margin: 6px 0 14px; font-size: 15px; font-weight: 600;
}

/* ── 분석 근거 ────────────────────────────────────────────────────────────── */
.reason-box {
    border-left: 4px solid var(--divider);
    border-radius: 0 8px 8px 0;
    padding: 7px 12px; margin: 4px 0;
    font-size: 14px;
    background: var(--card-bg3);
    color: inherit;
    word-break: keep-all; line-height: 1.6;
}

/* ── 매매 가격 카드 ───────────────────────────────────────────────────────── */
.zone-card {
    background: var(--card-bg); border-radius: 12px;
    padding: 14px 12px; text-align: center;
    word-break: keep-all;
}
.zone-label { font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
.zone-value { font-size: 19px; font-weight: 800; }
.zone-sub   { font-size: 12px; color: var(--text-sub);   margin-top: 2px; }

/* ── 수급 카드 ────────────────────────────────────────────────────────────── */
.flow-card {
    border-radius: 10px; padding: 12px;
    text-align: center; margin-bottom: 4px;
    background: var(--card-bg);
}

/* ── 사이드바 미니 카드 ───────────────────────────────────────────────────── */
.mini-card {
    background: var(--card-bg2); border-radius: 10px;
    padding: 8px 10px; margin: 4px 0 2px;
}

/* ── 공통 카드 (포트폴리오·스크리너) ─────────────────────────────────────── */
.app-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 14px; padding: 16px 20px; margin-bottom: 10px;
}
.app-label { font-size: 12px; color: var(--text-muted); }
.app-sub   { font-size: 12px; color: var(--text-sub); }
.app-muted { color: var(--text-muted); font-size: 13px; }

@media (max-width: 640px) {
    .signal-label { font-size: 20px; }
    .signal-emoji { font-size: 36px; }
    .zone-value   { font-size: 15px; }
}
</style>
""", unsafe_allow_html=True)

# ── 쿠키 컨트롤러 (스크립트 실행당 딱 1개) ────────────────────────────────────
try:
    from streamlit_cookies_controller import CookieController
    _ctrl = CookieController()          # 매 rerun 마다 1번만 생성 → 충돌 없음
except Exception:
    _ctrl = None


# ── KIS Developers API 설정 ──────────────────────────────────────────────────
KIS_APP_KEY    = st.secrets.get("kis_app_key",    "")
KIS_APP_SECRET = st.secrets.get("kis_app_secret", "")
# 실전투자 / 모의투자 URL (kis_is_mock=true 로 모의투자 전환 가능)
_KIS_REAL = "https://openapi.koreainvestment.com:9443"
_KIS_MOCK = "https://openapivts.koreainvestment.com:29443"
KIS_BASE   = _KIS_MOCK if st.secrets.get("kis_is_mock", False) else _KIS_REAL


def kis_available() -> bool:
    """KIS API 키가 Secrets에 설정돼 있으면 True"""
    return bool(KIS_APP_KEY and KIS_APP_SECRET)


def kis_get_token() -> str | None:
    """KIS OAuth2 액세스 토큰 발급 (세션당 24시간 캐시).
    실전투자 URL 우선 시도 → 실패 시 모의투자 URL 자동 재시도.
    마지막 에러는 _kis_last_error 에 저장해 사이드바에 표시.
    """
    if not kis_available():
        return None
    cache = st.session_state.get('_kis_token_cache', {})
    if cache.get('expires_at', 0) > time.time() + 60:
        return cache.get('token')   # 캐시 유효

    # 실전 → 모의 순서로 시도 (이미 성공한 URL이 있으면 그것 먼저)
    prev_base = st.session_state.get('_kis_base_url')
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
            data = r.json()
            token = data.get('access_token')
            if r.status_code == 200 and token:
                expires_in = int(data.get('expires_in', 86400))
                st.session_state['_kis_base_url']    = base_url   # 성공한 URL 저장
                st.session_state['_kis_token_cache'] = {
                    'token':      token,
                    'expires_at': time.time() + expires_in,
                }
                st.session_state.pop('_kis_last_error', None)
                return token
            else:
                msg = data.get('msg1') or data.get('message') or r.text[:120]
                last_err = f"[{base_url.split(':')[1][2:]}] HTTP {r.status_code} — {msg}"
        except Exception as e:
            last_err = f"[연결 오류] {str(e)[:100]}"

    # 모든 URL 실패
    st.session_state['_kis_last_error']  = last_err
    st.session_state['_kis_token_cache'] = {
        'token': None, 'expires_at': time.time() + 60   # 60초 후 재시도
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
    """KIS 국내주식 현재가 조회 (30초 캐시).
    _token, _base_url 모두 캐시 키에서 제외(underscore prefix).
    반환: price, chg_pct, per, pbr, w52_high, w52_low, market_cap, source
    """
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
        chg_pct = _safe_float(out.get('prdy_ctrt'), 0.0)   # 전일 대비율 (%)
        # 52주 고저 — 필드명 두 가지 모두 시도
        w52_h = (_safe_float(out.get('w52_hgpr'))
                 or _safe_float(out.get('stck_dryy_hgpr')))
        w52_l = (_safe_float(out.get('w52_lwpr'))
                 or _safe_float(out.get('stck_dryy_lwpr')))
        # 시가총액: hts_avls 는 억원 단위
        mktcap_raw = _safe_float(out.get('hts_avls'))
        return {
            'price':      price,
            'chg_pct':    chg_pct,
            'per':        _safe_float(out.get('per')),
            'pbr':        _safe_float(out.get('pbr')),
            'w52_high':   w52_h,
            'w52_low':    w52_l,
            'market_cap': mktcap_raw * 1e8 if mktcap_raw else None,  # 억원 → 원
            'source':     'KIS',
        }
    except Exception:
        return None


# ── 카카오 설정 ───────────────────────────────────────────────────────────────
KAKAO_REST_KEY  = st.secrets.get("kakao_rest_key", "")
REDIRECT_URI    = "https://stock-analyzer-egqwnt22pkfgzdgxuapppyw.streamlit.app"

# Secrets에 액세스 토큰 직접 저장 시 OAuth 없이 바로 사용 (가장 안정적)
_KAKAO_STATIC_TOKEN = st.secrets.get("kakao_access_token", "")


def kakao_auth_url() -> str:
    import urllib.parse
    return (
        "https://kauth.kakao.com/oauth/authorize"
        f"?client_id={KAKAO_REST_KEY}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        "&response_type=code"
        "&scope=talk_message"
    )


def _exchange_kakao_code(code: str) -> tuple[int, dict]:
    try:
        r = requests.post(
            "https://kauth.kakao.com/oauth/token",
            data={
                "grant_type":   "authorization_code",
                "client_id":    KAKAO_REST_KEY,
                "redirect_uri": REDIRECT_URI,
                "code":         code,
            },
            timeout=10,
        )
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": "network", "error_description": str(e)}


def _refresh_kakao_token(refresh_token: str) -> tuple[int, dict]:
    try:
        r = requests.post(
            "https://kauth.kakao.com/oauth/token",
            data={
                "grant_type":    "refresh_token",
                "client_id":     KAKAO_REST_KEY,
                "refresh_token": refresh_token,
            },
            timeout=10,
        )
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": "network", "error_description": str(e)}


def _save_kakao_token(token_data: dict):
    """카카오 토큰 쿠키에 저장 (30일)"""
    if _ctrl is not None:
        try:
            _ctrl.set(
                'kakao_token',
                json.dumps(token_data, ensure_ascii=False),
                max_age=60 * 60 * 24 * 30,
            )
        except Exception:
            pass


def _clear_kakao_token():
    """카카오 토큰 초기화"""
    st.session_state['kakao_token'] = None
    st.session_state.pop('_kakao_used_code', None)
    if _ctrl is not None:
        try:
            _ctrl.remove('kakao_token')
        except Exception:
            pass


def init_kakao():
    """앱 시작 시 카카오 토큰 초기화.
    우선순위: ① Secrets 직접 토큰 ② 쿠키 저장 토큰 ③ 없음
    """
    if 'kakao_token' not in st.session_state:
        st.session_state['kakao_token'] = None

    # 이미 토큰 있으면 스킵
    if st.session_state['kakao_token']:
        return

    # ① Secrets에 액세스 토큰이 직접 있으면 그걸 사용
    if _KAKAO_STATIC_TOKEN:
        st.session_state['kakao_token'] = {
            'access_token':  _KAKAO_STATIC_TOKEN,
            'refresh_token': st.secrets.get("kakao_refresh_token", ""),
            'expires_at':    int(time.time()) + 86400 * 30,  # 정적 토큰은 장기로 처리
            'static':        True,
        }
        return

    # ② 쿠키에서 로드 (한 세션에 한 번만)
    if st.session_state.get('_kakao_cookie_loaded'):
        return
    st.session_state['_kakao_cookie_loaded'] = True
    if _ctrl is not None:
        try:
            raw = _ctrl.get('kakao_token')
            if raw:
                token_data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(token_data, dict) and token_data.get('access_token'):
                    st.session_state['kakao_token'] = token_data
        except Exception:
            pass


def handle_kakao_callback():
    """URL ?code= 파라미터 처리.

    버그 수정 포인트:
    - st.query_params.clear() 가 rerun을 트리거하므로
      성공/실패 메시지를 session_state 에 저장 → 다음 render에서 표시
    - _kakao_used_code 로 같은 code 중복 처리 방지 (Kakao code 1회용)
    - error 파라미터(사용자 로그인 거부 등)도 처리
    """
    params = st.query_params.to_dict()

    # 카카오가 error 파라미터를 보낸 경우 (로그인 거부 등)
    if 'error' in params:
        st.query_params.clear()
        desc = params.get('error_description', params['error'])
        st.session_state['_kakao_notify'] = ('error', f"카카오 로그인 거부: {desc}")
        return

    code = params.get('code')
    if not code:
        return

    # 이미 처리한 code 면 스킵 (rerun 루프 방지)
    if st.session_state.get('_kakao_used_code') == code:
        st.query_params.clear()
        return
    st.session_state['_kakao_used_code'] = code

    # 토큰 교환
    status, result = _exchange_kakao_code(code)

    # query_params 클리어 → rerun 트리거 (이후 session_state 메시지가 표시됨)
    st.query_params.clear()

    if status == 200 and result.get('access_token'):
        token_data = {
            'access_token':  result['access_token'],
            'refresh_token': result.get('refresh_token', ''),
            'expires_at':    int(time.time()) + result.get('expires_in', 21600),
            'static':        False,
        }
        st.session_state['kakao_token']          = token_data
        st.session_state['_kakao_cookie_loaded'] = True
        _save_kakao_token(token_data)
        st.session_state['_kakao_notify'] = ('success', '✅ 카카오톡 연결 완료!')
    else:
        err  = result.get('error_description') or result.get('msg') or result.get('error') or '알 수 없는 오류'
        debug = f"HTTP {status} | {json.dumps(result, ensure_ascii=False)[:200]}"
        st.session_state['_kakao_notify'] = ('error', f"토큰 교환 실패: {err}")
        st.session_state['_kakao_debug']  = debug


def _apply_manual_kakao_token(raw_token: str) -> tuple[bool, str]:
    """수동 입력 액세스 토큰 저장 (검증은 테스트 전송으로 확인).
    Returns: (성공여부, 오류메시지)
    """
    raw_token = raw_token.strip()
    if not raw_token:
        return False, "토큰을 입력해주세요."
    if len(raw_token) < 10:
        return False, "토큰이 너무 짧아요. 액세스 토큰을 다시 확인해주세요."

    token_data = {
        'access_token':  raw_token,
        'refresh_token': '',
        'expires_at':    int(time.time()) + 86400 * 30,  # 30일 (실제 만료는 전송 시 확인)
        'static':        True,
    }
    st.session_state['kakao_token']          = token_data
    st.session_state['_kakao_cookie_loaded'] = True
    _save_kakao_token(token_data)
    return True, ""


def _apply_kakao_auth_code(auth_code: str) -> tuple[bool, str]:
    """카카오 auth code → 액세스 토큰 교환 (수동 코드 입력용).
    Returns: (성공여부, 오류메시지)
    """
    auth_code = auth_code.strip()
    if not auth_code:
        return False, "코드를 입력해주세요."

    # 이미 사용한 코드 방지
    if st.session_state.get('_kakao_used_code') == auth_code:
        return False, "이미 사용한 코드입니다. 새로 발급받아주세요."
    st.session_state['_kakao_used_code'] = auth_code

    status, result = _exchange_kakao_code(auth_code)
    if status == 200 and result.get('access_token'):
        token_data = {
            'access_token':  result['access_token'],
            'refresh_token': result.get('refresh_token', ''),
            'expires_at':    int(time.time()) + result.get('expires_in', 21600),
            'static':        False,
        }
        st.session_state['kakao_token']          = token_data
        st.session_state['_kakao_cookie_loaded'] = True
        _save_kakao_token(token_data)
        return True, ""
    else:
        err = (result.get('error_description')
               or result.get('msg')
               or result.get('error')
               or f"HTTP {status}")
        debug = f"HTTP {status} | {json.dumps(result, ensure_ascii=False)[:300]}"
        st.session_state['_kakao_debug'] = debug
        return False, f"코드 교환 실패: {err}"


def get_valid_kakao_token() -> str | None:
    """유효한 액세스 토큰 반환 (만료 시 자동 갱신)"""
    token_data = st.session_state.get('kakao_token')
    if not token_data:
        return None

    # 정적 토큰(Secrets/수동 입력)은 갱신 로직 건너뜀
    if token_data.get('static'):
        return token_data.get('access_token')

    # 만료 5분 전이면 refresh
    if time.time() > token_data.get('expires_at', 0) - 300:
        refresh = token_data.get('refresh_token', '')
        if not refresh:
            _clear_kakao_token()
            return None

        status, result = _refresh_kakao_token(refresh)
        if status == 200 and result.get('access_token'):
            token_data['access_token'] = result['access_token']
            token_data['expires_at']   = int(time.time()) + result.get('expires_in', 21600)
            if result.get('refresh_token'):
                token_data['refresh_token'] = result['refresh_token']
            st.session_state['kakao_token'] = token_data
            _save_kakao_token(token_data)
        else:
            _clear_kakao_token()
            return None

    return token_data.get('access_token')

def send_kakao_message(access_token: str, text: str) -> tuple[bool, dict]:
    """카카오 나에게 보내기 — result_code 0 이어야 실제 전송 성공"""
    template = {
        "object_type": "text",
        "text":        text[:2000],
        "link": {
            "web_url":        REDIRECT_URI,
            "mobile_web_url": REDIRECT_URI,
        },
        "button_title": "앱에서 자세히 보기",
    }
    r = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=10,
    )
    try:
        body = r.json()
    except Exception:
        body = {"msg": r.text, "code": r.status_code}
    # HTTP 200 + result_code 0 = 진짜 성공
    success = (r.status_code == 200) and (body.get('result_code', -1) == 0)
    return success, body

def format_kakao_message(code: str, name: str, z: dict, sig: dict) -> str:
    arrow = '▲' if z['day_chg'] >= 0 else '▼'
    reasons_lines = '\n'.join(
        f"{'✅' if s=='pos' else '⚠️' if s=='neg' else 'ℹ️'} {t}"
        for s, t in sig['reasons'][:5]
    )
    loss_p = round((z['buy_mid'] - z['stop'])  / z['buy_mid'] * 100, 1)
    gain_p = round((z['tgt1']   - z['buy_mid'])/ z['buy_mid'] * 100, 1)

    return (
        f"📈 [{name} {code}] 분석 요약\n\n"
        f"현재가: {int(z['last']):,}원 {arrow} {abs(z['day_chg']):.1f}%\n"
        f"종합 신호: {sig['emoji']} {sig['label']} ({sig['score']}/100)\n\n"
        f"📌 핵심 매매 가격\n"
        f"매수 구간: {int(z['buy_low']):,} ~ {int(z['buy_high']):,}원\n"
        f"추천 매수가: {int(z['buy_mid']):,}원\n"
        f"손절가: {int(z['stop']):,}원 ({loss_p}%)\n"
        f"단기 목표: {int(z['tgt1']):,}원 (+{gain_p}%)\n\n"
        f"📊 분석 근거\n{reasons_lines}\n\n"
        f"52주 위치: {z['pos_pct']:.0f}%  RSI: {z['rsi']}\n\n"
        f"🔗 자세히 보기\n{REDIRECT_URI}"
    )


# ── 종목명 사전 (오프라인 fallback — 외부 API 전부 실패 시 사용) ──────────────
KNOWN_NAMES = {
    # 대형주
    '005930': '삼성전자',        '000660': 'SK하이닉스',
    '035420': 'NAVER',           '035720': '카카오',
    '005380': '현대차',          '000270': '기아',
    '051910': 'LG화학',          '006400': '삼성SDI',
    '207940': '삼성바이오로직스','068270': '셀트리온',
    '028260': '삼성물산',        '105560': 'KB금융',
    '055550': '신한지주',        '086790': '하나금융지주',
    '003550': 'LG',              '066570': 'LG전자',
    '096770': 'SK이노베이션',    '017670': 'SK텔레콤',
    '030200': 'KT',              '032830': '삼성생명',
    '373220': 'LG에너지솔루션',  '247540': '에코프로비엠',
    '086520': '에코프로',        '011200': 'HMM',
    '010140': '삼성중공업',      '042660': '한화오션',
    '329180': 'HD현대중공업',    '012330': '현대모비스',
    '000810': '삼성화재',        '090430': '아모레퍼시픽',
    '034730': 'SK',              '005490': 'POSCO홀딩스',
    '003490': '대한항공',        '000100': '유한양행',
    '128940': '한미약품',        '196170': '알테오젠',
    '145020': '휴젤',            '015760': '한국전력',
    # 반도체·장비
    '042700': '한미반도체',      '357780': '솔브레인',
    '240810': '원익IPS',         '285130': 'SK실트론',
    '336370': '솔브레인홀딩스',  '079550': 'LIG넥스원',
    '058470': '리노공업',        '036830': '솔브레인',
    # 2차전지
    '278280': '천보',            '064760': '티씨케이',
    '006280': '녹십자',          '298040': '효성첨단소재',
    # 바이오·제약
    '326030': 'SK바이오팜',      '000100': '유한양행',
    '091990': '셀트리온헬스케어','302440': 'SK바이오사이언스',
    '185750': '종근당',          '000520': '삼일제약',
    '214370': '케어젠',          '111770': '영원무역',
    # 자동차·부품
    '011210': '현대위아',        '204320': '현대트랜시스',
    '060980': '한라홀딩스',      '009540': 'HD한국조선해양',
    # 조선·방산
    '012450': '한화에어로스페이스','047810': '한국항공우주',
    '064350': '현대로템',        '272210': '한화시스템',
    # IT·게임
    '259960': '크래프톤',        '036570': 'NC소프트',
    '251270': '넷마블',          '263750': '펄어비스',
    '293490': '카카오게임즈',    '035960': 'DRB동일',
    '041510': 'SM엔터테인먼트',  '035900': 'JYP Ent.',
    '122870': 'YG엔터테인먼트',  '352820': '하이브',
    # 금융
    '316140': '우리금융지주',    '138930': 'BNK금융지주',
    '175330': 'JB금융지주',      '024110': '기업은행',
    '005940': 'NH투자증권',      '006800': '미래에셋증권',
    '039490': '키움증권',        '071050': '한국금융지주',
    # 전기전자·디스플레이
    '034220': 'LG디스플레이',    '009150': '삼성전기',
    '000990': 'DB하이텍',        '023590': '다우기술',
    # 철강·소재
    '004020': '현대제철',        '010060': 'OCI',
    '001440': '태한화학공업',    '002380': 'KCC',
    # 통신
    '032640': 'LG유플러스',
    # 유통·소비
    '139480': '이마트',          '004170': '신세계',
    '000720': '현대건설',        '028050': '삼성엔지니어링',
    '006360': 'GS건설',          '047040': '대우건설',
    '000240': '한국타이어앤테크놀로지',
    '271560': '오리온',          '097950': 'CJ제일제당',
    '003230': '삼양식품',        '007070': 'GS리테일',
    # 에너지
    '078930': 'GS',              '010950': 'S-Oil',
    # 항공·물류
    '020560': '아시아나항공',
    # 지주·기타
    '000150': '두산',            '004000': '롯데케미칼',
    '011070': 'LG이노텍',        '036460': '한국가스공사',
}

# ── KRX 전체 종목 ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400)
def load_krx_stocks():
    def _normalize(df):
        """컬럼명 → Code/Name 으로 통일. 실패 시 None 반환."""
        col_map = {}
        for c in df.columns:
            cl = (c.lower().strip()
                  .replace(' ', '').replace('_', '').replace('-', ''))
            if cl in ('code', 'symbol', '종목코드', '단축코드',
                      'ticker', 'isin', 'shortcode'):
                col_map[c] = 'Code'
            elif cl in ('name', '종목명', '회사명', 'corpname',
                        'shortname', 'company', '기업명', '단축명'):
                col_map[c] = 'Name'
        df = df.rename(columns=col_map)
        if 'Code' not in df.columns or 'Name' not in df.columns:
            return None
        df = df[['Code', 'Name']].copy()
        df['Code'] = df['Code'].astype(str).str.extract(r'(\d{6})')[0]
        df = df.dropna(subset=['Code'])
        return df.drop_duplicates('Code').reset_index(drop=True)

    # 1순위: FDR KRX 전체
    try:
        import FinanceDataReader as fdr
        result = _normalize(fdr.StockListing('KRX'))
        if result is not None and len(result) > 200:
            return result
    except Exception:
        pass

    # 2순위: FDR KOSPI + KOSDAQ 분리 요청
    try:
        import FinanceDataReader as fdr
        parts = []
        for market in ('KOSPI', 'KOSDAQ'):
            try:
                r = _normalize(fdr.StockListing(market))
                if r is not None and not r.empty:
                    parts.append(r)
            except Exception:
                pass
        if parts:
            combined = pd.concat(parts, ignore_index=True).drop_duplicates('Code')
            if len(combined) > 200:
                return combined.reset_index(drop=True)
    except Exception:
        pass

    # 3순위: pykrx — 티커 목록(빠름) + 이름 조회
    try:
        from pykrx import stock as pstock
        from datetime import datetime, timedelta
        tickers = []
        for back in range(5):   # 최근 5거래일 중 데이터 있는 날 탐색
            d = (datetime.today() - timedelta(days=back)).strftime('%Y%m%d')
            try:
                t = (pstock.get_market_ticker_list(d, market='KOSPI') +
                     pstock.get_market_ticker_list(d, market='KOSDAQ'))
                if t:
                    tickers = t
                    break
            except Exception:
                pass
        if tickers:
            rows = []
            for t in tickers:
                try:
                    rows.append({'Code': t.zfill(6),
                                 'Name': pstock.get_market_ticker_name(t)})
                except Exception:
                    pass
            if len(rows) > 200:
                return pd.DataFrame(rows).drop_duplicates('Code').reset_index(drop=True)
    except Exception:
        pass

    # 최종 fallback: 하드코딩 목록
    return pd.DataFrame(list(KNOWN_NAMES.items()), columns=['Code', 'Name'])


def search_stocks(krx, query):
    q = query.strip()
    if not q:
        return pd.DataFrame(columns=['Code', 'Name'])
    mask = (krx['Name'].str.contains(q, na=False, case=False, regex=False) |
            krx['Code'].str.contains(q, na=False, regex=False))
    return krx[mask].head(12)


# ── 관심종목 (쿠키 기반) ──────────────────────────────────────────────────────
def init_watchlist():
    """쿠키에서 관심종목 불러오기"""
    if 'watchlist'  not in st.session_state: st.session_state.watchlist  = []
    if 'wl_loaded'  not in st.session_state: st.session_state.wl_loaded  = False

    if not st.session_state.wl_loaded:
        if _ctrl is not None:
            try:
                raw = _ctrl.get('kr_watchlist')
                if raw:
                    loaded = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(loaded, list):
                        st.session_state.watchlist = loaded
            except Exception:
                pass
        st.session_state.wl_loaded = True


def _save_watchlist():
    """관심종목 쿠키에 저장 (1년 유지)"""
    if _ctrl is not None:
        try:
            _ctrl.set(
                'kr_watchlist',
                json.dumps(st.session_state.watchlist, ensure_ascii=False),
                max_age=60 * 60 * 24 * 365,
            )
        except Exception:
            pass

def add_to_watchlist(code, name):
    if not any(i['code'] == code for i in st.session_state.watchlist):
        st.session_state.watchlist.append({'code': code, 'name': name})
        _save_watchlist()

def remove_from_watchlist(code):
    st.session_state.watchlist = [i for i in st.session_state.watchlist if i['code'] != code]
    _save_watchlist()

def in_watchlist(code):
    return any(i['code'] == code for i in st.session_state.watchlist)


# ── 사이드바 미니 신호판용 빠른 현재가 ───────────────────────────────────────
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
        kp = kis_price(code, token, base)
        if kp:
            return kp
    return _get_price_fdr(code)


# ── 가격 알림 ────────────────────────────────────────────────────────────────
_GH_OWNER = "chein206"
_GH_REPO  = "stock-analyzer"
_GH_ALERTS_PATH = "data/price_alerts.json"


def _sync_alerts_to_github(alerts: dict) -> bool:
    """알림 설정을 GitHub 레포 파일에 동기화.
    Secrets에 github_pat 있을 때만 동작 (없으면 session_state 전용).
    """
    import base64
    pat = st.secrets.get("github_pat", "")
    if not pat:
        return False
    try:
        payload_str = json.dumps(
            {"alerts": alerts, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00")},
            ensure_ascii=False, indent=2
        )
        b64 = base64.b64encode(payload_str.encode("utf-8")).decode()
        api_url = (f"https://api.github.com/repos/{_GH_OWNER}/{_GH_REPO}"
                   f"/contents/{_GH_ALERTS_PATH}")
        headers = {
            "Authorization": f"token {pat}",
            "Accept": "application/vnd.github.v3+json",
        }
        # 현재 파일 SHA 조회 (업데이트에 필요)
        r = requests.get(api_url, headers=headers, timeout=5)
        sha = r.json().get("sha", "") if r.status_code == 200 else ""

        body = {"message": "update price alerts [skip ci]", "content": b64}
        if sha:
            body["sha"] = sha
        r2 = requests.put(api_url, headers=headers, json=body, timeout=10)
        return r2.status_code in (200, 201)
    except Exception:
        return False


def _load_alerts_from_github() -> dict:
    """GitHub 레포 파일에서 알림 설정 로드 (초기 1회)."""
    import base64
    pat = st.secrets.get("github_pat", "")
    if not pat:
        return {}
    try:
        api_url = (f"https://api.github.com/repos/{_GH_OWNER}/{_GH_REPO}"
                   f"/contents/{_GH_ALERTS_PATH}")
        r = requests.get(
            api_url,
            headers={"Authorization": f"token {pat}",
                     "Accept": "application/vnd.github.v3+json"},
            timeout=5,
        )
        if r.status_code == 200:
            content = base64.b64decode(r.json().get("content", "")).decode("utf-8")
            return json.loads(content).get("alerts", {})
    except Exception:
        pass
    return {}


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
        price = pinfo.get('price', 0)
        name  = cfg.get('name', code)
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

        elif target and stop:
            # 가격이 두 경계 사이로 회복되면 트리거 리셋
            if stop < price < target:
                alerts[code]['last_triggered'] = ''

    st.session_state['price_alerts'] = alerts


# ── 사이드바 ──────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        # ── 30초마다 가격 알림 체크 ───────────────────────────
        _now = time.time()
        if _now - st.session_state.get('_alert_last_check', 0) > 30:
            st.session_state['_alert_last_check'] = _now
            _check_price_alerts()

        # ── 미니 신호판 ──────────────────────────────────────
        st.markdown("## ⭐ 관심종목")
        wl = st.session_state.get('watchlist', [])

        if not wl:
            st.markdown(
                "<div style='color:var(--text-sub);font-size:13px;padding:8px 0'>"
                "아직 추가된 종목이 없어요.<br>"
                "분석 후 ☆ 버튼으로 추가하세요.</div>",
                unsafe_allow_html=True,
            )
        else:
            if 'price_alerts' not in st.session_state:
                # GitHub 파일에서 먼저 로드 시도, 없으면 빈 dict
                loaded = _load_alerts_from_github()
                st.session_state['price_alerts'] = loaded

            for item in wl:
                code = item['code']
                name = item['name']
                pinfo = get_quick_price(code)

                if pinfo:
                    price   = pinfo['price']
                    chg     = pinfo['chg_pct']
                    up      = chg >= 0
                    arrow   = '▲' if up else '▼'
                    dot     = '🟢' if up else '🔴'
                    p_color = '#C0392B' if up else '#1A5FAC'   # 한국식: 상승=빨강, 하락=파랑
                    price_str = f"{int(price):,}원 {arrow}{abs(chg):.2f}%"
                else:
                    price   = 0
                    dot       = '⚪'
                    p_color   = '#888'
                    price_str = '데이터 없음'

                # 종목 카드
                st.markdown(
                    f"<div class='mini-card'>"
                    f"<span style='font-size:14px;font-weight:700'>{dot} {name}</span>"
                    f"<br><span style='font-size:12px;color:{p_color};padding-left:4px'>{price_str}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                btn_c, del_c = st.columns([5, 1])
                with btn_c:
                    if st.button(f"📊 분석", key=f"wl_btn_{code}", use_container_width=True):
                        st.session_state['auto_code'] = code
                        st.session_state['auto_name'] = name
                        st.rerun()
                with del_c:
                    if st.button("✕", key=f"wl_del_{code}"):
                        remove_from_watchlist(code)
                        st.rerun()

                # ── 🔔 알림 설정 (종목별) ─────────────────────
                _al = st.session_state['price_alerts'].get(code, {})
                with st.expander(f"🔔 알림 설정", expanded=False):
                    _default_tgt = float(_al.get('target') or (price * 1.10 if price else 0))
                    _default_stp = float(_al.get('stop')   or (price * 0.93 if price else 0))
                    _tgt = st.number_input(
                        "목표가 (원)", min_value=0, value=int(_default_tgt),
                        step=100, key=f"al_tgt_{code}")
                    _stp = st.number_input(
                        "손절가 (원)", min_value=0, value=int(_default_stp),
                        step=100, key=f"al_stp_{code}")
                    col_save, col_del = st.columns(2)
                    with col_save:
                        if st.button("💾 저장", key=f"al_save_{code}", use_container_width=True):
                            st.session_state['price_alerts'][code] = {
                                'target': float(_tgt) if _tgt > 0 else None,
                                'stop':   float(_stp) if _stp > 0 else None,
                                'name':   name,
                                'enabled': True,
                                'last_triggered': '',
                            }
                            synced = _sync_alerts_to_github(st.session_state['price_alerts'])
                            if synced:
                                st.toast(f"✅ {name} 알림 저장 + GitHub 동기화 완료", icon="🔔")
                            else:
                                st.toast(f"✅ {name} 알림 저장됨 (앱 켜진 동안만)", icon="🔔")
                    with col_del:
                        if st.button("🗑 삭제", key=f"al_del_{code}", use_container_width=True):
                            st.session_state['price_alerts'].pop(code, None)
                            _sync_alerts_to_github(st.session_state['price_alerts'])
                            st.rerun()
                    if _al:
                        tgt_disp = f"{int(_al['target']):,}원" if _al.get('target') else '-'
                        stp_disp = f"{int(_al['stop']):,}원"   if _al.get('stop')   else '-'
                        st.caption(f"현재 설정: 목표 {tgt_disp} / 손절 {stp_disp}")

        # ── 카카오톡 연결 ─────────────────────────────────────
        st.divider()
        st.markdown("### 📱 카카오톡")

        # ① 알림 메시지 표시 (handle_kakao_callback 에서 저장한 것)
        if notify := st.session_state.pop('_kakao_notify', None):
            kind, msg = notify
            if kind == 'success':
                st.success(msg)
            else:
                st.error(msg)
                if debug := st.session_state.pop('_kakao_debug', None):
                    with st.expander("🔍 오류 상세"):
                        st.code(debug, language=None)
                        st.caption("이 내용을 캡처해서 공유해주세요")

        kakao_token = st.session_state.get('kakao_token')

        if kakao_token:
            # ── 연결된 상태 ──────────────────────────────────
            is_static = kakao_token.get('static', False)
            src_label = 'Secrets/수동' if is_static else 'OAuth'
            st.success(f"✅ 카카오 연결됨 ({src_label})")

            tc1, tc2 = st.columns(2)
            with tc1:
                if st.button("🔔 테스트", key="kakao_test",
                             use_container_width=True):
                    tok = get_valid_kakao_token()
                    if tok:
                        ok, res = send_kakao_message(
                            tok,
                            "📈 주식 분석기 연결 테스트\n카카오톡 전송이 정상 작동합니다! ✅")
                        # result_code 0 = 실제 성공, 나머지는 실패
                        result_code = res.get('result_code', -1) if ok else -1
                        if ok and result_code == 0:
                            st.toast("카카오톡 전송 성공! 📱", icon="✅")
                        else:
                            err_code = res.get('code', result_code)
                            err_msg  = res.get('msg', str(res))
                            st.error(f"전송 실패 ({err_code}): {err_msg}")
                            st.code(str(res), language=None)  # 실제 응답 출력
                            if err_code in (-401, -403):
                                st.caption("토큰 만료됨. 연결 해제 후 재연결해주세요.")
                    else:
                        st.warning("토큰 없음")
            with tc2:
                if st.button("연결 해제", key="kakao_disconnect",
                             use_container_width=True):
                    _clear_kakao_token(); st.rerun()

        else:
            # ── 미연결 상태 ──────────────────────────────────
            if not KAKAO_REST_KEY and not _KAKAO_STATIC_TOKEN:
                st.warning("Secrets에 `kakao_rest_key` 또는\n`kakao_access_token`을 설정하세요")
            else:
                # ── 방법 1: OAuth 로그인 (새 탭) ─────────────
                if KAKAO_REST_KEY:
                    auth_url = kakao_auth_url()
                    # st.link_button은 새 탭으로 열림 (HTML anchor 대체)
                    st.link_button(
                        "🔗 카카오 로그인 (새 탭)",
                        auth_url,
                        use_container_width=True,
                    )
                    st.caption(
                        "① 위 버튼 클릭 → 카카오 로그인\n"
                        "② 로그인 후 리다이렉트된 URL에서 `?code=` 뒤 값을 복사\n"
                        "③ 아래 **auth code 입력**에 붙여넣기"
                    )

                # ── 방법 2: Auth code 직접 입력 ──────────────
                with st.expander("📋 Auth code 직접 입력"):
                    st.caption(
                        "카카오 로그인 후 브라우저 주소창에서\n"
                        "`?code=XXXX` 부분의 XXXX만 복사해서 붙여넣기\n\n"
                        "예) `...streamlit.app?code=abc123` → `abc123` 입력"
                    )
                    auth_code_input = st.text_input(
                        "카카오 Auth Code",
                        placeholder="code 값을 붙여넣으세요",
                        key="kakao_auth_code_input",
                    )
                    if st.button("✅ 코드로 연결", key="kakao_code_apply",
                                 use_container_width=True):
                        if auth_code_input:
                            with st.spinner("토큰 교환 중..."):
                                ok, err = _apply_kakao_auth_code(auth_code_input)
                            if ok:
                                st.session_state['_kakao_notify'] = (
                                    'success', '✅ 카카오 연결 완료!')
                                st.rerun()
                            else:
                                st.error(err)
                                if dbg := st.session_state.pop('_kakao_debug', None):
                                    with st.expander("🔍 오류 상세"):
                                        st.code(dbg)
                        else:
                            st.warning("code를 입력해주세요.")

                # ── 방법 3: 액세스 토큰 직접 입력 ───────────
                with st.expander("🔑 액세스 토큰 직접 입력"):
                    st.caption(
                        "카카오 개발자 콘솔 → 내 앱 선택\n"
                        "→ **도구 > 토큰 발급** 또는\n"
                        "→ **플랫폼 > 카카오 로그인 테스트**에서 발급\n\n"
                        "⚠️ '앱 키'가 아닌 **액세스 토큰**을 입력하세요.\n"
                        "Secrets에 `kakao_access_token`으로 저장하면 자동 연결됩니다."
                    )
                    manual_tok = st.text_input(
                        "액세스 토큰",
                        type="password",
                        placeholder="액세스 토큰 (앱 키 아님)",
                        key="kakao_manual_token_input",
                    )
                    if st.button("✅ 토큰 저장 후 연결", key="kakao_manual_apply",
                                 use_container_width=True):
                        ok, err = _apply_manual_kakao_token(manual_tok)
                        if ok:
                            st.session_state['_kakao_notify'] = (
                                'success',
                                '✅ 토큰 저장 완료! 아래 테스트 버튼으로 확인하세요.')
                            st.rerun()
                        else:
                            st.error(err)

        # ── KIS API 연결 상태 ─────────────────────────────────────
        st.divider()
        if kis_available():
            _t = kis_get_token()
            if _t:
                _used = st.session_state.get('_kis_base_url', '')
                _env  = '모의투자' if 'vts' in _used else '실전투자'
                st.markdown(
                    f"<div style='font-size:12px;padding:4px 0'>"
                    f"🟢 <b style='color:#1D9E75'>KIS 실시간</b> ({_env})</div>",
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    "<div style='font-size:12px;padding:4px 0'>"
                    "🟡 <span style='color:#D4870E'>KIS 토큰 오류</span></div>",
                    unsafe_allow_html=True)
                _err = st.session_state.get('_kis_last_error', '')
                if _err:
                    with st.expander("🔍 오류 상세 보기"):
                        st.code(_err, language=None)
                        st.caption("위 내용을 캡처해서 공유해주세요")
        else:
            st.markdown(
                "<div style='font-size:12px;padding:4px 0;color:var(--text-muted)'>"
                "⚪ 지연 데이터 (KIS 미연동)</div>",
                unsafe_allow_html=True)

        # ── 조건 알림 (AlertMonitor) ─────────────────────────────────────
        if _QE and st.session_state.get('watchlist'):
            zones_cache = st.session_state.get('zones_cache', {})
            wl_with_z = [
                {**item, 'z': zones_cache[item['code']]}
                for item in st.session_state['watchlist']
                if item['code'] in zones_cache
            ]
            if wl_with_z:
                if 'alert_cache' not in st.session_state:
                    st.session_state['alert_cache'] = {}
                alerts = AlertMonitor.check(
                    wl_with_z, get_quick_price,
                    st.session_state['alert_cache'])
                for al in alerts:
                    lvl = al['level']
                    if   lvl == 'success': st.success(f"{al['emoji']} {al['msg']}")
                    elif lvl == 'error':   st.error(f"{al['emoji']} {al['msg']}")
                    elif lvl == 'warning': st.warning(f"{al['emoji']} {al['msg']}")
                    else:                  st.info(f"{al['emoji']} {al['msg']}")

        st.caption("💡 사이드바가 안 보이면\n화면 왼쪽 **>** 버튼을 누르세요")


# ── 데이터 수집 ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=900)
def get_stock_data(code, months):
    from datetime import datetime, timedelta
    import FinanceDataReader as fdr
    import yfinance as yf

    end = datetime.today(); start = end - timedelta(days=months * 31)
    s, e = start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')

    try:
        df = fdr.DataReader(code, s, e)
        if not df.empty and len(df) > 10:
            df.index = pd.to_datetime(df.index)
            df.columns = [c.capitalize() for c in df.columns]
            if 'Volume' not in df.columns: df['Volume'] = 0
            return df[['Open','High','Low','Close','Volume']]
    except Exception: pass

    for suffix in ['.KS', '.KQ']:
        try:
            df = yf.Ticker(f'{code}{suffix}').history(start=s, end=e)
            if not df.empty and len(df) > 10:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return df[['Open','High','Low','Close','Volume']]
        except Exception: pass
    return pd.DataFrame()


@st.cache_data(ttl=900)
def get_stock_info(code):
    import yfinance as yf
    for suffix in ['.KS', '.KQ']:
        try:
            raw = yf.Ticker(f'{code}{suffix}').info
            if raw and raw.get('regularMarketPrice'):
                return {
                    'per': raw.get('trailingPE'), 'pbr': raw.get('priceToBook'),
                    'roe': raw.get('returnOnEquity'), 'market_cap': raw.get('marketCap'),
                    'dividend': raw.get('dividendYield'), 'sector': raw.get('sector','-'),
                    '52w_high': raw.get('fiftyTwoWeekHigh'), '52w_low': raw.get('fiftyTwoWeekLow'),
                    'eps': raw.get('trailingEps'),
                    'dividend_rate': raw.get('dividendRate'),
                    'ex_dividend_date': raw.get('exDividendDate'),
                }
        except Exception: pass
    return {}


@st.cache_data(ttl=600)
def get_stock_news(name: str) -> list:
    """Google News RSS로 종목 관련 뉴스 5건 반환 (제목·링크·발행시간)."""
    import urllib.parse
    import xml.etree.ElementTree as ET
    try:
        rss_url = (f"https://news.google.com/rss/search?"
                   f"q={urllib.parse.quote(name)}&hl=ko&gl=KR&ceid=KR:ko")
        r = requests.get(rss_url, timeout=8,
                         headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = root.findall('.//item')[:5]
        news = []
        for it in items:
            title   = (it.findtext('title') or '').strip()
            link    = (it.findtext('link')  or '').strip()
            pub     = (it.findtext('pubDate') or '').strip()
            desc    = (it.findtext('description') or '').strip()
            # pubDate 파싱
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub)
                pub_fmt = dt.strftime('%m/%d %H:%M')
            except Exception:
                pub_fmt = pub[:16]
            news.append({'title': title, 'link': link,
                         'pub': pub_fmt, 'desc': desc})
        return news
    except Exception:
        return []


@st.cache_data(ttl=3600)
def get_investor_flow(code, days=20):
    """기관/외국인 수급 데이터 — pykrx 우선, 실패 시 KIS fallback."""
    from datetime import datetime, timedelta

    # 1순위: pykrx (20일 히스토리)
    try:
        from pykrx import stock as pstock
        end   = datetime.today()
        # 주말·공휴일 여유분을 넉넉히 (days × 3)
        start = end - timedelta(days=days * 3)
        df = pstock.get_market_trading_value_by_date(
            start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), code)
        if df is not None and not df.empty:
            # 거래 없는 날(합계=0) 제거
            df = df[df.abs().sum(axis=1) > 0]
            if len(df) >= 2:
                return df.tail(days)
    except Exception:
        pass

    # 2순위: KIS API — 오늘 하루 투자자별 데이터만이라도 반환
    try:
        token = kis_get_token()
        if not token:
            return None
        base = st.session_state.get('_kis_base_url', _KIS_REAL)
        r = requests.get(
            f"{base}/uapi/domestic-stock/v1/quotations/inquire-investor",
            headers={
                "Authorization": f"Bearer {token}",
                "appkey":       KIS_APP_KEY,
                "appsecret":    KIS_APP_SECRET,
                "tr_id":        "FHKST01010900",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD":         code,
            },
            timeout=10,
        )
        if r.status_code == 200:
            out = r.json().get('output', [])
            if out:
                rows = []
                for item in out[:days]:
                    try:
                        date_str = item.get('stck_bsop_date', '')
                        date = pd.to_datetime(date_str, format='%Y%m%d')
                        rows.append({
                            'date':    date,
                            '외국인':  float(item.get('frgn_ntby_qty', 0)) * 1000,
                            '기관합계': float(item.get('orgn_ntby_qty', 0)) * 1000,
                            '개인':    float(item.get('indv_ntby_qty', 0)) * 1000,
                        })
                    except Exception:
                        pass
                if rows:
                    df = pd.DataFrame(rows).set_index('date').sort_index()
                    return df
    except Exception:
        pass

    return None


@st.cache_data(ttl=86400)
def get_quarterly_earnings(code):
    import yfinance as yf
    for suffix in ['.KS', '.KQ']:
        try:
            fin = yf.Ticker(f'{code}{suffix}').quarterly_financials
            if fin is not None and not fin.empty and len(fin.columns) >= 2:
                return fin
        except Exception: pass
    return None


@st.cache_data(ttl=900)
def get_kospi_regime() -> dict | None:
    """KOSPI 시장 상태 감지 (15분 캐시). quant_engine 없으면 None 반환."""
    if not _QE:
        return None
    try:
        import FinanceDataReader as fdr
        from datetime import datetime, timedelta
        end   = datetime.today()
        start = end - timedelta(days=420)
        df = fdr.DataReader('KS11', start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
        if df is None or df.empty or len(df) < 60:
            return None
        df.columns = [c.capitalize() for c in df.columns]
        return MarketRegime.detect(df)
    except Exception:
        return None


# ── 기술지표 ─────────────────────────────────────────────────────────────────
def calc_indicators(df):
    import ta
    df = df.copy(); c = df['Close']
    for w, col in [(5,'MA5'),(20,'MA20'),(60,'MA60'),(120,'MA120')]:
        df[col] = c.rolling(w).mean()
    bb_mid = c.rolling(20).mean(); bb_std = c.rolling(20).std()
    df['BB_mid'] = bb_mid; df['BB_upper'] = bb_mid + 2*bb_std; df['BB_lower'] = bb_mid - 2*bb_std
    try:
        df['RSI'] = ta.momentum.RSIIndicator(c, window=14).rsi()
    except Exception:
        d = c.diff(); g = d.clip(lower=0).rolling(14).mean()
        l = (-d.clip(upper=0)).rolling(14).mean()
        df['RSI'] = 100 - 100 / (1 + g / l.replace(0, np.nan))
    try:
        m = ta.trend.MACD(c)
        df['MACD'] = m.macd(); df['MACD_signal'] = m.macd_signal(); df['MACD_hist'] = m.macd_diff()
    except Exception:
        e12 = c.ewm(span=12).mean(); e26 = c.ewm(span=26).mean()
        df['MACD'] = e12-e26; df['MACD_signal'] = df['MACD'].ewm(span=9).mean()
        df['MACD_hist'] = df['MACD'] - df['MACD_signal']
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()
    return df


def calc_zones(df, info):
    last     = df['Close'].iloc[-1]
    bb_lower = df['BB_lower'].iloc[-1]
    bb_upper = df['BB_upper'].iloc[-1]
    ma20     = df['MA20'].iloc[-1]
    ma60     = df['MA60'].iloc[-1]
    rsi      = df['RSI'].iloc[-1]
    w52_low  = info.get('52w_low')  or df['Low'].min()
    w52_high = info.get('52w_high') or df['High'].max()

    # ── 매수 구간 ──────────────────────────────────────────────────────
    buy_low  = max(bb_lower, w52_low * 1.03)
    buy_high = min(ma20, last * 0.99)
    if buy_high <= buy_low:
        buy_high = buy_low * 1.05
    buy_mid = (buy_low + buy_high) / 2
    stop    = round(buy_mid * 0.93 / 100) * 100

    # ── 목표가 — 반드시 현재가 위에 설정 ─────────────────────────────
    # 1차: 볼린저 상단 vs 현재가 +8% 중 높은 값
    tgt1_raw = round(bb_upper / 100) * 100
    tgt1     = max(tgt1_raw, round(last * 1.08 / 100) * 100)

    # 2차: 52주 고점 97% vs 현재가 +15% 중 높은 값
    tgt2_raw = round(w52_high * 0.97 / 100) * 100
    tgt2     = max(tgt2_raw, round(last * 1.15 / 100) * 100)

    # tgt2 는 tgt1 보다 반드시 위에
    if tgt2 <= tgt1:
        tgt2 = round(tgt1 * 1.07 / 100) * 100

    # 현재가가 이미 볼린저 상단을 넘었는지 플래그
    above_bb_upper = last > bb_upper

    # ── R:R ─────────────────────────────────────────────────────────
    # 현재가가 매수구간 위면 현재가를 기준 진입가로 사용 (보수적 계산)
    entry_ref = max(buy_mid, last)
    risk = entry_ref - stop
    rr   = round((tgt1 - entry_ref) / risk, 1) if risk > 0 and tgt1 > entry_ref else 0

    # ── 52주 위치, 등락 ──────────────────────────────────────────────
    pos_pct = (last - w52_low) / (w52_high - w52_low) * 100 if w52_high != w52_low else 50
    day_chg = (last / df['Close'].iloc[-2] - 1) * 100 if len(df) > 1 else 0.0

    return {
        'last': last, 'day_chg': day_chg,
        'buy_low':  round(buy_low  / 100) * 100,
        'buy_high': round(buy_high / 100) * 100,
        'buy_mid':  round(buy_mid  / 100) * 100,
        'stop': stop, 'tgt1': tgt1, 'tgt2': tgt2, 'rr': rr,
        'rsi': round(rsi, 1) if not np.isnan(rsi) else None,
        'pos_pct': round(pos_pct, 1), 'w52_low': w52_low, 'w52_high': w52_high,
        'ma20': ma20, 'ma60': ma60,
        'above_bb_upper': above_bb_upper,   # 신규: 볼린저 상단 돌파 여부
        'tgt1_raw': tgt1_raw,               # 신규: 원래 BB 기반 목표가 (참고용)
    }


def calc_signal(df, z, flow_df=None):
    score = 50; reasons = []
    rsi = z['rsi']; last = z['last']; pos = z['pos_pct']
    bb_lower = df['BB_lower'].iloc[-1]; bb_upper = df['BB_upper'].iloc[-1]
    bb_range = bb_upper - bb_lower
    bb_pct = (last - bb_lower) / bb_range if bb_range > 0 else 0.5
    macd_v = df['MACD'].iloc[-1]; macd_s = df['MACD_signal'].iloc[-1]
    macd_h = df['MACD_hist'].iloc[-1]
    macd_hp = df['MACD_hist'].iloc[-2] if len(df) > 1 else macd_h
    ma5, ma20, ma60 = df['MA5'].iloc[-1], df['MA20'].iloc[-1], df['MA60'].iloc[-1]

    if rsi is not None:
        if   rsi < 30:  score += 22; reasons.append(('pos', f'RSI {rsi:.0f} — 과매도 구간, 반등 가능성 높음'))
        elif rsi < 42:  score += 10; reasons.append(('pos', f'RSI {rsi:.0f} — 저점 근처'))
        elif rsi > 72:  score -= 22; reasons.append(('neg', f'RSI {rsi:.0f} — 과매수, 단기 조정 가능'))
        elif rsi > 62:  score -= 10; reasons.append(('neu', f'RSI {rsi:.0f} — 다소 높은 편'))

    if   bb_pct < 0.10: score += 20; reasons.append(('pos', '볼린저밴드 하단 근처 — 기술적 저점'))
    elif bb_pct < 0.35: score += 10; reasons.append(('pos', '볼린저밴드 하단~중간 — 매수 고려 구간'))
    elif bb_pct > 1.0:  score -= 28; reasons.append(('neg', '볼린저밴드 상단 돌파 — 추격 매수 고위험 구간'))
    elif bb_pct > 0.90: score -= 20; reasons.append(('neg', '볼린저밴드 상단 근처 — 단기 고점 주의'))
    elif bb_pct > 0.70: score -= 8

    if   macd_v > macd_s and macd_h > macd_hp and macd_h > 0:
        score += 15; reasons.append(('pos', 'MACD 상승 전환 — 매수 신호'))
    elif macd_v > macd_s and macd_h > macd_hp:
        score += 8;  reasons.append(('pos', 'MACD 개선 중 — 매수 신호 준비'))
    elif macd_v < macd_s and macd_h < macd_hp and macd_h < 0:
        score -= 15; reasons.append(('neg', 'MACD 하락 전환 — 매도 압력'))

    if   ma5 > ma20 > ma60: score += 10; reasons.append(('pos', '이동평균 정배열 — 상승 추세 유지'))
    elif ma5 < ma20 < ma60: score -= 10; reasons.append(('neg', '이동평균 역배열 — 하락 추세'))

    if   pos < 25: score += 15; reasons.append(('pos', f'52주 저점 근처 ({pos:.0f}%) — 역사적 저점 구간'))
    elif pos < 40: score += 5
    elif pos > 85: score -= 15; reasons.append(('neg', f'52주 고점 근처 ({pos:.0f}%) — 신중한 접근 필요'))
    elif pos > 70: score -= 5;  reasons.append(('neu', f'52주 상단 ({pos:.0f}%) — 다소 높은 위치'))

    # 수급 반영
    if flow_df is not None and not flow_df.empty:
        foreign_col = next((c for c in flow_df.columns if '외국인' in c), None)
        inst_col    = next((c for c in flow_df.columns if '기관' in c and '합계' in c), None)
        r5 = flow_df.tail(5)
        if foreign_col:
            f5 = r5[foreign_col].sum()
            if   f5 >  5e9: score += 12; reasons.append(('pos', f'외국인 최근 5일 순매수 +{f5/1e8:.0f}억'))
            elif f5 < -5e9: score -= 12; reasons.append(('neg', f'외국인 최근 5일 순매도 -{abs(f5)/1e8:.0f}억'))
        if inst_col:
            i5 = r5[inst_col].sum()
            if   i5 >  5e9: score += 8;  reasons.append(('pos', f'기관 최근 5일 순매수 +{i5/1e8:.0f}억'))
            elif i5 < -5e9: score -= 8;  reasons.append(('neg', f'기관 최근 5일 순매도 -{abs(i5)/1e8:.0f}억'))

    score = max(5, min(95, score))
    if   score >= 65: emoji, label, color, bg = '🟢', '매수 고려',  '#1D9E75', '#E8F8F2'; desc = '여러 지표가 매수 적합 신호를 보냅니다'
    elif score >= 45: emoji, label, color, bg = '🟡', '관망',       '#D4870E', '#FFF8E8'; desc = '명확한 신호가 없습니다. 조금 더 지켜보세요'
    else:             emoji, label, color, bg = '🔴', '매수 자제',  '#E24B4A', '#FEF0F0'; desc = '고점이거나 하락 추세입니다. 신중하게 접근하세요'

    return dict(score=score, emoji=emoji, label=label, color=color, bg=bg, desc=desc, reasons=reasons)


def build_signal_detail(z: dict, sig: dict, df) -> str:
    """신호 박스용 수치 기반 상세 설명 HTML 생성."""
    rsi     = z.get('rsi')
    pos     = z.get('pos_pct', 50)
    last    = z['last']
    score   = sig['score']
    buy_low = z['buy_low']
    buy_high= z['buy_high']
    buy_mid = z['buy_mid']
    stop    = z['stop']
    tgt1    = z['tgt1']
    ma20    = z['ma20']
    ma60    = z['ma60']

    # ── 지표 요약 칩 ──────────────────────────────────────────────
    chips = []

    # RSI
    if rsi is not None:
        if   rsi < 30:  chips.append(('pos', f'RSI {rsi:.0f} 과매도'))
        elif rsi < 45:  chips.append(('pos', f'RSI {rsi:.0f} 저점권'))
        elif rsi > 70:  chips.append(('neg', f'RSI {rsi:.0f} 과매수'))
        elif rsi > 60:  chips.append(('neu', f'RSI {rsi:.0f} 다소 높음'))
        else:           chips.append(('neu', f'RSI {rsi:.0f} 중립'))

    # 52주 위치
    if   pos < 25:  chips.append(('pos', f'52주 {pos:.0f}% 저점권'))
    elif pos < 40:  chips.append(('pos', f'52주 {pos:.0f}%'))
    elif pos > 85:  chips.append(('neg', f'52주 {pos:.0f}% 고점권'))
    else:           chips.append(('neu', f'52주 {pos:.0f}%'))

    # 볼린저밴드 위치
    bb_lower = df['BB_lower'].iloc[-1]
    bb_upper = df['BB_upper'].iloc[-1]
    bb_range = bb_upper - bb_lower
    if bb_range > 0:
        bb_pct = (last - bb_lower) / bb_range
        if   bb_pct < 0.15: chips.append(('pos', f'볼린저 하단 ({bb_pct*100:.0f}%)'))
        elif bb_pct < 0.40: chips.append(('pos', f'볼린저 하단~중단 ({bb_pct*100:.0f}%)'))
        elif bb_pct > 0.85: chips.append(('neg', f'볼린저 상단 ({bb_pct*100:.0f}%)'))
        else:               chips.append(('neu', f'볼린저 중단 ({bb_pct*100:.0f}%)'))

    # MACD
    macd_v = df['MACD'].iloc[-1]; macd_s = df['MACD_signal'].iloc[-1]
    macd_h = df['MACD_hist'].iloc[-1]
    macd_hp= df['MACD_hist'].iloc[-2] if len(df) > 1 else macd_h
    if   macd_v > macd_s and macd_h > macd_hp: chips.append(('pos', 'MACD 상승전환'))
    elif macd_v < macd_s and macd_h < macd_hp: chips.append(('neg', 'MACD 하락전환'))
    else: chips.append(('neu', 'MACD 혼조'))

    # 이동평균 배열
    ma5 = df['MA5'].iloc[-1]
    if   ma5 > ma20 > ma60: chips.append(('pos', '이평 정배열'))
    elif ma5 < ma20 < ma60: chips.append(('neg', '이평 역배열'))
    else:                   chips.append(('neu', '이평 혼조'))

    # ── 칩 HTML ───────────────────────────────────────────────────
    chip_colors = {'pos': '#1D9E75', 'neg': '#E24B4A', 'neu': '#888'}
    chip_bg     = {'pos': 'rgba(29,158,117,0.12)',
                   'neg': 'rgba(226,75,74,0.12)',
                   'neu': 'rgba(136,136,136,0.10)'}
    chip_html = ''.join(
        f"<span style='display:inline-block;margin:2px 3px;"
        f"padding:2px 8px;border-radius:20px;font-size:12px;font-weight:600;"
        f"color:{chip_colors[s]};background:{chip_bg[s]}'>{t}</span>"
        for s, t in chips[:5]
    )

    # ── 액션 문장 ─────────────────────────────────────────────────
    above_bb  = z.get('above_bb_upper', False)
    tgt1_raw  = z.get('tgt1_raw', tgt1)
    dist_to_buy = (last - buy_high) / buy_high * 100  # 양수=매수구간 위, 음수=이미 진입
    dist_pct    = abs(dist_to_buy)

    # 볼린저 상단 돌파 케이스 — 가장 먼저 체크
    if above_bb and last > tgt1_raw:
        over_pct = round((last - tgt1_raw) / tgt1_raw * 100, 1)
        pullback = round(tgt1_raw / 100) * 100
        action = (f"볼린저 상단(<b>{int(tgt1_raw):,}원</b>)을 <b>{over_pct}%</b> 초과한 강세 구간이에요. "
                  f"보유 중이라면 <b>분할 익절</b>(현재 +{over_pct}%)을 고려하고, "
                  f"신규 매수는 <b>{int(pullback):,}원</b> 부근 눌림목을 기다리세요. "
                  f"상단 돌파 직후 추격 매수는 고위험입니다.")
    elif score >= 65:
        if last <= buy_high:
            action = (f"현재가 <b>{int(last):,}원</b>이 매수 구간 "
                      f"<b>{int(buy_low):,}~{int(buy_high):,}원</b> 안에 있어요. "
                      f"손절 <b>{int(stop):,}원</b> / 목표 <b>{int(tgt1):,}원</b> 기준으로 분할 매수를 고려해보세요.")
        elif dist_pct <= 3:
            action = (f"매수 구간 <b>{int(buy_low):,}~{int(buy_high):,}원</b>보다 "
                      f"<b>{dist_pct:.1f}%</b> 위에 있어요. 소폭 눌림목 후 진입 고려.")
        else:
            action = (f"현재가 <b>{int(last):,}원</b>이 매수 구간 <b>{int(buy_high):,}원</b>보다 "
                      f"<b>{dist_pct:.1f}%</b> 높아요. 충분한 눌림목 후 분할 진입 전략 권장.")
    elif score >= 45:
        action = (f"뚜렷한 방향성이 없어요. MA20 <b>{int(ma20):,}원</b> · MA60 <b>{int(ma60):,}원</b> "
                  f"지지 여부를 확인 후, 매수 구간 <b>{int(buy_low):,}~{int(buy_high):,}원</b> 진입 시 재판단 권장.")
    else:
        action = (f"현재 하락 추세 또는 고점 신호 다수. "
                  f"매수 구간 <b>{int(buy_low):,}원</b> 이하로 충분히 내려올 때까지 관망을 권장해요. "
                  f"무리한 매수 보류.")

    return (
        f"<div style='margin-top:4px'>{chip_html}</div>"
        f"<div style='margin-top:10px;font-size:13px;line-height:1.7;opacity:0.9'>{action}</div>"
    )


def _render_regime_badge(regime: dict):
    """KOSPI 시장 상태 배지 (메인 페이지 상단 표시용)."""
    if not regime:
        return
    c = regime['color']
    label    = regime['label']
    emoji    = regime['emoji']
    strength = regime['strength']
    details  = regime.get('details', {})
    ma200_gap = details.get('ma200_gap', 0)
    ret20     = details.get('ret_20d',   0)
    adx       = details.get('adx',       0)
    st.markdown(
        f"<div style='display:inline-flex;align-items:center;gap:10px;"
        f"background:rgba(0,0,0,0.04);border:1px solid {c}44;"
        f"border-radius:10px;padding:8px 14px;margin-bottom:8px'>"
        f"<span style='font-size:22px'>{emoji}</span>"
        f"<div>"
        f"<span style='font-weight:800;font-size:15px;color:{c}'>KOSPI {label}</span>"
        f"<span style='font-size:12px;color:var(--text-muted);margin-left:8px'>신뢰도 {strength}%</span><br>"
        f"<span style='font-size:12px;color:var(--text-sub)'>"
        f"MA200 대비 {ma200_gap:+.1f}% · 20일 수익률 {ret20:+.1f}% · ADX {adx:.0f}"
        f"</span></div></div>",
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=3600)
def _cached_backtest(code: str, months: int):
    """백테스트 연산 캐시 (1시간). expander 열 때마다 재실행 방지."""
    if not _QE:
        return None
    df_raw = get_stock_data(code, months)
    if df_raw is None or df_raw.empty or len(df_raw) < 60:
        return None
    return Backtester.run(df_raw, initial_capital=10_000_000,
                          walk_forward=len(df_raw) >= 120, oos_ratio=0.3)


def _render_backtest(code: str, months: int):
    """백테스트 결과 렌더링 (expander 안에서 호출)."""
    if not _QE:
        st.caption("quant_engine이 설치되지 않았습니다."); return

    result = _cached_backtest(code, months)
    if result is None:
        st.caption("데이터 부족으로 백테스트를 실행할 수 없습니다."); return

    s = result.summary()
    if not result.trades:
        st.caption("백테스트 기간 내 신호가 발생하지 않았습니다."); return

    # ── 핵심 지표 ─────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    ret  = s['총 수익률 (%)']
    ret_col = '#1D9E75' if ret >= 0 else '#E24B4A'
    m1.metric("총 수익률",   f"{ret:+.1f}%",  delta=None)
    m2.metric("승률",        f"{s['승률 (%)']:.0f}%")
    m3.metric("MDD",         f"{s['MDD (%)']:.1f}%")
    m4.metric("Sharpe",      f"{s['Sharpe Ratio']:.2f}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("거래 횟수",   f"{s['거래 횟수']}건")
    c2.metric("Profit Factor", f"{s['Profit Factor']}")
    c3.metric("평균 수익",   f"{s['평균 수익 (%)']:+.1f}%")
    c4.metric("기댓값",      f"{s['기댓값 (%)']:+.2f}%")

    st.caption(f"📅 검증 기간: {s['검증 기간']}")

    # ── 주의사항 ──────────────────────────────────────────────────────
    st.info(
        "⚠️ **백테스트 주의사항** — 과거 성과가 미래를 보장하지 않습니다. "
        "Walk-Forward(OOS 30%) 방식으로 과적합을 최소화했으나 실전 수익률은 다를 수 있습니다. "
        "수수료 0.15% + 슬리피지 0.1% 포함 계산.",
        icon="ℹ️"
    )

    # ── 거래 내역 ─────────────────────────────────────────────────────
    if result.trades:
        trades_df = result.trades_df()
        with st.expander(f"📋 거래 내역 ({len(result.trades)}건)"):
            st.dataframe(trades_df, use_container_width=True, hide_index=True)

    # ── 에쿼티 커브 ───────────────────────────────────────────────────
    if len(result.equity_curve) > 5:
        import plotly.graph_objects as go
        eq  = result.equity_curve
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=eq.index, y=eq.values,
            fill='tozeroy', fillcolor='rgba(29,158,117,0.10)',
            line=dict(color='#1D9E75', width=2), name='자본'))
        fig.add_hline(y=10_000_000, line=dict(color='#888', width=1, dash='dot'))
        fig.update_layout(
            height=200, margin=dict(l=50, r=20, t=16, b=24),
            yaxis_title='자본 (원)', paper_bgcolor='white', plot_bgcolor='#FAFAF9',
            showlegend=False, font=dict(size=11),
            yaxis=dict(tickformat=','))
        fig.update_xaxes(showgrid=True, gridcolor='#EEE')
        fig.update_yaxes(showgrid=True, gridcolor='#EEE')
        st.plotly_chart(fig, use_container_width=True)


def _render_top5(top5: list, regime: dict):
    """TOP-5 추천 종목 렌더링."""
    if not top5:
        return

    r_lbl = regime['label']  if regime else '시장 미감지'
    r_emoji = regime['emoji'] if regime else '❓'

    st.markdown(f"### 🏆 AI 추천 TOP-5  <span style='font-size:14px;color:var(--text-muted)'>({r_emoji} {r_lbl} 기준)</span>",
                unsafe_allow_html=True)
    st.caption("복합 랭킹: 신호 점수 60% + R:R 30% + 52주 위치 역수 10%")

    for i, r in enumerate(top5, 1):
        reason = Recommender.reason(r, regime)
        tier   = r.get('tier', '중')
        tc = _TIER_COLOR.get(tier, '#888')
        tbg= _TIER_BG.get(tier, 'rgba(0,0,0,0.05)')
        tlbl = _TIER_LABEL.get(tier, tier)
        loss  = round((r['buy_mid'] - r['stop'])  / r['buy_mid'] * 100, 1) if r['buy_mid'] else 0
        gain  = round((r['tgt1']   - r['buy_mid'])/ r['buy_mid'] * 100, 1) if r['buy_mid'] else 0

        rc1, rc2, rc3 = st.columns([4, 3, 2])
        with rc1:
            st.markdown(
                f"<div style='font-size:15px;font-weight:800'>{i}. {r['emoji']} {r['name']}</div>"
                f"<div class='app-label'>"
                f"<span style='background:{tbg};color:{tc};border-radius:4px;"
                f"padding:1px 6px;font-size:11px;font-weight:700'>{tlbl}</span>"
                f"&nbsp;{r['sector']} · {r['code']}</div>"
                f"<div style='font-size:12px;color:var(--text-sub);margin-top:3px'>{reason}</div>",
                unsafe_allow_html=True)
        with rc2:
            rsi_c = ('#1D9E75' if r.get('rsi') and r['rsi'] < 40
                     else '#E24B4A' if r.get('rsi') and r['rsi'] > 65
                     else 'var(--text-label)')
            st.markdown(
                f"<div class='app-muted' style='line-height:1.9'>"
                f"점수: <b style='color:#1D9E75;font-size:16px'>{r['score']}</b> · "
                f"RSI: <b style='color:{rsi_c}'>{r.get('rsi', '-')}</b><br>"
                f"매수가: <b>{r['buy_mid']:,}원</b><br>"
                f"손절 <b style='color:#E24B4A'>-{loss}%</b> · "
                f"목표 <b style='color:#1D9E75'>+{gain}%</b> · R:R=1:{r['rr']}"
                f"</div>",
                unsafe_allow_html=True)
        with rc3:
            if st.button("📊 분석", key=f"top5_{r['code']}_{i}", use_container_width=True):
                st.session_state['auto_code'] = r['code']
                st.session_state['auto_name'] = r['name']
                st.session_state['go_analysis'] = True
                st.rerun()
        st.divider()


def price_position(last, z):
    above_bb = z.get('above_bb_upper', False)
    tgt1_raw = z.get('tgt1_raw', z['tgt1'])

    if last < z['stop']:
        return ('🔴', '손절 구간 아래입니다 — 보유 중이라면 손절 고려',              '#FEF0F0', '#E24B4A')
    if last <= z['buy_low']:
        return ('🎯', '매수 구간에 접근 중 — 분할 매수 고려',                        '#E8F8F2', '#1D9E75')
    if last <= z['buy_high']:
        return ('✅', '현재가가 매수 구간 안에 있습니다!',                             '#E8F8F2', '#1D9E75')
    if above_bb and last > tgt1_raw:
        # 볼린저 상단 돌파 → 기존 목표가 이미 넘어선 상태
        over_pct = round((last - tgt1_raw) / tgt1_raw * 100, 1)
        return ('🔥', f'볼린저 상단을 {over_pct}% 돌파 중 — 보유자는 분할 익절, 신규 매수는 눌림목 대기',
                '#FFF3E0', '#E65100')
    if last <= z['tgt1']:
        return ('🟡', '매수 구간보다 높습니다 — 눌림목(하락 후 반등) 기다리세요',      '#FFF8E8', '#D4870E')
    return     ('🏆', '단기 목표가 도달 구간 — 보유 중이라면 분할 익절 고려',          '#FFF9E6', '#B8860B')


def find_sr(df, n=5):
    recent = df.tail(60); highs, lows = recent['High'].values, recent['Low'].values
    sup, res = [], []
    for i in range(n, len(lows)-n):
        if all(lows[i]<=lows[i-j] for j in range(1,n+1)) and all(lows[i]<=lows[i+j] for j in range(1,n+1)):
            sup.append(lows[i])
    for i in range(n, len(highs)-n):
        if all(highs[i]>=highs[i-j] for j in range(1,n+1)) and all(highs[i]>=highs[i+j] for j in range(1,n+1)):
            res.append(highs[i])
    def cluster(lvls, pct=0.02):
        if not lvls: return []
        lvls = sorted(set(lvls)); result, grp = [lvls[0]], [lvls[0]]
        for v in lvls[1:]:
            if abs(v-grp[-1])/grp[-1] < pct: grp.append(v); result[-1] = np.mean(grp)
            else: grp=[v]; result.append(v)
        return result
    return cluster(sup)[-3:], cluster(res)[:3]


def build_chart(df, z):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    has_vol = 'Volume' in df.columns and df['Volume'].sum() > 0
    rows    = 4 if has_vol else 3
    heights = [0.50, 0.17, 0.17, 0.16] if has_vol else [0.58, 0.21, 0.21]
    titles  = ('주가 (캔들차트)', 'RSI', 'MACD', '거래량') if has_vol else ('주가 (캔들차트)', 'RSI', 'MACD')
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        row_heights=heights, vertical_spacing=0.03,
                        subplot_titles=titles)
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='주가',
        increasing_line_color='#E24B4A', decreasing_line_color='#185FA5',
        increasing_fillcolor='#E24B4A', decreasing_fillcolor='#185FA5'), row=1, col=1)
    for col, color, w in [('MA20','#534AB7',1.5),('MA60','#1D9E75',1.5)]:
        if col in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df[col], name=col,
                                     line=dict(color=color, width=w), opacity=0.9), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_upper'], name='BB 상단',
                             line=dict(color='#999', width=1, dash='dot'), opacity=0.5), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_lower'], name='BB 하단',
                             line=dict(color='#999', width=1, dash='dot'),
                             fill='tonexty', fillcolor='rgba(150,150,150,0.07)', opacity=0.5), row=1, col=1)
    if z['buy_high'] > z['buy_low'] > 0:
        fig.add_hrect(y0=z['buy_low'], y1=z['buy_high'],
                      fillcolor='rgba(29,158,117,0.13)',
                      line=dict(color='rgba(29,158,117,0.35)', width=1), row=1, col=1)
    fig.add_hline(y=z['stop'], row=1, col=1, line=dict(color='#E24B4A', width=1.8, dash='longdash'),
                  annotation_text=f"손절 {int(z['stop']):,}", annotation_font=dict(size=10, color='#C03333'),
                  annotation_position='bottom right')
    fig.add_hline(y=z['tgt1'], row=1, col=1, line=dict(color='#534AB7', width=1.5, dash='dot'),
                  annotation_text=f"목표 {int(z['tgt1']):,}", annotation_font=dict(size=10, color='#3C3489'),
                  annotation_position='top right')
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name='RSI',
                             line=dict(color='#534AB7', width=1.5)), row=2, col=1)
    fig.add_hline(y=70, row=2, col=1, line=dict(color='#E24B4A', width=1, dash='dot'))
    fig.add_hline(y=30, row=2, col=1, line=dict(color='#1D9E75', width=1, dash='dot'))
    fig.add_hrect(y0=70, y1=100, fillcolor='rgba(226,75,74,0.06)',  line_width=0, row=2, col=1)
    fig.add_hrect(y0=0,  y1=30,  fillcolor='rgba(29,158,117,0.06)', line_width=0, row=2, col=1)
    hist_colors = ['#E24B4A' if v>=0 else '#185FA5' for v in df['MACD_hist'].fillna(0)]
    fig.add_trace(go.Bar(x=df.index, y=df['MACD_hist'], name='히스토그램',
                         marker_color=hist_colors, opacity=0.55), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], name='MACD',
                             line=dict(color='#534AB7', width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_signal'], name='Signal',
                             line=dict(color='#E24B4A', width=1.5)), row=3, col=1)
    # ── 거래량 (4번째 서브플롯) ───────────────────────────────────────────
    if has_vol:
        vol_colors = [
            '#E24B4A' if o <= c else '#185FA5'
            for o, c in zip(df['Open'].fillna(0), df['Close'].fillna(0))
        ]
        fig.add_trace(go.Bar(
            x=df.index, y=df['Volume'],
            name='거래량', marker_color=vol_colors, opacity=0.65), row=4, col=1)
        if 'Vol_MA20' in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Vol_MA20'], name='거래량MA20',
                line=dict(color='#D4870E', width=1.4), opacity=0.9), row=4, col=1)

    chart_h = 680 if has_vol else 580
    fig.update_layout(height=chart_h, paper_bgcolor='white', plot_bgcolor='#FAFAF9',
                      legend=dict(orientation='h', y=1.02, x=1, xanchor='right', font=dict(size=11)),
                      xaxis_rangeslider_visible=False, hovermode='x unified',
                      margin=dict(l=50, r=90, t=36, b=24), font=dict(size=11))
    fig.update_xaxes(showgrid=True, gridcolor='#EEE', gridwidth=0.5)
    fig.update_yaxes(showgrid=True, gridcolor='#EEE', tickformat=',')
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    if has_vol:
        fig.update_yaxes(tickformat='.2s', row=4, col=1)   # 1.2M 형식
    return fig


def render_investor_flow(flow_df):
    import plotly.graph_objects as go
    if flow_df is None or flow_df.empty:
        st.markdown(
            "<div style='padding:16px;background:var(--card-bg);border-radius:10px;"
            "color:var(--text-muted);font-size:13px;text-align:center'>"
            "📡 수급 데이터를 가져올 수 없어요.<br>"
            "<span style='font-size:12px'>KRX 서버 응답이 없거나 거래일이 아닌 경우입니다.</span>"
            "</div>",
            unsafe_allow_html=True)
        return
    # 컬럼 탐지 — '합계' 없어도 '기관' 이름이 있으면 허용
    foreign_col = next((c for c in flow_df.columns if '외국인' in c), None)
    inst_col    = next((c for c in flow_df.columns
                        if '기관' in c and ('합계' in c or c == '기관')), None)
    indiv_col   = next((c for c in flow_df.columns if '개인' in c), None)
    if not foreign_col and not inst_col:
        st.caption(f"수급 컬럼을 인식할 수 없습니다. (컬럼: {list(flow_df.columns)})"); return
    r5 = flow_df.tail(5)
    cards = [(n, c) for n, c in [('외국인', foreign_col), ('기관', inst_col), ('개인', indiv_col)] if c]
    cols = st.columns(len(cards))
    for i, (name, col) in enumerate(cards):
        val = r5[col].sum(); color = '#1D9E75' if val >= 0 else '#E24B4A'
        trend = '▲ 순매수' if val >= 0 else '▼ 순매도'
        amount = f"+{val/1e8:.0f}억" if val >= 0 else f"-{abs(val)/1e8:.0f}억"
        with cols[i]:
            st.markdown(
                f"<div class='flow-card' style='border-top:3px solid {color}'>"
                f"<div style='font-size:12px;color:var(--text-muted)'>{name} (5일)</div>"
                f"<div style='font-size:17px;font-weight:800;color:{color}'>{trend}</div>"
                f"<div style='font-size:13px;color:{color}'>{amount}</div></div>",
                unsafe_allow_html=True)
    fig = go.Figure()
    if foreign_col:
        bar_colors = ['#1D9E75' if v>=0 else '#E24B4A' for v in flow_df[foreign_col]]
        fig.add_trace(go.Bar(x=flow_df.index, y=flow_df[foreign_col]/1e8,
                             name='외국인', marker_color=bar_colors, opacity=0.85))
    if inst_col:
        inst_colors = ['#534AB7' if v>=0 else '#A090D0' for v in flow_df[inst_col]]
        fig.add_trace(go.Bar(x=flow_df.index, y=flow_df[inst_col]/1e8,
                             name='기관', marker_color=inst_colors, opacity=0.6))
    fig.add_hline(y=0, line_color='#888', line_width=1)
    fig.update_layout(height=240, barmode='group', plot_bgcolor='#FAFAF9', paper_bgcolor='white',
                      margin=dict(l=50,r=20,t=16,b=24), yaxis_title='순매수 (억원)',
                      legend=dict(orientation='h', y=1.1, x=1, xanchor='right'), font=dict(size=11))
    fig.update_xaxes(showgrid=True, gridcolor='#EEE')
    fig.update_yaxes(showgrid=True, gridcolor='#EEE')
    st.plotly_chart(fig, use_container_width=True)
    st.caption("※ KRX 기준 / 양수=순매수(사는 중) / 음수=순매도(파는 중)")


def render_quarterly_earnings(earnings):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    if earnings is None or earnings.empty:
        st.caption("실적 데이터를 가져올 수 없습니다."); return
    rev_data = next((earnings.loc[k] for k in ['Total Revenue','Revenue','TotalRevenue'] if k in earnings.index), None)
    op_data  = next((earnings.loc[k] for k in ['Operating Income','EBIT','OperatingIncome'] if k in earnings.index), None)
    net_data = next((earnings.loc[k] for k in ['Net Income','NetIncome'] if k in earnings.index), None)
    if rev_data is None and op_data is None:
        st.caption("실적 데이터 형식을 확인할 수 없습니다."); return
    cols  = sorted(earnings.columns)[-4:]
    dates = [str(c)[:7] for c in cols]
    fig = make_subplots(rows=1, cols=2, subplot_titles=('매출/영업이익 (억원)', '순이익 (억원)'))
    if rev_data is not None:
        vals = [rev_data[c]/1e8 if pd.notna(rev_data[c]) else 0 for c in cols]
        fig.add_trace(go.Bar(x=dates, y=vals, name='매출', marker_color='#534AB7', opacity=0.5), row=1, col=1)
    if op_data is not None:
        vals = [op_data[c]/1e8 if pd.notna(op_data[c]) else 0 for c in cols]
        fig.add_trace(go.Bar(x=dates, y=vals, name='영업이익',
                             marker_color=['#1D9E75' if v>=0 else '#E24B4A' for v in vals], opacity=0.85), row=1, col=1)
    if net_data is not None:
        vals = [net_data[c]/1e8 if pd.notna(net_data[c]) else 0 for c in cols]
        fig.add_trace(go.Bar(x=dates, y=vals, name='순이익',
                             marker_color=['#1D9E75' if v>=0 else '#E24B4A' for v in vals], opacity=0.85), row=1, col=2)
    fig.update_layout(height=280, plot_bgcolor='#FAFAF9', paper_bgcolor='white',
                      margin=dict(l=40,r=20,t=36,b=24), showlegend=True, font=dict(size=11))
    fig.update_xaxes(showgrid=True, gridcolor='#EEE')
    fig.update_yaxes(showgrid=True, gridcolor='#EEE', tickformat=',')
    st.plotly_chart(fig, use_container_width=True)
    st.caption("※ Yahoo Finance 기준 · 단위: 억원 · 음수=적자")


# ── AI 채팅 액션 헬퍼 ────────────────────────────────────────────────────────
def _clipboard_btn(text: str, key: str):
    """클립보드 복사 버튼 (JavaScript, UTF-8 안전)."""
    import base64
    import streamlit.components.v1 as components
    # base64 encode → JS에서 decode (한국어 포함 모든 문자 안전)
    b64 = base64.b64encode(text.encode('utf-8')).decode()
    components.html(
        f"""
        <button id="btn_{key}" onclick="
            try {{
                const raw = atob('{b64}');
                const bytes = new Uint8Array(raw.length);
                for (let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i);
                const decoded = new TextDecoder('utf-8').decode(bytes);
                navigator.clipboard.writeText(decoded).then(() => {{
                    document.getElementById('btn_{key}').textContent='✅ 복사됨!';
                    setTimeout(() => document.getElementById('btn_{key}').textContent='📋 복사', 2000);
                }});
            }} catch(e) {{
                alert('복사 실패: ' + e);
            }}
        "
        style="width:100%;padding:5px 10px;background:#F5F5F5;border:1px solid #DDD;
               border-radius:7px;cursor:pointer;font-size:13px;font-family:inherit">
        📋 복사
        </button>
        """,
        height=34,
    )


def _kakao_send_btn(text: str, code: str, name: str, z: dict, key: str):
    """카카오톡 전송 버튼 (Streamlit 버튼)."""
    kakao_token = st.session_state.get('kakao_token')
    if not kakao_token:
        return
    if st.button("📱 카카오", key=f"kk_{key}", use_container_width=True):
        access_token = get_valid_kakao_token()
        if access_token:
            header = (f"📈 {name}({code}) AI 분석\n"
                      f"현재가 {int(z['last']):,}원 | 매수가 {int(z['buy_mid']):,}원\n\n")
            full_msg = header + text
            ok, result = send_kakao_message(access_token, full_msg)
            if ok:
                st.toast("카카오톡으로 전송했어요! ✅", icon="📱")
            else:
                err = result.get('msg', str(result))
                if result.get('code') in (-401, -403):
                    _clear_kakao_token()
                    st.warning("카카오 토큰 만료. 사이드바에서 재로그인 해주세요.")
                else:
                    st.error(f"전송 실패: {err}")
        else:
            st.warning("카카오 토큰이 만료됐어요.")


def _scenario_card(text: str, code: str, name: str, z: dict, key: str):
    """AI 응답을 시각적 카드로 렌더링 (스크린샷용)."""
    arrow = '▲' if z['day_chg'] >= 0 else '▼'
    chg_col = '#C0392B' if z['day_chg'] >= 0 else '#1A5FAC'
    # 마크다운 표(|)가 포함된 경우 그대로 st.markdown으로 렌더링
    st.markdown(
        f"""
        <div style='border:2px solid #534AB7;border-radius:14px;padding:20px 22px;
                    background:linear-gradient(135deg,#F8F8FF 0%,#EEF0FF 100%);
                    margin:4px 0'>
          <div style='font-size:13px;color:#888;margin-bottom:6px'>
            📸 시나리오 카드 — 스크린샷 후 공유하세요
          </div>
          <div style='font-size:17px;font-weight:800;color:#222;margin-bottom:2px'>
            📈 {name} <span style='color:#888;font-size:13px'>({code})</span>
          </div>
          <div style='font-size:14px;color:{chg_col};margin-bottom:12px'>
            현재가 {int(z['last']):,}원 {arrow}{abs(z['day_chg']):.2f}% &nbsp;|&nbsp;
            매수가 {int(z['buy_mid']):,}원 &nbsp;|&nbsp;
            손절 {int(z['stop']):,}원 &nbsp;|&nbsp;
            목표 {int(z['tgt1']):,}원
          </div>
          <hr style='border:none;border-top:1px solid #DDD;margin:8px 0'>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # 본문은 st.markdown으로 (표 렌더링 지원)
    st.markdown(text)
    st.caption("📱 위 내용을 스크린샷해서 카카오톡으로 공유하세요")


# ── AI 투자 상담 ──────────────────────────────────────────────────────────────
def ask_ai_advisor(question: str, code: str, name: str, z: dict, sig: dict,
                   history: list) -> str:
    """Claude API로 맞춤 투자 상담 답변 생성"""
    api_key = st.secrets.get("anthropic_api_key", "")
    if not api_key:
        return "⚠️ Streamlit Secrets에 `anthropic_api_key`를 추가해 주세요."

    import anthropic

    reasons_txt = "\n".join(
        f"  {'✅' if s=='pos' else '⚠️' if s=='neg' else 'ℹ️'} {t}"
        for s, t in sig['reasons']
    )

    system = f"""당신은 친근하고 실용적인 한국 주식 투자 상담 AI입니다.
사용자는 주린이(초보 투자자)일 수 있으니 어려운 용어는 쉽게 풀어서 설명하세요.

━━━ 현재 분석 중인 종목 ━━━
종목: {name} ({code})
현재가: {int(z['last']):,}원  (전일 대비 {z['day_chg']:+.2f}%)
종합 신호: {sig['emoji']} {sig['label']}  (점수 {sig['score']}/100)

📌 매매 가격대
  매수 구간: {int(z['buy_low']):,} ~ {int(z['buy_high']):,}원
  추천 매수가: {int(z['buy_mid']):,}원
  손절가: {int(z['stop']):,}원
  단기 목표가: {int(z['tgt1']):,}원
  중기 목표가: {int(z['tgt2']):,}원
  리스크:리워드 = 1:{z['rr']}

📊 기술 지표
  RSI: {z['rsi']}  (30 이하=과매도, 70 이상=과매수)
  52주 위치: {z['pos_pct']:.0f}%  (0%=52주 저점, 100%=52주 고점)
  MA20: {int(z['ma20']):,}원  /  MA60: {int(z['ma60']):,}원

📋 분석 근거
{reasons_txt}
━━━━━━━━━━━━━━━━━━━━━━━━━

답변 규칙:
1. 위 데이터를 적극 활용해 구체적으로 답변하세요 (가격, % 수치 포함).
2. 사용자가 보유 수량·평균 단가를 알려주면 수익률·손익 계산도 해주세요.
3. 분할 매수/매도 전략은 2~3단계로 나눠 설명하세요.
4. 시나리오 요청 시 반드시 마크다운 표(| 컬럼 | 값 |)로 단계별 정리하세요.
   표 예시: 단계 | 조건 | 수량 | 가격 | 예상 손익
4. 마지막에 항상 "⚠️ 투자 결정과 책임은 본인에게 있습니다" 한 줄 추가.
5. 절대 수익 보장 표현 금지. 한국어로만 답변."""

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": question})

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1200,
        system=system,
        messages=messages,
    )
    return resp.content[0].text


def render_ai_chat(code: str, name: str, z: dict, sig: dict):
    """AI 투자 상담 채팅 UI"""
    st.markdown("#### 🤖 AI 투자 상담")
    st.caption("보유 수량·단가를 알려주면 맞춤 매매 전략을 제안해드려요")

    chat_key = f"chat_{code}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    # 빠른 질문 버튼
    quick = [
        "지금 매수해도 괜찮을까요?",
        "손절 기준을 어떻게 잡아야 할까요?",
        "분할 매수 전략을 알려주세요",
        "지금 고점인가요, 저점인가요?",
    ]
    st.markdown("<div style='margin-bottom:6px;font-size:13px;color:var(--text-label)'>💡 빠른 질문</div>",
                unsafe_allow_html=True)
    cols = st.columns(2)
    for i, q in enumerate(quick):
        if cols[i % 2].button(q, key=f"quick_{code}_{i}", use_container_width=True):
            st.session_state[chat_key].append({"role": "user", "content": q})
            with st.spinner("AI 분석 중..."):
                answer = ask_ai_advisor(q, code, name, z, sig,
                                        st.session_state[chat_key][:-1])
            st.session_state[chat_key].append({"role": "assistant", "content": answer})
            st.rerun()

    # 시나리오 버튼 (풀 너비 강조)
    scenario_q = (
        f"10주 기준으로 매수·매도·손절 전체 시나리오를 세워주세요. "
        f"현재가 {int(z['last']):,}원 기준으로 "
        f"① 언제/어떻게 매수할지 (분할 단계 포함) "
        f"② 1차·2차 익절 시점과 수량 "
        f"③ 손절 조건과 예상 손실금액 "
        f"④ 전체 투자금 대비 기대 수익/손실 요약을 표로 정리해주세요."
    )
    if st.button("📋 매수·매도·손절 시나리오 (10주 기준)",
                 key=f"quick_{code}_scenario",
                 use_container_width=True, type="primary"):
        st.session_state[chat_key].append({"role": "user", "content": scenario_q})
        with st.spinner("AI가 시나리오를 작성 중... (10~20초)"):
            answer = ask_ai_advisor(scenario_q, code, name, z, sig,
                                    st.session_state[chat_key][:-1])
        st.session_state[chat_key].append({"role": "assistant", "content": answer})
        st.rerun()

    # 대화 기록 표시
    for idx, msg in enumerate(st.session_state[chat_key]):
        with st.chat_message(msg["role"],
                             avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

        # ── 어시스턴트 응답 하단 액션 버튼 ─────────────────────────────
        if msg["role"] == "assistant":
            btn_key = f"{code}_{idx}"
            content = msg["content"]
            ab1, ab2, ab3, ab4 = st.columns([1.4, 1.4, 1.4, 5])
            with ab1:
                _clipboard_btn(content, btn_key)
            with ab2:
                _kakao_send_btn(content, code, name, z, btn_key)
            with ab3:
                if st.button("📸 카드", key=f"card_{btn_key}",
                             use_container_width=True,
                             help="스크린샷용 시나리오 카드 보기"):
                    st.session_state[f"show_card_{btn_key}"] = \
                        not st.session_state.get(f"show_card_{btn_key}", False)
            # 카드 토글
            if st.session_state.get(f"show_card_{btn_key}", False):
                _scenario_card(content, code, name, z, btn_key)

    # 입력창
    placeholder = f"예: {int(z['last']*0.9):,}원에 100주 보유 중인데 매도 계획 어떻게 잡을까요?"
    if prompt := st.chat_input(placeholder, key=f"chat_input_{code}"):
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.spinner("AI 분석 중..."):
            answer = ask_ai_advisor(prompt, code, name, z, sig,
                                    st.session_state[chat_key][:-1])
        st.session_state[chat_key].append({"role": "assistant", "content": answer})
        st.rerun()   # ← 히스토리 즉시 갱신

    # 대화 초기화
    if st.session_state[chat_key]:
        if st.button("🗑️ 대화 초기화", key=f"chat_clear_{code}"):
            st.session_state[chat_key] = []
            st.rerun()


def render_news_tab(name: str, code: str, z: dict, sig: dict):
    """뉴스 탭 — Google News RSS 5건 + AI 요약 버튼."""
    with st.spinner("뉴스 가져오는 중..."):
        news = get_stock_news(name)

    if not news:
        st.info("뉴스를 가져올 수 없습니다. 잠시 후 다시 시도해주세요.")
        return

    for i, n in enumerate(news):
        title = n['title']
        link  = n['link']
        pub   = n['pub']
        st.markdown(
            f"<div style='background:var(--card-bg);border-radius:10px;"
            f"padding:10px 14px;margin-bottom:8px;border:1px solid var(--card-border)'>"
            f"<div style='font-size:14px;font-weight:700;word-break:keep-all;line-height:1.5'>"
            f"<a href='{link}' target='_blank' style='text-decoration:none;color:inherit'>{title}</a>"
            f"</div>"
            f"<div style='font-size:12px;color:var(--text-muted);margin-top:4px'>{pub}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.divider()
    if st.button("🤖 AI 뉴스 요약", key=f"news_ai_{code}", use_container_width=True):
        headlines = "\n".join(
            f"{i+1}. {n['title']}" for i, n in enumerate(news))
        summary_prompt = (
            f"다음은 '{name}' 관련 최신 뉴스 헤드라인입니다:\n{headlines}\n\n"
            f"위 뉴스를 3줄로 요약하고, 주가에 미칠 영향을 짧게 평가해주세요. "
            f"한국어로, 간결하게 답변하세요.")
        with st.spinner("AI가 뉴스를 분석 중..."):
            summary = ask_ai_advisor(
                summary_prompt, code, name, z, sig, [])
        st.markdown(f"**📰 AI 뉴스 요약**\n\n{summary}")


# ── 분석 결과 ─────────────────────────────────────────────────────────────────
def render_analysis(code, name, months):
    with st.spinner(f'{name} 데이터 수집 중...'):
        df_raw   = get_stock_data(code, months)
        info     = get_stock_info(code)
        flow_df  = get_investor_flow(code)
        earnings = get_quarterly_earnings(code)

        # ── KIS 실시간 데이터로 info 보강 ────────────────────────────
        _kis_data = None
        _kis_token = kis_get_token()
        if _kis_token:
            _kis_base = st.session_state.get('_kis_base_url', _KIS_REAL)
            _kis_data = kis_price(code, _kis_token, _kis_base)
            if _kis_data:
                # 더 정확한 KIS 지표로 덮어쓰기
                if _kis_data.get('per'):
                    info['per']      = _kis_data['per']
                if _kis_data.get('pbr'):
                    info['pbr']      = _kis_data['pbr']
                if _kis_data.get('w52_high'):
                    info['52w_high'] = _kis_data['w52_high']
                if _kis_data.get('w52_low'):
                    info['52w_low']  = _kis_data['w52_low']
                if _kis_data.get('market_cap') and not info.get('market_cap'):
                    info['market_cap'] = _kis_data['market_cap']

    if df_raw is None or df_raw.empty:
        st.error("데이터를 가져올 수 없습니다. 종목코드를 다시 확인해주세요."); return

    df  = calc_indicators(df_raw)
    z   = calc_zones(df, info)

    # ── KIS 실시간 현재가로 z 핵심 수치 교체 ────────────────────────────
    # calc_zones 는 FDR 종가(지연) 기준으로 계산됨
    # KIS 실시간 가격이 있으면 last · day_chg 만 교체 → AI에게도 실시간 맥락 전달
    if _kis_data and _kis_data.get('price'):
        kis_last    = _kis_data['price']
        kis_chg     = _kis_data.get('chg_pct', z['day_chg'])
        # 매매 가격대(buy_mid/stop/tgt)는 기술지표 기반이라 그대로 유지
        z['last']    = kis_last
        z['day_chg'] = kis_chg
        # 52주 위치도 KIS 실시간 가격으로 재계산
        wh, wl = z['w52_high'], z['w52_low']
        if wh != wl:
            z['pos_pct'] = round((kis_last - wl) / (wh - wl) * 100, 1)

    # ── 관심종목 zones 캐시 저장 (AlertMonitor용) ─────────────────────
    if 'zones_cache' not in st.session_state:
        st.session_state['zones_cache'] = {}
    st.session_state['zones_cache'][code] = z

    # ── 신호 평가 ─────────────────────────────────────────────────────
    # quant_engine 있으면 SignalEngine(4단계) 사용, 없으면 기존 calc_signal
    if _QE:
        regime = get_kospi_regime()
        sig = SignalEngine.evaluate(df, z, flow_df, regime)
    else:
        regime = None
        sig = calc_signal(df, z, flow_df)
    sup, res = find_sr(df)

    # 종목 헤더 + 버튼들
    chg_col = '#E24B4A' if z['day_chg'] >= 0 else '#185FA5'
    arrow   = '▲' if z['day_chg'] >= 0 else '▼'

    # 실시간 / 지연 뱃지
    if _kis_data:
        data_badge = (
            "<span style='font-size:11px;background:#E8F8F2;color:#1D9E75;"
            "border-radius:4px;padding:2px 7px;margin-left:8px;font-weight:700'>"
            "🟢 실시간</span>"
        )
    else:
        data_badge = (
            "<span style='font-size:11px;background:var(--card-bg2);color:var(--text-muted);"
            "border-radius:4px;padding:2px 7px;margin-left:8px;'>⏱ 지연</span>"
        )

    h_col, wl_col, kk_col = st.columns([4, 1, 1])
    with h_col:
        st.markdown(
            f"### {name} <span style='color:var(--text-sub);font-size:15px'>({code})</span>"
            f"{data_badge}<br>"
            f"<span style='font-size:30px;font-weight:900'>{int(z['last']):,}원</span>"
            f"&nbsp;<span style='font-size:16px;color:{chg_col}'>{arrow} {abs(z['day_chg']):.2f}%</span>",
            unsafe_allow_html=True)
    with wl_col:
        st.write(""); st.write("")
        if in_watchlist(code):
            if st.button("⭐ 저장됨", use_container_width=True):
                remove_from_watchlist(code); st.rerun()
        else:
            if st.button("☆ 관심종목", use_container_width=True):
                add_to_watchlist(code, name); st.rerun()
    with kk_col:
        st.write(""); st.write("")
        kakao_token = st.session_state.get('kakao_token')
        if kakao_token:
            if st.button("📱 카카오 전송", use_container_width=True, type="primary"):
                access_token = get_valid_kakao_token()
                if access_token:
                    msg = format_kakao_message(code, name, z, sig)
                    ok, result = send_kakao_message(access_token, msg)
                    if ok:
                        st.toast("카카오톡으로 전송했어요! ✅", icon="📱")
                    else:
                        err = result.get('msg', str(result))
                        if result.get('code') in (-401, -403):
                            _clear_kakao_token()
                            st.warning("카카오 토큰이 만료됐어요. 사이드바에서 다시 로그인해주세요.")
                        else:
                            st.error(f"전송 실패: {err}")
                else:
                    st.warning("카카오 토큰이 만료됐어요. 사이드바에서 다시 로그인해주세요.")
        else:
            st.button("📱 카카오 전송", use_container_width=True, disabled=True,
                      help="사이드바에서 카카오 로그인 후 사용 가능")

    # 신호 박스
    s = sig
    signal_detail = build_signal_detail(z, sig, df)
    regime_tag = ""
    if regime:
        regime_tag = (f"<span style='font-size:11px;background:{regime['color']}22;"
                      f"color:{regime['color']};border-radius:4px;padding:1px 7px;"
                      f"font-weight:700;margin-left:6px'>"
                      f"{regime['emoji']} {regime['label']}</span>")
    level_info = ""
    if _QE and sig.get('raw_score') is not None:
        adj = sig.get('regime_adj', 0)
        adj_txt = f"{adj:+d}" if adj != 0 else "±0"
        level_info = (f"<div style='font-size:11px;opacity:0.65;margin-top:2px'>"
                      f"원점수 {sig['raw_score']} 시장보정 {adj_txt}</div>")
    st.markdown(
        f"<div class='signal-box' style='background:{s['bg']};border:2px solid {s['color']}55'>"
        f"<div class='signal-emoji'>{s['emoji']}</div>"
        f"<div class='signal-label' style='color:{s['color']}'>{s['label']}{regime_tag}</div>"
        f"<div class='signal-score' style='color:{s['color']}'>종합 점수 {s['score']}/100 (기술지표 + 수급)</div>"
        f"{level_info}"
        f"<div class='signal-desc'>{signal_detail}</div></div>", unsafe_allow_html=True)

    # 현재가 위치
    icon, msg, bg, col = price_position(z['last'], z)
    st.markdown(
        f"<div class='price-bar' style='background:{bg};color:{col};border-left:4px solid {col}'>"
        f"{icon} {msg}</div>", unsafe_allow_html=True)

    # 핵심 매매 가격
    st.markdown("#### 📌 핵심 매매 가격")
    c1, c2 = st.columns(2)
    dp = round((z['last'] - z['buy_mid']) / z['buy_mid'] * 100, 1)
    sp = round((z['stop'] - z['buy_mid']) / z['buy_mid'] * 100, 1)
    with c1:
        st.markdown(
            f"<div class='zone-card' style='border-top:4px solid #1D9E75'>"
            f"<div class='zone-label'>🟢 매수 구간</div>"
            f"<div class='zone-value' style='color:#1D9E75'>{int(z['buy_low']):,} ~ {int(z['buy_high']):,}원</div>"
            f"<div class='zone-sub'>추천 매수가 {int(z['buy_mid']):,}원 · 현재가 대비 {dp:+.1f}%</div></div>",
            unsafe_allow_html=True)
    with c2:
        st.markdown(
            f"<div class='zone-card' style='border-top:4px solid #E24B4A'>"
            f"<div class='zone-label'>🔴 손절가</div>"
            f"<div class='zone-value' style='color:#E24B4A'>{int(z['stop']):,}원</div>"
            f"<div class='zone-sub'>매수가 대비 {sp:.1f}% · 이 이하면 손절</div></div>",
            unsafe_allow_html=True)
    st.write("")
    c3, c4 = st.columns(2)
    t1p = round((z['tgt1'] - z['buy_mid']) / z['buy_mid'] * 100, 1)
    t2p = round((z['tgt2'] - z['buy_mid']) / z['buy_mid'] * 100, 1)
    with c3:
        above_bb = z.get('above_bb_upper', False)
        tgt1_sub = "볼린저 상단 돌파 중 🔥" if above_bb else "볼린저 상단"
        tgt1_col = '#E65100' if above_bb else '#534AB7'
        st.markdown(
            f"<div class='zone-card' style='border-top:4px solid {tgt1_col}'>"
            f"<div class='zone-label'>🎯 단기 목표가</div>"
            f"<div class='zone-value' style='color:{tgt1_col}'>{int(z['tgt1']):,}원</div>"
            f"<div class='zone-sub'>매수가 대비 +{t1p:.1f}% · {tgt1_sub}</div></div>",
            unsafe_allow_html=True)
    with c4:
        st.markdown(
            f"<div class='zone-card' style='border-top:4px solid #BA7517'>"
            f"<div class='zone-label'>🏆 중기 목표가</div>"
            f"<div class='zone-value' style='color:#BA7517'>{int(z['tgt2']):,}원</div>"
            f"<div class='zone-sub'>매수가 대비 +{t2p:.1f}% · 52주 고점 부근</div></div>",
            unsafe_allow_html=True)

    rr = z['rr']
    rr_col = '#1D9E75' if rr >= 2 else '#D4870E' if rr >= 1 else '#E24B4A'
    rr_txt = '유리한 비율 👍' if rr >= 2 else '보통' if rr >= 1 else '불리한 비율'
    loss_p = round((z['buy_mid'] - z['stop'])  / z['buy_mid'] * 100, 1)
    gain_p = round((z['tgt1']   - z['buy_mid'])/ z['buy_mid'] * 100, 1)
    st.markdown(
        f"<div style='margin:12px 0 4px;font-size:13px;color:var(--text-label)'>"
        f"리스크:리워드 = <b style='color:{rr_col}'>1:{rr} ({rr_txt})</b>"
        f"&nbsp;·&nbsp; 손절 시 <b>-{loss_p}%</b>&nbsp;·&nbsp; 목표 시 <b>+{gain_p}%</b></div>",
        unsafe_allow_html=True)

    if sig['reasons']:
        st.markdown("#### 📊 분석 근거")
        for sentiment, text in sig['reasons']:
            icon_  = '✅' if sentiment=='pos' else '⚠️' if sentiment=='neg' else 'ℹ️'
            border = '#1D9E75' if sentiment=='pos' else '#E24B4A' if sentiment=='neg' else '#999'
            st.markdown(
                f"<div class='reason-box' style='border-left-color:{border}'>{icon_} {text}</div>",
                unsafe_allow_html=True)

    st.markdown("#### 📉 52주 가격 위치")
    lc, rc = st.columns(2)
    lc.caption(f"52주 저가: {int(z['w52_low']):,}원")
    rc.caption(f"52주 고가: {int(z['w52_high']):,}원")
    st.progress(max(0, min(100, int(z['pos_pct']))) / 100,
                text=f"현재가는 52주 범위의 {z['pos_pct']:.0f}% 위치")

    if sup or res:
        st.markdown("#### 🔲 지지선 / 저항선 (최근 60일)")
        lc2, rc2 = st.columns(2)
        with lc2:
            if sup:
                st.markdown("**지지선** (반등 가능 구간)")
                for v in sup:
                    st.markdown(f"- `{int(v):,}원` ({round((z['last']-v)/z['last']*100,1):+.1f}%)")
        with rc2:
            if res:
                st.markdown("**저항선** (매도 압력 구간)")
                for v in res:
                    st.markdown(f"- `{int(v):,}원` (+{round((v-z['last'])/z['last']*100,1):.1f}%)")

    # ── 재무 지표 & 배당 요약 행 ─────────────────────────────────────────────
    _per = info.get('per'); _pbr = info.get('pbr'); _roe = info.get('roe')
    _div = info.get('dividend'); _div_rate = info.get('dividend_rate')
    _ex_date = info.get('ex_dividend_date')
    _cap = info.get('market_cap'); _eps = info.get('eps')

    _has_metrics = any([_per, _pbr, _roe, _cap])
    _has_div = any([_div, _div_rate])

    if _has_metrics or _has_div:
        with st.expander("🏢 기업 기본 정보 · 재무 지표 · 배당", expanded=False):
            # 재무 지표 색상 코딩
            if _has_metrics:
                st.markdown("**📊 재무 지표**")
                _fm_cols = st.columns(4)
                with _fm_cols[0]:
                    if _cap:
                        st.metric("시가총액",
                                  f"{_cap/1e12:.1f}조" if _cap>=1e12 else f"{_cap/1e8:.0f}억")
                with _fm_cols[1]:
                    if _per:
                        _per_col = ('#1D9E75' if _per < 10
                                    else '#D4870E' if _per < 20 else '#E24B4A')
                        _per_delta = ('저평가' if _per < 10
                                      else '적정' if _per < 20 else '고평가')
                        st.metric("PER", f"{_per:.1f}배", _per_delta,
                                  delta_color="normal" if _per < 20 else "inverse")
                with _fm_cols[2]:
                    if _pbr:
                        _pbr_delta = '저평가' if _pbr < 1 else ('적정' if _pbr < 2 else '고평가')
                        st.metric("PBR", f"{_pbr:.2f}배", _pbr_delta,
                                  delta_color="normal" if _pbr < 2 else "inverse")
                with _fm_cols[3]:
                    if _roe:
                        _roe_pct = _roe * 100
                        _roe_delta = '우수' if _roe_pct >= 15 else ('양호' if _roe_pct >= 8 else '저조')
                        st.metric("ROE", f"{_roe_pct:.1f}%", _roe_delta)
                if _eps:
                    st.caption(f"EPS (주당순이익): {int(_eps):,}원")
                if info.get('sector') and info['sector'] != '-':
                    st.caption(f"섹터: {info['sector']}")

            # 배당 정보
            if _has_div:
                st.markdown("**💰 배당 정보**")
                _div_cols = st.columns(3)
                with _div_cols[0]:
                    if _div:
                        st.metric("배당수익률", f"{_div*100:.2f}%")
                with _div_cols[1]:
                    if _div_rate:
                        st.metric("연간 배당금", f"{_div_rate:,.0f}원")
                with _div_cols[2]:
                    if _ex_date:
                        try:
                            import datetime as _dt
                            _ex_dt = _dt.datetime.fromtimestamp(_ex_date)
                            st.metric("배당락일", _ex_dt.strftime('%Y-%m-%d'))
                        except Exception:
                            pass

    # ── 하단 탭: 차트·수급·실적·뉴스·AI상담 ─────────────────────────────────
    st.divider()
    _tab_chart, _tab_flow, _tab_earn, _tab_news, _tab_ai = st.tabs(
        ["📈 차트", "💰 수급", "📊 실적", "📰 뉴스", "🤖 AI상담"])

    with _tab_chart:
        st.plotly_chart(build_chart(df, z), use_container_width=True)
        with st.expander("🔍 상세 기술 분석"):
            rsi_v = z['rsi']; ma5_v = df['MA5'].iloc[-1]
            ma20_v = df['MA20'].iloc[-1]; ma60_v = df['MA60'].iloc[-1]
            macd_v = df['MACD'].iloc[-1]; macd_s = df['MACD_signal'].iloc[-1]
            ec1, ec2 = st.columns(2)
            with ec1:
                if rsi_v:
                    rsi_lbl = '과매도 ↗' if rsi_v < 30 else ('과매수 ↘' if rsi_v > 70 else '중립')
                    st.metric("RSI (14일)", f"{rsi_v:.1f}", rsi_lbl)
                st.metric("MACD", "골든크로스 (매수)" if macd_v > macd_s else "데드크로스 (매도)")
            with ec2:
                trend = ('정배열 — 상승 추세' if ma5_v > ma20_v > ma60_v
                         else '역배열 — 하락 추세' if ma5_v < ma20_v < ma60_v else '혼조')
                st.metric("이동평균 배열", trend)
                st.metric("MA20 / MA60", f"{int(ma20_v):,} / {int(ma60_v):,}원")

    with _tab_flow:
        st.markdown("#### 💰 기관/외국인 수급 현황 (최근 20일)")
        render_investor_flow(flow_df)

    with _tab_earn:
        with st.expander("📊 분기 실적 추이 (최근 4분기)", expanded=True):
            render_quarterly_earnings(earnings)
        if _QE:
            with st.expander("🔬 Walk-Forward 백테스트 (과거 성과 시뮬레이션)"):
                _render_backtest(code, months)

    with _tab_news:
        render_news_tab(name, code, z, sig)

    with _tab_ai:
        render_ai_chat(code, name, z, sig)

    st.divider()
    st.caption("⚠️ **투자 주의사항** — 본 분석은 기술적 지표 기반 참고 정보이며 투자 권유가 아닙니다. 모든 투자 판단과 책임은 투자자 본인에게 있습니다.")


# ── 포트폴리오 ───────────────────────────────────────────────────────────────
def init_portfolio():
    """쿠키에서 포트폴리오 보유 데이터 로드"""
    if 'portfolio'        not in st.session_state: st.session_state.portfolio        = {}
    if 'portfolio_loaded' not in st.session_state: st.session_state.portfolio_loaded = False

    if not st.session_state.portfolio_loaded:
        if _ctrl is not None:
            try:
                raw = _ctrl.get('kr_portfolio')
                if raw:
                    loaded = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(loaded, dict):
                        st.session_state.portfolio = loaded
            except Exception:
                pass
        st.session_state.portfolio_loaded = True


def save_portfolio():
    """포트폴리오 보유 데이터 쿠키 저장 (1년)"""
    if _ctrl is not None:
        try:
            _ctrl.set('kr_portfolio',
                      json.dumps(st.session_state.portfolio, ensure_ascii=False),
                      max_age=60 * 60 * 24 * 365)
        except Exception:
            pass


def render_portfolio_tab():
    wl = st.session_state.get('watchlist', [])
    if not wl:
        st.info("관심종목이 없어요.\n종목 분석 후 ⭐ 버튼으로 추가하면 여기서 수익률을 확인할 수 있어요.")
        return

    holdings = st.session_state.portfolio   # dict: {code: {avg_price, qty}}

    # ── 1단계: 현재가 + 보유 데이터 수집 (요약용) ────────────────────────────
    rows = []
    for item in wl:
        code, name = item['code'], item['name']
        pinfo = get_quick_price(code)
        h     = holdings.get(code, {})
        avg_p = h.get('avg_price', 0)
        qty   = h.get('qty', 0)
        cur_p = pinfo['price']   if pinfo else None
        chg   = pinfo['chg_pct'] if pinfo else None
        rows.append(dict(code=code, name=name, cur_p=cur_p, chg=chg,
                         avg_p=avg_p, qty=qty))

    # ── 2단계: 요약 카드 (보유 데이터 있는 종목만) ───────────────────────────
    invested_total = sum(r['avg_p'] * r['qty']
                         for r in rows if r['avg_p'] > 0 and r['qty'] > 0)
    current_total  = sum(r['cur_p'] * r['qty']
                         for r in rows
                         if r['avg_p'] > 0 and r['qty'] > 0 and r['cur_p'])

    if invested_total > 0:
        pnl_total     = current_total - invested_total
        pnl_pct_total = pnl_total / invested_total * 100
        p_col = '#C0392B' if pnl_total >= 0 else '#1A5FAC'
        st.markdown(
            f"<div class='app-card' style='display:flex;gap:32px;flex-wrap:wrap;margin-bottom:18px'>"
            f"<div><div class='app-label'>💰 총 투자금액</div>"
            f"<div style='font-size:20px;font-weight:800'>{int(invested_total):,}원</div></div>"
            f"<div><div class='app-label'>📈 총 평가금액</div>"
            f"<div style='font-size:20px;font-weight:800'>{int(current_total):,}원</div></div>"
            f"<div><div class='app-label'>💵 총 손익</div>"
            f"<div style='font-size:20px;font-weight:800;color:{p_col}'>"
            f"{'+'if pnl_total>=0 else ''}{int(pnl_total):,}원 "
            f"({pnl_pct_total:+.2f}%)</div></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── 3단계: 종목별 카드 ───────────────────────────────────────────────────
    for r in rows:
        code, name = r['code'], r['name']
        cur_p, chg = r['cur_p'], r['chg']
        h = holdings.get(code, {})

        with st.container():
            # 종목명 + 현재가 행
            hc1, hc2, hc3 = st.columns([4, 4, 1])
            with hc1:
                st.markdown(f"**{name}** `{code}`")
            with hc2:
                if cur_p and chg is not None:
                    up    = chg >= 0
                    arrow = '▲' if up else '▼'
                    c     = '#C0392B' if up else '#1A5FAC'
                    st.markdown(
                        f"<span style='color:{c};font-weight:700'>"
                        f"{int(cur_p):,}원 {arrow}{abs(chg):.2f}%</span>",
                        unsafe_allow_html=True)
                else:
                    st.caption("가격 조회 중...")
            with hc3:
                if st.button("📊", key=f"pt_go_{code}", help="종목 분석 탭에서 분석"):
                    st.session_state['auto_code'] = code
                    st.session_state['auto_name'] = name
                    st.session_state['go_analysis'] = True
                    st.rerun()

            # 평균단가 · 수량 입력 + 수익률
            ic1, ic2, ic3, ic4 = st.columns([2, 2, 3, 1])
            with ic1:
                avg_input = st.number_input(
                    "평균단가 (원)", min_value=0, step=100, format="%d",
                    value=h.get('avg_price', 0),
                    key=f"pt_avg_{code}")
            with ic2:
                qty_input = st.number_input(
                    "수량 (주)", min_value=0, step=1, format="%d",
                    value=h.get('qty', 0),
                    key=f"pt_qty_{code}")
            with ic3:
                if avg_input > 0 and qty_input > 0 and cur_p:
                    invested  = avg_input * qty_input
                    cur_val   = cur_p    * qty_input
                    pnl       = cur_val - invested
                    pnl_pct   = pnl / invested * 100
                    pc        = '#C0392B' if pnl >= 0 else '#1A5FAC'
                    arr       = '▲' if pnl >= 0 else '▼'
                    st.markdown(
                        f"<div style='padding-top:24px'>"
                        f"<span style='color:{pc};font-weight:700;font-size:15px'>"
                        f"{arr} {abs(pnl_pct):.2f}%&nbsp;&nbsp;"
                        f"({'+'if pnl>=0 else ''}{int(pnl):,}원)</span><br>"
                        f"<span class='app-sub'>"
                        f"매수 {int(invested):,}원 → 평가 {int(cur_val):,}원</span>"
                        f"</div>",
                        unsafe_allow_html=True)
                else:
                    st.markdown(
                        "<div style='padding-top:28px;font-size:13px;color:var(--text-muted)'>"
                        "단가·수량 입력 시 수익률 표시</div>",
                        unsafe_allow_html=True)
            with ic4:
                st.markdown("<div style='padding-top:22px'>", unsafe_allow_html=True)
                if st.button("💾", key=f"pt_save_{code}", help="저장"):
                    st.session_state.portfolio[code] = {
                        'avg_price': int(avg_input),
                        'qty':       int(qty_input),
                    }
                    save_portfolio()
                    st.toast(f"✅ {name} 저장 완료!")
                st.markdown("</div>", unsafe_allow_html=True)

            st.divider()

    st.caption("💡 💾 버튼으로 저장하면 다음에 앱을 열어도 단가·수량이 유지돼요")


# ── 스크리너 ─────────────────────────────────────────────────────────────────
# ── 스크리너 유니버스 (상/중/하 등급 포함, 약 200종목) ──────────────────────
# 형식: 'code': ('종목명', '섹터', '등급')
# 등급 상 = 코스피 대형주/블루칩  중 = 코스피 중형·코스닥 대형  하 = 성장·테마주
SCREEN_UNIVERSE = {
    # ── 반도체 ──────────────────────────────────────────────────────────────
    '005930': ('삼성전자',          '반도체', '상'),
    '000660': ('SK하이닉스',        '반도체', '상'),
    '042700': ('한미반도체',        '반도체', '중'),
    '009150': ('삼성전기',          '반도체', '중'),
    '011070': ('LG이노텍',          '반도체', '중'),
    '240810': ('원익IPS',           '반도체', '하'),
    '357780': ('솔브레인',          '반도체', '하'),
    '058470': ('리노공업',          '반도체', '하'),
    '039030': ('이오테크닉스',      '반도체', '하'),
    '095340': ('ISC',               '반도체', '하'),
    # ── 2차전지 ─────────────────────────────────────────────────────────────
    '373220': ('LG에너지솔루션',    '2차전지', '상'),
    '006400': ('삼성SDI',           '2차전지', '상'),
    '051910': ('LG화학',            '2차전지', '상'),
    '096770': ('SK이노베이션',      '2차전지', '상'),
    '247540': ('에코프로비엠',      '2차전지', '중'),
    '086520': ('에코프로',          '2차전지', '중'),
    '278280': ('천보',              '2차전지', '중'),
    '298040': ('효성첨단소재',      '2차전지', '중'),
    '064760': ('티씨케이',          '2차전지', '하'),
    '334370': ('엔켐',              '2차전지', '하'),
    '003670': ('포스코퓨처엠',      '2차전지', '중'),
    '272290': ('이엔에프테크놀로지','2차전지', '하'),
    # ── 바이오/제약 ─────────────────────────────────────────────────────────
    '207940': ('삼성바이오로직스',  '바이오', '상'),
    '068270': ('셀트리온',          '바이오', '상'),
    '128940': ('한미약품',          '바이오', '중'),
    '000100': ('유한양행',          '바이오', '중'),
    '196170': ('알테오젠',          '바이오', '중'),
    '145020': ('휴젤',              '바이오', '중'),
    '326030': ('SK바이오팜',        '바이오', '중'),
    '091990': ('셀트리온헬스케어',  '바이오', '중'),
    '302440': ('SK바이오사이언스',  '바이오', '중'),
    '185750': ('종근당',            '바이오', '중'),
    '006280': ('녹십자',            '바이오', '중'),
    '214370': ('케어젠',            '바이오', '하'),
    '237690': ('에스티팜',          '바이오', '하'),
    '950130': ('엑세스바이오',      '바이오', '하'),
    # ── 자동차/부품 ─────────────────────────────────────────────────────────
    '005380': ('현대차',            '자동차', '상'),
    '000270': ('기아',              '자동차', '상'),
    '012330': ('현대모비스',        '자동차', '상'),
    '011210': ('현대위아',          '자동차', '중'),
    '161390': ('한국타이어앤테크놀로지','자동차','중'),
    '204320': ('현대트랜시스',      '자동차', '중'),
    '060980': ('한라홀딩스',        '자동차', '하'),
    # ── 조선/방산 ───────────────────────────────────────────────────────────
    '329180': ('HD현대중공업',      '조선/방산', '상'),
    '042660': ('한화오션',          '조선/방산', '상'),
    '010140': ('삼성중공업',        '조선/방산', '상'),
    '012450': ('한화에어로스페이스','조선/방산', '상'),
    '047810': ('한국항공우주',      '조선/방산', '중'),
    '064350': ('현대로템',          '조선/방산', '중'),
    '272210': ('한화시스템',        '조선/방산', '중'),
    '079550': ('LIG넥스원',         '조선/방산', '중'),
    '009540': ('HD한국조선해양',    '조선/방산', '상'),
    # ── IT/플랫폼/게임 ───────────────────────────────────────────────────────
    '035420': ('NAVER',             'IT', '상'),
    '035720': ('카카오',            'IT', '상'),
    '259960': ('크래프톤',          'IT', '상'),
    '036570': ('NC소프트',          'IT', '중'),
    '251270': ('넷마블',            'IT', '중'),
    '263750': ('펄어비스',          'IT', '중'),
    '293490': ('카카오게임즈',      'IT', '중'),
    '112040': ('위메이드',          'IT', '하'),
    '078340': ('컴투스',            'IT', '하'),
    '192080': ('더블유게임즈',      'IT', '하'),
    '067160': ('아프리카TV',        'IT', '하'),
    # ── 엔터/미디어 ─────────────────────────────────────────────────────────
    '352820': ('하이브',            '엔터', '중'),
    '041510': ('SM엔터테인먼트',    '엔터', '중'),
    '035900': ('JYP Ent.',          '엔터', '중'),
    '122870': ('YG엔터테인먼트',    '엔터', '중'),
    '028040': ('CJ ENM',            '엔터', '중'),
    # ── 금융 ────────────────────────────────────────────────────────────────
    '105560': ('KB금융',            '금융', '상'),
    '055550': ('신한지주',          '금융', '상'),
    '086790': ('하나금융지주',      '금융', '상'),
    '032830': ('삼성생명',          '금융', '상'),
    '000810': ('삼성화재',          '금융', '상'),
    '316140': ('우리금융지주',      '금융', '상'),
    '024110': ('기업은행',          '금융', '중'),
    '138930': ('BNK금융지주',       '금융', '중'),
    '175330': ('JB금융지주',        '금융', '중'),
    '005940': ('NH투자증권',        '금융', '중'),
    '006800': ('미래에셋증권',      '금융', '중'),
    '039490': ('키움증권',          '금융', '중'),
    '071050': ('한국금융지주',      '금융', '중'),
    '088350': ('한화생명',          '금융', '중'),
    # ── 전기전자/디스플레이 ─────────────────────────────────────────────────
    '066570': ('LG전자',            '전기전자', '상'),
    '034220': ('LG디스플레이',      '전기전자', '중'),
    '000990': ('DB하이텍',          '전기전자', '하'),
    '032680': ('루멘스',            '전기전자', '하'),
    # ── 철강/소재 ───────────────────────────────────────────────────────────
    '005490': ('POSCO홀딩스',       '철강/소재', '상'),
    '004020': ('현대제철',          '철강/소재', '중'),
    '010130': ('고려아연',          '철강/소재', '중'),
    '002380': ('KCC',               '철강/소재', '중'),
    '010060': ('OCI',               '철강/소재', '중'),
    # ── 화학 ────────────────────────────────────────────────────────────────
    '004000': ('롯데케미칼',        '화학', '중'),
    '009830': ('한화솔루션',        '화학', '중'),
    '011170': ('롯데케미칼',        '화학', '중'),
    '025000': ('KPX케미칼',         '화학', '하'),
    # ── 통신 ────────────────────────────────────────────────────────────────
    '017670': ('SK텔레콤',          '통신', '상'),
    '030200': ('KT',                '통신', '상'),
    '032640': ('LG유플러스',        '통신', '상'),
    # ── 건설 ────────────────────────────────────────────────────────────────
    '000720': ('현대건설',          '건설', '중'),
    '006360': ('GS건설',            '건설', '중'),
    '028050': ('삼성엔지니어링',    '건설', '중'),
    '047040': ('대우건설',          '건설', '중'),
    '034020': ('두산에너빌리티',    '건설', '중'),
    # ── 유통/소비 ───────────────────────────────────────────────────────────
    '139480': ('이마트',            '유통/소비', '중'),
    '004170': ('신세계',            '유통/소비', '중'),
    '090430': ('아모레퍼시픽',      '유통/소비', '중'),
    '097950': ('CJ제일제당',        '유통/소비', '중'),
    '271560': ('오리온',            '유통/소비', '중'),
    '003230': ('삼양식품',          '유통/소비', '중'),
    '007070': ('GS리테일',          '유통/소비', '중'),
    '023530': ('롯데쇼핑',          '유통/소비', '중'),
    '111770': ('영원무역',          '유통/소비', '하'),
    # ── 에너지 ──────────────────────────────────────────────────────────────
    '034730': ('SK',                '에너지', '상'),
    '015760': ('한국전력',          '에너지', '상'),
    '010950': ('S-Oil',             '에너지', '중'),
    '078930': ('GS',                '에너지', '중'),
    '036460': ('한국가스공사',      '에너지', '중'),
    # ── 항공/물류 ───────────────────────────────────────────────────────────
    '003490': ('대한항공',          '항공/물류', '상'),
    '011200': ('HMM',               '항공/물류', '중'),
    '020560': ('아시아나항공',      '항공/물류', '중'),
    '086280': ('현대글로비스',      '항공/물류', '중'),
    # ── 지주/기타 ───────────────────────────────────────────────────────────
    '003550': ('LG',                '기타', '상'),
    '028260': ('삼성물산',          '기타', '상'),
    '000150': ('두산',              '기타', '중'),
    '241560': ('두산밥캣',          '기타', '중'),
    '267250': ('HD현대',            '기타', '중'),
}


def _scan_one(args):
    """단일 종목 스캔 (멀티스레드용)"""
    code, name, sector, tier = args
    try:
        df_raw = get_stock_data(code, 3)
        if df_raw is None or df_raw.empty or len(df_raw) < 20:
            return None
        df  = calc_indicators(df_raw)
        z   = calc_zones(df, {})
        sig = SignalEngine.evaluate(df, z) if _QE else calc_signal(df, z)
        return {
            'code': code, 'name': name, 'sector': sector, 'tier': tier,
            'score':   sig['score'],
            'emoji':   sig['emoji'],
            'label':   sig['label'],
            'price':   int(z['last']),
            'day_chg': round(z['day_chg'], 2),
            'rsi':     z['rsi'],
            'pos_pct': round(z['pos_pct'], 1),
            'buy_mid': int(z['buy_mid']),
            'stop':    int(z['stop']),
            'tgt1':    int(z['tgt1']),
            'rr':      z['rr'],
        }
    except Exception:
        return None


@st.cache_data(ttl=3600)
def run_screen(min_score: int, max_rsi: int, max_pos_pct: int,
               sectors: tuple, tiers: tuple) -> list:
    """전체 유니버스 병렬 스캔 (1시간 캐시)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    args_list = [
        (code, info[0], info[1], info[2])
        for code, info in SCREEN_UNIVERSE.items()
        if ('전체' in sectors or info[1] in sectors)
        and ('전체' in tiers   or info[2] in tiers)
    ]
    results = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = {ex.submit(_scan_one, a): a for a in args_list}
        for f in as_completed(futures):
            r = f.result()
            if r is None:                       continue
            if r['score'] < min_score:          continue
            if r['rsi'] and r['rsi'] > max_rsi: continue
            if r['pos_pct'] > max_pos_pct:      continue
            results.append(r)
    return sorted(results, key=lambda x: x['score'], reverse=True)


# 등급별 색상
_TIER_COLOR = {'상': '#534AB7', '중': '#D4870E', '하': '#1D9E75'}
_TIER_BG    = {'상': 'rgba(83,74,183,0.12)',
               '중': 'rgba(212,135,14,0.12)',
               '하': 'rgba(29,158,117,0.12)'}
_TIER_LABEL = {'상': '상 · 대형주', '중': '중 · 중형주', '하': '하 · 성장주'}


def render_screener_tab():
    st.markdown("### 🔍 종목 스크리너")
    n_total = len(SCREEN_UNIVERSE)
    st.caption(f"총 {n_total}개 종목 · 신호 점수 순 정렬 · 1시간 캐시")

    # ── 저장된 조건 불러오기 (쿠키) ─────────────────────────────────────────
    _saved_filter = {}
    if _ctrl is not None:
        try:
            _raw_f = _ctrl.get('kr_screener_filter')
            if _raw_f:
                _saved_filter = json.loads(_raw_f) if isinstance(_raw_f, str) else _raw_f
        except Exception:
            pass

    # ── 조건 설정 ────────────────────────────────────────────────────────────
    with st.expander("⚙️ 스캔 조건 설정", expanded=True):
        # 저장/불러오기 버튼 행
        _sv1, _sv2 = st.columns(2)
        _load_clicked = _sv1.button("📂 조건 불러오기", use_container_width=True,
                                     key="scr_load",
                                     disabled=not bool(_saved_filter))
        _save_now = False  # 저장 버튼은 슬라이더 값 알고 난 뒤에 처리

        # 저장된 값으로 초기값 설정
        if _load_clicked and _saved_filter:
            st.session_state['_scr_min_score']  = _saved_filter.get('min_score', 65)
            st.session_state['_scr_max_rsi']    = _saved_filter.get('max_rsi', 60)
            st.session_state['_scr_max_pos_pct'] = _saved_filter.get('max_pos_pct', 55)
            st.toast("✅ 조건 불러오기 완료!", icon="📂")

        c1, c2, c3 = st.columns(3)
        with c1:
            min_score = st.slider(
                "🎯 최소 신호 점수", 50, 85,
                st.session_state.get('_scr_min_score', 65), step=5,
                help="65↑ 매수 고려 / 높을수록 강한 신호만",
                key="scr_slider_min_score")
        with c2:
            max_rsi = st.slider(
                "📉 RSI 상한선", 40, 75,
                st.session_state.get('_scr_max_rsi', 60), step=5,
                help="낮을수록 과매도 구간 종목만 (30=과매도, 70=과매수)",
                key="scr_slider_max_rsi")
        with c3:
            max_pos_pct = st.slider(
                "📍 52주 위치 상한 (%)", 30, 80,
                st.session_state.get('_scr_max_pos_pct', 55), step=5,
                help="낮을수록 52주 저점 근처 종목만",
                key="scr_slider_max_pos_pct")

        # 등급 체크박스
        st.markdown("**📊 종목 등급**")
        tc1, tc2, tc3 = st.columns(3)
        chk_상 = tc1.checkbox('🔵 상  (대형주)', value=True)
        chk_중 = tc2.checkbox('🟡 중  (중형주)', value=True)
        chk_하 = tc3.checkbox('🟢 하  (성장주)', value=True)
        selected_tiers = [t for t, c in [('상', chk_상), ('중', chk_중), ('하', chk_하)] if c]
        if not selected_tiers:
            selected_tiers = ['상', '중', '하']

        # 섹터 필터
        all_sectors = ['반도체', '2차전지', '바이오', '자동차', '조선/방산',
                       'IT', '엔터', '금융', '전기전자', '철강/소재',
                       '화학', '통신', '건설', '유통/소비', '에너지',
                       '항공/물류', '기타']
        selected_sectors = st.multiselect(
            "🏭 섹터 선택 (미선택 시 전체)", all_sectors,
            placeholder="전체 섹터 스캔")
        if not selected_sectors:
            selected_sectors = ['전체']

        # 💾 조건 저장 버튼 (슬라이더 값 확정 후)
        if _sv2.button("💾 조건 저장", use_container_width=True, key="scr_save"):
            _filter_data = {
                'min_score': min_score, 'max_rsi': max_rsi,
                'max_pos_pct': max_pos_pct,
            }
            if _ctrl is not None:
                try:
                    import datetime as _dt
                    _ctrl.set('kr_screener_filter',
                              json.dumps(_filter_data, ensure_ascii=False),
                              expires=_dt.datetime.now() + _dt.timedelta(days=365))
                except Exception:
                    pass
            st.toast("✅ 조건 저장 완료!", icon="💾")

    n_scan = sum(
        1 for info in SCREEN_UNIVERSE.values()
        if ('전체' in selected_sectors or info[1] in selected_sectors)
        and info[2] in selected_tiers
    )
    scan_btn = st.button(
        f"🔍 스캔 시작  ({n_scan}개 종목)",
        type="primary", use_container_width=True)

    if 'screen_results' not in st.session_state:
        st.session_state.screen_results = None

    if scan_btn:
        params = (min_score, max_rsi, max_pos_pct,
                  tuple(sorted(selected_sectors)),
                  tuple(sorted(selected_tiers)))
        est = max(30, n_scan // 3)
        with st.spinner(f"🔄 {n_scan}개 종목 스캔 중... (약 {est}초 소요)"):
            results = run_screen(*params)
        st.session_state.screen_results = results

    results = st.session_state.screen_results
    if results is None:
        st.info("조건을 설정하고 **🔍 스캔 시작** 버튼을 눌러주세요.\n\n"
                "💡 기본 조건: 신호 65점↑ · RSI 60↓ · 52주 위치 55%↓")
        return

    if not results:
        st.warning("조건에 맞는 종목이 없어요. 조건을 완화해보세요.")
        return

    st.success(f"✅ **{len(results)}개** 종목 발견!")

    for i, r in enumerate(results):
        up    = r['day_chg'] >= 0
        arrow = '▲' if up else '▼'
        pc    = '#C0392B' if up else '#1A5FAC'
        loss  = round((r['buy_mid'] - r['stop'])  / r['buy_mid'] * 100, 1) if r['buy_mid'] else 0
        gain  = round((r['tgt1']   - r['buy_mid'])/ r['buy_mid'] * 100, 1) if r['buy_mid'] else 0
        tier  = r.get('tier', '중')
        tc    = _TIER_COLOR.get(tier, '#888')
        tbg   = _TIER_BG.get(tier, 'rgba(136,136,136,0.1)')
        tlbl  = _TIER_LABEL.get(tier, tier)

        with st.container():
            rc1, rc2, rc3, rc4 = st.columns([3, 3, 3, 1])

            with rc1:
                st.markdown(
                    f"<div style='font-size:15px;font-weight:800'>"
                    f"{i+1}위 {r['emoji']} {r['name']}</div>"
                    f"<div class='app-label'>"
                    f"<span style='background:{tbg};color:{tc};border-radius:4px;"
                    f"padding:1px 6px;font-size:11px;font-weight:700'>{tlbl}</span>"
                    f"&nbsp;{r['sector']} · {r['code']}</div>",
                    unsafe_allow_html=True)
                st.markdown(
                    f"<span style='color:{pc};font-weight:700'>"
                    f"{r['price']:,}원 {arrow}{abs(r['day_chg']):.2f}%</span>",
                    unsafe_allow_html=True)

            with rc2:
                st.markdown(
                    f"<div class='app-label' style='margin-bottom:4px'>신호 점수</div>"
                    f"<div style='font-size:22px;font-weight:900;color:#1D9E75'>{r['score']}</div>"
                    f"<div class='app-label'>{r['label']}</div>",
                    unsafe_allow_html=True)

            with rc3:
                rsi_c = ('#1D9E75' if r['rsi'] and r['rsi'] < 40
                         else '#E24B4A' if r['rsi'] and r['rsi'] > 65
                         else 'var(--text-label)')
                st.markdown(
                    f"<div class='app-muted' style='line-height:1.9'>"
                    f"RSI: <b style='color:{rsi_c}'>{r['rsi']}</b> · "
                    f"52주: <b>{r['pos_pct']:.0f}%</b><br>"
                    f"매수가: <b>{r['buy_mid']:,}원</b><br>"
                    f"손절: <b style='color:#E24B4A'>-{loss}%</b> · "
                    f"목표: <b style='color:#1D9E75'>+{gain}%</b> · "
                    f"R:R=1:{r['rr']}"
                    f"</div>",
                    unsafe_allow_html=True)

            with rc4:
                st.markdown("<div style='padding-top:6px'>", unsafe_allow_html=True)
                if st.button("📊 분석", key=f"scr_{r['code']}", use_container_width=True):
                    st.session_state['auto_code'] = r['code']
                    st.session_state['auto_name'] = r['name']
                    st.session_state['go_analysis'] = True
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            st.divider()

    st.caption(f"⏱ 결과는 1시간 캐시됩니다. 새로 스캔하려면 버튼을 다시 눌러주세요.")

    # ── TOP-5 추천 (Recommender) ──────────────────────────────────────
    if results and _QE:
        st.divider()
        _regime_scr = get_kospi_regime()
        top5 = Recommender.get_top_n(results, _regime_scr, n=5, min_rr=1.5)
        _render_top5(top5, _regime_scr)


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    init_watchlist()
    init_portfolio()
    init_kakao()
    handle_kakao_callback()
    render_sidebar()

    st.markdown("## 📈 한국 주식 분석기")
    st.caption("실시간 데이터 기반 · 기술지표 + 수급 분석 · 투자 판단은 본인 책임")

    # KOSPI 시장 상태 배지
    if _QE:
        _regime_main = get_kospi_regime()
        if _regime_main:
            _render_regime_badge(_regime_main)

    st.divider()

    # 스크리너/포트폴리오 📊 버튼 → 종목 분석 탭으로 JS 자동 전환
    go_analysis = st.session_state.pop('go_analysis', False)

    tab_analysis, tab_portfolio, tab_screen = st.tabs(["📊 종목 분석", "💼 포트폴리오", "🔍 스크리너"])

    if go_analysis:
        import streamlit.components.v1 as components
        components.html("""
        <script>
            setTimeout(function() {
                var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                if (tabs && tabs.length > 0) tabs[0].click();
            }, 300);
        </script>
        """, height=0)

    # ── 종목 분석 탭 ─────────────────────────────────────────────────────────
    with tab_analysis:
        krx = load_krx_stocks()
        auto_code = st.session_state.pop('auto_code', None)
        auto_name = st.session_state.pop('auto_name', None)

        # ★ value= 파라미터 대신 session_state 직접 설정
        #   → rerun 시 검색창이 리셋되지 않아 AI 채팅이 유지됨
        if auto_code:
            st.session_state['search_input'] = auto_code

        query = st.text_input(
            "🔍 종목명 또는 코드 검색",
            placeholder="예: 삼성전자 / 005930 / SK하이닉스",
            key="search_input",
        )

        selected_code, selected_name = None, None
        if query.strip():
            q = query.strip()
            if q.isdigit() and len(q) == 6:
                selected_code = q
                row = krx[krx['Code'] == q]
                selected_name = (row['Name'].values[0] if not row.empty
                                 else KNOWN_NAMES.get(q, f'종목 {q}'))
            else:
                matches = search_stocks(krx, q)
                if not matches.empty:
                    options = {f"{r['Name']}  ({r['Code']})": (r['Code'], r['Name'])
                               for _, r in matches.iterrows()}
                    sel = st.selectbox("종목 선택", list(options.keys()), key="stock_select")
                    selected_code, selected_name = options[sel]
                else:
                    st.warning("검색 결과가 없습니다.")

        if auto_code and not selected_code:
            selected_code = auto_code
            selected_name = auto_name

        period_map = {"3개월": 3, "6개월": 6, "1년": 12, "2년": 24}
        cur = st.session_state.get('cur_analysis')

        if selected_code:
            col_p, col_b = st.columns([2, 1])
            with col_p:
                period_sel = st.selectbox("조회 기간", ["3개월","6개월","1년","2년"],
                                          index=2, key="period_sel")
            with col_b:
                st.write("")
                analyze = st.button("📊 분석하기", use_container_width=True, type="primary")

            # 분석 실행: 버튼 or 사이드바 자동실행 → cur_analysis 저장
            if analyze or auto_code:
                st.session_state['cur_analysis'] = {
                    'code':   selected_code,
                    'name':   selected_name,
                    'months': period_map[period_sel],
                }
                cur = st.session_state['cur_analysis']

        # ★ 분석 표시 조건: cur_analysis 가 있으면 항상 표시
        #   (selected_code 와의 비교 제거 → 채팅 rerun 시 사라지지 않음)
        if cur:
            # 다른 종목으로 검색했으면 재분석 안내
            if selected_code and selected_code != cur['code']:
                st.info(f"💡 {cur['name']} 분석 중이에요. "
                        f"새 종목을 보려면 **📊 분석하기** 버튼을 눌러주세요.")
            st.divider()
            render_analysis(cur['code'], cur['name'], cur['months'])
        elif not query.strip():
            st.info("종목명 또는 코드를 검색하세요.\n\n"
                    "**예시** — `삼성전자` `SK하이닉스` `005930` `에코프로`")

    # ── 포트폴리오 탭 ─────────────────────────────────────────────────────────
    with tab_portfolio:
        render_portfolio_tab()

    # ── 스크리너 탭 ───────────────────────────────────────────────────────────
    with tab_screen:
        render_screener_tab()


if __name__ == '__main__':
    main()
