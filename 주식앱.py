"""
주식 분석기 v2.3
- 종목명/코드 검색
- 관심종목 저장
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

st.set_page_config(
    page_title="📈 주식 분석기",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
.signal-box {
    border-radius: 16px; padding: 22px 16px;
    text-align: center; margin: 8px 0 12px;
}
.signal-emoji  { font-size: 44px; line-height: 1.2; }
.signal-label  { font-size: 24px; font-weight: 800; margin: 6px 0 3px; }
.signal-score  { font-size: 13px; opacity: 0.7; }
.signal-desc   { font-size: 14px; margin-top: 8px; }
.price-bar {
    border-radius: 10px; padding: 11px 14px;
    margin: 6px 0 14px; font-size: 15px; font-weight: 600;
}
.reason-box {
    border-left: 4px solid #ddd; border-radius: 0 8px 8px 0;
    padding: 7px 12px; margin: 4px 0;
    font-size: 14px; background: #F6F6F6;
}
.zone-card {
    background: #F8F8F8; border-radius: 12px;
    padding: 14px 12px; text-align: center;
}
.zone-label { font-size: 12px; color: #888; margin-bottom: 4px; }
.zone-value { font-size: 19px; font-weight: 800; }
.zone-sub   { font-size: 12px; color: #999; margin-top: 2px; }
.flow-card  {
    border-radius: 10px; padding: 12px;
    text-align: center; margin-bottom: 4px;
}
@media (max-width: 640px) {
    .signal-label { font-size: 20px; }
    .signal-emoji { font-size: 36px; }
    .zone-value   { font-size: 15px; }
}
</style>
""", unsafe_allow_html=True)

# ── 카카오 설정 ───────────────────────────────────────────────────────────────
KAKAO_REST_KEY  = st.secrets.get("kakao_rest_key", "")
REDIRECT_URI    = "https://stock-analyzer-egqwnt22pkfgzdgxuapppyw.streamlit.app"

def kakao_auth_url():
    return (
        "https://kauth.kakao.com/oauth/authorize"
        f"?client_id={KAKAO_REST_KEY}"
        f"&redirect_uri={REDIRECT_URI}"
        "&response_type=code"
        "&scope=talk_message"
    )

def _exchange_kakao_code(code: str):
    r = requests.post("https://kauth.kakao.com/oauth/token", data={
        "grant_type":   "authorization_code",
        "client_id":    KAKAO_REST_KEY,
        "redirect_uri": REDIRECT_URI,
        "code":         code,
    }, timeout=10)
    return r.status_code, r.json()

def _refresh_kakao_token(refresh_token: str):
    r = requests.post("https://kauth.kakao.com/oauth/token", data={
        "grant_type":    "refresh_token",
        "client_id":     KAKAO_REST_KEY,
        "refresh_token": refresh_token,
    }, timeout=10)
    return r.status_code, r.json()

def _save_kakao_token(token_data: dict):
    try:
        from streamlit_js_eval import streamlit_js_eval
        data = json.dumps(token_data, ensure_ascii=False)
        cnt  = st.session_state.get('kakao_save_cnt', 0)
        streamlit_js_eval(
            js_expressions=f"localStorage.setItem('kakao_token', {json.dumps(data)}); 1",
            key=f"kakao_save_{cnt}"
        )
        st.session_state['kakao_save_cnt'] = cnt + 1
    except Exception:
        pass

def _clear_kakao_token():
    st.session_state['kakao_token'] = None
    try:
        from streamlit_js_eval import streamlit_js_eval
        cnt = st.session_state.get('kakao_save_cnt', 0)
        streamlit_js_eval(
            js_expressions="localStorage.removeItem('kakao_token'); 1",
            key=f"kakao_clear_{cnt}"
        )
        st.session_state['kakao_save_cnt'] = cnt + 1
    except Exception:
        pass

def init_kakao():
    """앱 시작 시 localStorage에서 카카오 토큰 로드"""
    if 'kakao_token'    not in st.session_state:
        st.session_state['kakao_token'] = None
    if 'kakao_loaded'   not in st.session_state:
        st.session_state['kakao_loaded'] = False
    if 'kakao_save_cnt' not in st.session_state:
        st.session_state['kakao_save_cnt'] = 0

    if not st.session_state['kakao_loaded']:
        try:
            from streamlit_js_eval import streamlit_js_eval
            raw = streamlit_js_eval(
                js_expressions="localStorage.getItem('kakao_token') || 'null'",
                key="kakao_init"
            )
            if raw is not None:
                token_data = json.loads(raw)
                if token_data:
                    st.session_state['kakao_token'] = token_data
                st.session_state['kakao_loaded'] = True
        except Exception:
            st.session_state['kakao_loaded'] = True

