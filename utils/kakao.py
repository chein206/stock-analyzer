"""
카카오톡 OAuth + 메시지 전송.
- init_kakao           : 쿠키에서 토큰 복원
- handle_kakao_callback: ?code= 파라미터 처리 (OAuth 콜백)
- get_valid_kakao_token: 유효 토큰 반환 (만료 전 자동 갱신)
- send_kakao_message   : 나에게 보내기
- format_kakao_message : 분석 결과 포맷팅

=======================================================================
[카카오 연결 문제 해결 기록] — 다시 건드리기 전에 반드시 읽을 것
=======================================================================

■ 문제 1: -401 "this access token does not exist"
  원인: Secrets에 kakao_access_token을 직접 저장하는 방식.
        카카오 Access Token 유효기간은 6시간이라 만료 후 항상 -401.
  해결: Secrets에서 kakao_access_token 완전 제거.
        OAuth로 받은 토큰(Access+Refresh)을 쿠키에 저장하고,
        Refresh Token(유효기간 2개월)으로 자동 갱신.

■ 문제 2: handle_kakao_callback()이 code를 자동 소비
  원인: Streamlit Cloud에서 Kakao OAuth 리디렉션 시
        st.query_params로 ?code= 값을 받아 자동 교환 시도.
        BUT CookieController 초기화가 query_params를 클리어하여
        st.query_params가 항상 비어서 교환 실패 → 에러 메시지 없이 사라짐.
        그런데 내부적으로 code는 이미 Kakao에 전송되어 소비(KOE320).
        결과적으로 자동도 안 되고 수동도 안 되는 교착 상태.
  해결: handle_kakao_callback()에서 code 교환 로직 완전 제거.
        사용자가 URL에서 code 값을 직접 복사 → 사이드바 입력란에 붙여넣기.
        _apply_kakao_auth_code()만 사용 (중복 코드 체크 없이).

■ 현재 연결 방법 (정상 작동 확인됨)
  1. 사이드바 "🔑 카카오 로그인" 클릭
  2. 새 탭 URL에서 ?code= 뒤 값 복사
  3. 사이드바 입력란에 붙여넣고 "✅ 연결하기"
  4. 토큰이 쿠키에 저장 → 앱 재시작 시 자동 복원
  5. Access Token 만료 전 Refresh Token으로 자동 갱신

■ Streamlit Cloud + CookieController 주의사항
  - st.query_params는 CookieController 초기화 후 비워질 수 있음
  - OAuth redirect 방식(리디렉션 자동 처리)은 이 환경에서 신뢰 불가
  - 반드시 수동 code 입력 방식 유지할 것

■ Secrets에 필요한 키 (카카오 관련)
  - kakao_rest_key : REST API 키 (플랫폼 키 탭의 대표 키)
  - kakao_access_token, kakao_refresh_token : 불필요, 넣지 말 것
=======================================================================
"""
import json
import time
import urllib.parse

import requests
import streamlit as st

from utils.shared import shared

# ── 설정 ──────────────────────────────────────────────────────────────────────
KAKAO_REST_KEY = st.secrets.get("kakao_rest_key", "")
REDIRECT_URI   = "https://stock-analyzer-egqwnt22pkfgzdgxuapppyw.streamlit.app"


# ── OAuth URL ─────────────────────────────────────────────────────────────────
def kakao_auth_url() -> str:
    return (
        "https://kauth.kakao.com/oauth/authorize"
        f"?client_id={KAKAO_REST_KEY}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        "&response_type=code"
        "&scope=talk_message"
    )


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────
def _exchange_kakao_code(code: str) -> tuple[int, dict]:
    """Authorization Code → Access Token + Refresh Token."""
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
    """Refresh Token으로 Access Token 갱신."""
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
    """카카오 토큰 쿠키에 저장 (60일)."""
    ctrl = shared.ctrl
    if ctrl is not None:
        try:
            ctrl.set(
                'kakao_token',
                json.dumps(token_data, ensure_ascii=False),
                max_age=60 * 60 * 24 * 60,
            )
        except Exception:
            pass