def handle_kakao_callback():
    """URL에 ?code= 가 있으면 토큰 교환 처리"""
    params = st.query_params
    if 'code' not in params:
        return

    code = params['code']
    status, result = _exchange_kakao_code(code)
    st.query_params.clear()

    if status == 200 and 'access_token' in result:
        token_data = {
            'access_token':  result['access_token'],
            'refresh_token': result.get('refresh_token', ''),
            'expires_at':    int(time.time()) + result.get('expires_in', 21600),
        }
        st.session_state['kakao_token']  = token_data
        st.session_state['kakao_loaded'] = True
        _save_kakao_token(token_data)
        st.toast("✅ 카카오톡 연결 완료! 분석 결과를 카카오로 받을 수 있어요.", icon="🎉")
    else:
        st.error(f"카카오 로그인 실패: {result.get('error_description', result)}")

def get_valid_kakao_token() -> str | None:
    """유효한 액세스 토큰 반환 (만료 시 자동 갱신)"""
    token_data = st.session_state.get('kakao_token')
    if not token_data:
        return None

    # 만료 5분 전이면 갱신
    if time.time() > token_data.get('expires_at', 0) - 300:
        refresh = token_data.get('refresh_token')
        if not refresh:
            _clear_kakao_token()
            return None

        status, result = _refresh_kakao_token(refresh)
        if status == 200:
            token_data['access_token'] = result['access_token']
            token_data['expires_at']   = int(time.time()) + result.get('expires_in', 21600)
            if 'refresh_token' in result:
                token_data['refresh_token'] = result['refresh_token']
            st.session_state['kakao_token'] = token_data
            _save_kakao_token(token_data)
        else:
            _clear_kakao_token()
            return None

    return token_data.get('access_token')

def send_kakao_message(access_token: str, text: str) -> tuple[bool, dict]:
    """카카오 나에게 보내기"""
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
    return r.status_code == 200, r.json()

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


# ── 종목명 사전 ───────────────────────────────────────────────────────────────
KNOWN_NAMES = {
    '005930': '삼성전자',    '000660': 'SK하이닉스',
    '035420': 'NAVER',       '035720': '카카오',
    '005380': '현대차',      '000270': '기아',
    '051910': 'LG화학',      '006400': '삼성SDI',
    '207940': '삼성바이오로직스', '068270': '셀트리온',
    '028260': '삼성물산',    '105560': 'KB금융',
    '055550': '신한지주',    '086790': '하나금융지주',
    '003550': 'LG',          '066570': 'LG전자',
    '096770': 'SK이노베이션','017670': 'SK텔레콤',
    '030200': 'KT',          '032830': '삼성생명',
    '373220': 'LG에너지솔루션','247540': '에코프로비엠',
    '086520': '에코프로',    '011200': 'HMM',
    '010140': '삼성중공업',  '042660': '한화오션',
    '329180': 'HD현대중공업','012330': '현대모비스',
    '000810': '삼성화재',    '090430': '아모레퍼시픽',
    '034730': 'SK',          '005490': 'POSCO홀딩스',
    '003490': '대한항공',    '000100': '유한양행',
    '128940': '한미약품',    '196170': '알테오젠',
    '145020': '휴젤',        '015760': '한국전력',
}

# ── KRX 전체 종목 ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400)
def load_krx_stocks():
    try:
        import FinanceDataReader as fdr
        df = fdr.StockListing('KRX')
        col_map = {}
        for c in df.columns:
            cl = c.lower().strip()
            if cl in ('code', 'symbol', '종목코드', '단축코드'): col_map[c] = 'Code'
            elif cl in ('name', '종목명', '회사명'):             col_map[c] = 'Name'
        df = df.rename(columns=col_map)
        if 'Code' not in df.columns or 'Name' not in df.columns:
            raise ValueError
        df = df[['Code', 'Name']].copy()
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        return df[df['Code'].str.match(r'^\d{6}$')].drop_duplicates('Code').reset_index(drop=True)
    except Exception:
        return pd.DataFrame(list(KNOWN_NAMES.items()), columns=['Code', 'Name'])


def search_stocks(krx, query):
    q = query.strip()
    if not q:
        return pd.DataFrame(columns=['Code', 'Name'])
    mask = krx['Name'].str.contains(q, na=False, case=False) | krx['Code'].str.contains(q, na=False)
    return krx[mask].head(12)


# ── 관심종목 ──────────────────────────────────────────────────────────────────
def init_watchlist():
    if 'watchlist'    not in st.session_state: st.session_state.watchlist    = []
    if 'wl_loaded'    not in st.session_state: st.session_state.wl_loaded    = False
    if 'wl_save_cnt'  not in st.session_state: st.session_state.wl_save_cnt  = 0

    if not st.session_state.wl_loaded:
        try:
            from streamlit_js_eval import streamlit_js_eval
            raw = streamlit_js_eval(
                js_expressions="localStorage.getItem('kr_watchlist') || '[]'",
                key="wl_init"
            )
            if raw is not None:
                st.session_state.watchlist = json.loads(raw)
                st.session_state.wl_loaded = True
        except Exception:
            st.session_state.wl_loaded = True


def _save_watchlist():
    try:
        from streamlit_js_eval import streamlit_js_eval
        data = json.dumps(st.session_state.watchlist, ensure_ascii=False)
        cnt  = st.session_state.wl_save_cnt
        streamlit_js_eval(
            js_expressions=f"localStorage.setItem('kr_watchlist', {json.dumps(data)}); 1",
            key=f"wl_save_{cnt}"
        )
        st.session_state.wl_save_cnt += 1
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


# ── 사이드바 ──────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        # 관심종목
        st.markdown("## ⭐ 관심종목")
        wl = st.session_state.get('watchlist', [])
        if not wl:
            st.caption("아직 추가된 종목이 없어요.\n분석 후 ⭐ 버튼으로 추가하세요.")
        else:
            for item in wl:
                c1, c2 = st.columns([5, 1])
                with c1:
                    if st.button(f"📊 {item['name']}", key=f"wl_btn_{item['code']}",
                                 use_container_width=True):
                        st.session_state['auto_code'] = item['code']
                        st.session_state['auto_name'] = item['name']
                        st.rerun()
                with c2:
                    if st.button("✕", key=f"wl_del_{item['code']}"):
                        remove_from_watchlist(item['code']); st.rerun()

        # 카카오톡 연결
        st.divider()
        st.markdown("### 📱 카카오톡 알림")
        kakao_token = st.session_state.get('kakao_token')
        if kakao_token:
            st.success("✅ 카카오 연결됨")
            if st.button("연결 해제", key="kakao_disconnect", use_container_width=True):
                _clear_kakao_token(); st.rerun()
        else:
            if KAKAO_REST_KEY:
                url = kakao_auth_url()
                st.markdown(
                    f'<a href="{url}" target="_top" style="'
                    'display:block;text-align:center;text-decoration:none;'
                    'background:#FEE500;border-radius:8px;padding:10px 0;'
                    'font-weight:700;font-size:14px;color:#191919;cursor:pointer;'
                    'margin:4px 0">'
                    '🔗 카카오 로그인</a>',
                    unsafe_allow_html=True,
                )
                st.caption("위 버튼 클릭 → 카카오 로그인 → 앱 자동 복귀")
            else:
                st.warning("Secrets에 kakao_rest_key를\n설정해주세요")

        st.divider()
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
                }
        except Exception: pass
    return {}


@st.cache_data(ttl=3600)
def get_investor_flow(code, days=20):
    from datetime import datetime, timedelta
    try:
        from pykrx import stock as pstock
        end = datetime.today(); start = end - timedelta(days=days * 2 + 10)
        df = pstock.get_market_trading_value_by_date(
            start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), code)
        if df is None or df.empty: return None
        return df.tail(days)
    except Exception: return None


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
    last = df['Close'].iloc[-1]
    bb_lower = df['BB_lower'].iloc[-1]; bb_upper = df['BB_upper'].iloc[-1]
    ma20 = df['MA20'].iloc[-1]; rsi = df['RSI'].iloc[-1]
    w52_low  = info.get('52w_low')  or df['Low'].min()
    w52_high = info.get('52w_high') or df['High'].max()
    buy_low = max(bb_lower, w52_low * 1.03)
    buy_high = min(ma20, last * 0.99)
    if buy_high <= buy_low: buy_high = buy_low * 1.05
    buy_mid = (buy_low + buy_high) / 2
    stop = round(buy_mid * 0.93 / 100) * 100
    tgt1 = round(bb_upper / 100) * 100
    tgt2 = round(w52_high * 0.97 / 100) * 100
    risk = buy_mid - stop
    rr   = round((tgt1 - buy_mid) / risk, 1) if risk > 0 else 0
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
        'ma20': ma20, 'ma60': df['MA60'].iloc[-1],
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