def _clear_kakao_token():
    """카카오 토큰 초기화 (세션 + 쿠키)."""
    st.session_state['kakao_token'] = None
    st.session_state.pop('_kakao_used_code', None)
    ctrl = shared.ctrl
    if ctrl is not None:
        try:
            ctrl.remove('kakao_token')
        except Exception:
            pass


# ── 공개 API ──────────────────────────────────────────────────────────────────
def init_kakao():
    """앱 시작 시 쿠키에서 카카오 토큰 복원."""
    if 'kakao_token' not in st.session_state:
        st.session_state['kakao_token'] = None

    if st.session_state['kakao_token']:
        return

    # 쿠키 로드 (세션당 1회)
    if st.session_state.get('_kakao_cookie_loaded'):
        return
    st.session_state['_kakao_cookie_loaded'] = True

    ctrl = shared.ctrl
    if ctrl is not None:
        try:
            raw = ctrl.get('kakao_token')
            if raw:
                token_data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(token_data, dict) and token_data.get('access_token'):
                    st.session_state['kakao_token'] = token_data
        except Exception:
            pass


def handle_kakao_callback():
    """URL ?code= 파라미터 기록만 (교환은 사용자가 수동으로 진행).
    자동 교환 시 code가 소비되어 수동 입력이 불가능해지는 문제 방지.
    """
    params = st.query_params.to_dict()
    # error 파라미터만 처리
    if 'error' in params:
        st.query_params.clear()
        desc = params.get('error_description', params['error'])
        st.session_state['_kakao_notify'] = ('error', f"카카오 로그인 거부: {desc}")
        return
    # code가 있으면 URL만 정리 (교환하지 않음)
    if 'code' in params:
        st.session_state['_cb_params'] = ['code — URL에서 확인 후 아래 입력란에 붙여넣기']
        st.query_params.clear()


def _apply_kakao_auth_code(auth_code: str) -> tuple[bool, str]:
    """수동으로 입력한 auth code → 토큰 교환."""
    auth_code = auth_code.strip()
    if not auth_code:
        return False, "코드를 입력해주세요."

    status, result = _exchange_kakao_code(auth_code)
    if status == 200 and result.get('access_token'):
        token_data = {
            'access_token':  result['access_token'],
            'refresh_token': result.get('refresh_token', ''),
            'expires_at':    int(time.time()) + result.get('expires_in', 21600),
        }
        st.session_state['kakao_token']          = token_data
        st.session_state['_kakao_cookie_loaded'] = True
        _save_kakao_token(token_data)
        return True, ""
    else:
        err   = (result.get('error_description') or result.get('msg')
                 or result.get('error') or f"HTTP {status}")
        debug = f"HTTP {status} | {json.dumps(result, ensure_ascii=False)[:300]}"
        st.session_state['_kakao_debug'] = debug
        return False, f"코드 교환 실패: {err}"


def get_valid_kakao_token() -> str | None:
    """유효한 액세스 토큰 반환. 만료 5분 전 자동 갱신."""
    token_data = st.session_state.get('kakao_token')
    if not token_data:
        return None

    # 만료 5분 전이면 갱신
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
    """카카오 나에게 보내기. result_code == 0 이어야 실제 성공."""
    template = {
        "object_type": "text",
        "text":        text[:2000],
        "link": {
            "web_url":        REDIRECT_URI,
            "mobile_web_url": REDIRECT_URI,
        },
        "button_title": "앱에서 자세히 보기",
    }
    try:
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
        success = (r.status_code == 200) and (body.get('result_code', -1) == 0)
        return success, body
    except Exception as e:
        return False, {"msg": str(e), "code": 0}


def format_kakao_message(code: str, name: str, z: dict, sig: dict) -> str:
    """분석 결과 카카오톡 메시지 포맷팅."""
    arrow = '▲' if z['day_chg'] >= 0 else '▼'
    reasons_lines = '\n'.join(
        f"{'✅' if s=='pos' else '⚠️' if s=='neg' else 'ℹ️'} {t}"
        for s, t in sig['reasons'][:5]
    )
    loss_p = round((z['buy_mid'] - z['stop'])   / z['buy_mid'] * 100, 1)
    gain_p = round((z['tgt1']   - z['buy_mid']) / z['buy_mid'] * 100, 1)
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