def price_position(last, z):
    if last < z['stop']:     return ('🔴', '손절 구간 아래입니다 — 보유 중이라면 손절 고려',              '#FEF0F0', '#E24B4A')
    if last <= z['buy_low']: return ('🎯', '매수 구간에 접근 중 — 분할 매수 고려',                       '#E8F8F2', '#1D9E75')
    if last <= z['buy_high']:return ('✅', '현재가가 매수 구간 안에 있습니다!',                            '#E8F8F2', '#1D9E75')
    if last <= z['tgt1']:    return ('🟡', '매수 구간보다 높습니다 — 눌림목(하락 후 반등) 기다리세요',     '#FFF8E8', '#D4870E')
    return                          ('🏆', '단기 목표가 도달 구간 — 보유 중이라면 분할 익절 고려',         '#FFF9E6', '#B8860B')


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
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.58,0.21,0.21], vertical_spacing=0.04,
                        subplot_titles=('주가 (캔들차트)','RSI','MACD'))
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
    fig.update_layout(height=580, paper_bgcolor='white', plot_bgcolor='#FAFAF9',
                      legend=dict(orientation='h', y=1.02, x=1, xanchor='right', font=dict(size=11)),
                      xaxis_rangeslider_visible=False, hovermode='x unified',
                      margin=dict(l=50, r=90, t=36, b=24), font=dict(size=11))
    fig.update_xaxes(showgrid=True, gridcolor='#EEE', gridwidth=0.5)
    fig.update_yaxes(showgrid=True, gridcolor='#EEE', tickformat=',')
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    return fig


def render_investor_flow(flow_df):
    import plotly.graph_objects as go
    if flow_df is None or flow_df.empty:
        st.caption("수급 데이터를 가져올 수 없습니다."); return
    foreign_col = next((c for c in flow_df.columns if '외국인' in c), None)
    inst_col    = next((c for c in flow_df.columns if '기관' in c and '합계' in c), None)
    indiv_col   = next((c for c in flow_df.columns if '개인' in c), None)
    if not foreign_col and not inst_col:
        st.caption("수급 컬럼을 찾을 수 없습니다."); return
    r5 = flow_df.tail(5)
    cards = [(n, c) for n, c in [('외국인', foreign_col), ('기관', inst_col), ('개인', indiv_col)] if c]
    cols = st.columns(len(cards))
    for i, (name, col) in enumerate(cards):
        val = r5[col].sum(); color = '#1D9E75' if val >= 0 else '#E24B4A'
        trend = '▲ 순매수' if val >= 0 else '▼ 순매도'
        amount = f"+{val/1e8:.0f}억" if val >= 0 else f"-{abs(val)/1e8:.0f}억"
        with cols[i]:
            st.markdown(
                f"<div class='flow-card' style='background:#F8F8F8;border-top:3px solid {color}'>"
                f"<div style='font-size:12px;color:#888'>{name} (5일)</div>"
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


# ── 분석 결과 ─────────────────────────────────────────────────────────────────
def render_analysis(code, name, months):
    with st.spinner(f'{name} 데이터 수집 중...'):
        df_raw   = get_stock_data(code, months)
        info     = get_stock_info(code)
        flow_df  = get_investor_flow(code)
        earnings = get_quarterly_earnings(code)

    if df_raw is None or df_raw.empty:
        st.error("데이터를 가져올 수 없습니다. 종목코드를 다시 확인해주세요."); return

    df  = calc_indicators(df_raw)
    z   = calc_zones(df, info)
    sig = calc_signal(df, z, flow_df)
    sup, res = find_sr(df)

    # 종목 헤더 + 버튼들
    chg_col = '#E24B4A' if z['day_chg'] >= 0 else '#185FA5'
    arrow   = '▲' if z['day_chg'] >= 0 else '▼'
    h_col, wl_col, kk_col = st.columns([4, 1, 1])
    with h_col:
        st.markdown(
            f"### {name} <span style='color:#999;font-size:15px'>({code})</span><br>"
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
                        # 토큰 만료 에러 처리
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
    st.markdown(
        f"<div class='signal-box' style='background:{s['bg']};border:2px solid {s['color']}55'>"
        f"<div class='signal-emoji'>{s['emoji']}</div>"
        f"<div class='signal-label' style='color:{s['color']}'>{s['label']}</div>"
        f"<div class='signal-score' style='color:{s['color']}'>종합 점수 {s['score']}/100 (기술지표 + 수급)</div>"
        f"<div class='signal-desc'>{s['desc']}</div></div>", unsafe_allow_html=True)

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
        st.markdown(
            f"<div class='zone-card' style='border-top:4px solid #534AB7'>"
            f"<div class='zone-label'>🎯 단기 목표가</div>"
            f"<div class='zone-value' style='color:#534AB7'>{int(z['tgt1']):,}원</div>"
            f"<div class='zone-sub'>매수가 대비 +{t1p:.1f}% · 볼린저 상단</div></div>",
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
        f"<div style='margin:12px 0 4px;font-size:13px;color:#666'>"
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

    st.markdown("#### 💰 기관/외국인 수급 현황 (최근 20일)")
    render_investor_flow(flow_df)

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

    st.markdown("#### 📈 주가 차트")
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

    with st.expander("📊 분기 실적 추이 (최근 4분기)"):
        render_quarterly_earnings(earnings)

    if any([info.get('per'), info.get('pbr'), info.get('market_cap')]):
        with st.expander("🏢 기업 기본 정보"):
            ic1, ic2 = st.columns(2)
            cap = info.get('market_cap')
            with ic1:
                if cap: st.metric("시가총액", f"{cap/1e12:.1f}조원" if cap>=1e12 else f"{cap/1e8:.0f}억원")
                if info.get('per'): st.metric("PER", f"{info['per']:.1f}배")
            with ic2:
                if info.get('pbr'): st.metric("PBR", f"{info['pbr']:.2f}배")
                if info.get('roe'): st.metric("ROE", f"{info['roe']*100:.1f}%")
            if info.get('sector') and info['sector'] != '-': st.caption(f"섹터: {info['sector']}")
            if info.get('dividend'): st.caption(f"배당수익률: {info['dividend']*100:.2f}%")

    st.divider()
    st.caption("⚠️ **투자 주의사항** — 본 분석은 기술적 지표 기반 참고 정보이며 투자 권유가 아닙니다. 모든 투자 판단과 책임은 투자자 본인에게 있습니다.")


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    init_watchlist()
    init_kakao()
    handle_kakao_callback()   # ← URL에 ?code= 있으면 토큰 교환
    render_sidebar()

    st.markdown("## 📈 한국 주식 분석기")
    st.caption("실시간 데이터 기반 · 기술지표 + 수급 분석 · 투자 판단은 본인 책임")
    st.divider()

    krx = load_krx_stocks()
    auto_code = st.session_state.pop('auto_code', None)
    auto_name = st.session_state.pop('auto_name', None)

    query = st.text_input(
        "🔍 종목명 또는 코드 검색",
        value=auto_code or '',
        placeholder="예: 삼성전자 / 005930 / SK하이닉스",
        key="search_input",
    )

    selected_code, selected_name = None, None
    if query.strip():
        q = query.strip()
        if q.isdigit() and len(q) == 6:
            selected_code = q
            row = krx[krx['Code'] == q]
            selected_name = row['Name'].values[0] if not row.empty else KNOWN_NAMES.get(q, f'종목 {q}')
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
        selected_code = auto_code; selected_name = auto_name

    if selected_code:
        col_p, col_b = st.columns([2, 1])
        with col_p:
            period_sel = st.selectbox("조회 기간", ["3개월","6개월","1년","2년"],
                                      index=2, key="period_sel")
        with col_b:
            st.write("")
            analyze = st.button("📊 분석하기", use_container_width=True, type="primary")
        if analyze or auto_code:
            period_map = {"3개월":3,"6개월":6,"1년":12,"2년":24}
            st.divider()
            render_analysis(selected_code, selected_name, period_map[period_sel])
    else:
        if not query.strip():
            st.info("종목명 또는 코드를 검색하세요.\n\n**예시** — `삼성전자` `SK하이닉스` `005930` `에코프로`")


if __name__ == '__main__':
    main()
