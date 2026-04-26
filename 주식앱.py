"""
주식 분석기 v2.0 — Streamlit 웹앱
PC + 스마트폰 모두 사용 가능
실행: streamlit run 주식앱.py
"""
import streamlit as st
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(
    page_title="📈 주식 분석기",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
.signal-box {
    border-radius: 16px;
    padding: 22px 16px;
    text-align: center;
    margin: 8px 0 12px;
}
.signal-emoji  { font-size: 44px; line-height: 1.2; }
.signal-label  { font-size: 24px; font-weight: 800; margin: 6px 0 3px; }
.signal-score  { font-size: 13px; opacity: 0.7; }
.signal-desc   { font-size: 14px; margin-top: 8px; }
.price-bar {
    border-radius: 10px;
    padding: 11px 14px;
    margin: 6px 0 14px;
    font-size: 15px;
    font-weight: 600;
}
.reason-box {
    border-left: 4px solid #ddd;
    border-radius: 0 8px 8px 0;
    padding: 7px 12px;
    margin: 4px 0;
    font-size: 14px;
    background: #F6F6F6;
}
.zone-card {
    background: #F8F8F8;
    border-radius: 12px;
    padding: 14px 12px;
    text-align: center;
    height: 100%;
}
.zone-label { font-size: 12px; color: #888; margin-bottom: 4px; }
.zone-value { font-size: 19px; font-weight: 800; }
.zone-sub   { font-size: 12px; color: #999; margin-top: 2px; }
@media (max-width: 640px) {
    .signal-label { font-size: 20px; }
    .signal-emoji { font-size: 36px; }
    .zone-value   { font-size: 16px; }
}
</style>
""", unsafe_allow_html=True)

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
    '034730': 'SK',          '011170': '롯데케미칼',
    '047050': '포스코인터내셔널','005490': 'POSCO홀딩스',
    '003490': '대한항공',    '018260': '삼성에스디에스',
    '009150': '삼성전기',    '032640': 'LG유플러스',
    '015760': '한국전력',    '034020': '두산에너빌리티',
    '000100': '유한양행',    '128940': '한미약품',
    '145020': '휴젤',        '196170': '알테오젠',
}

# ── 데이터 수집 ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=900)
def get_stock_data(code: str, months: int):
    from datetime import datetime, timedelta
    import FinanceDataReader as fdr
    import yfinance as yf

    end   = datetime.today()
    start = end - timedelta(days=months * 31)
    s, e  = start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')

    try:
        df = fdr.DataReader(code, s, e)
        if not df.empty and len(df) > 10:
            df.index   = pd.to_datetime(df.index)
            df.columns = [c.capitalize() for c in df.columns]
            if 'Volume' not in df.columns:
                df['Volume'] = 0
            return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except Exception:
        pass

    for suffix in ['.KS', '.KQ']:
        try:
            df = yf.Ticker(f'{code}{suffix}').history(start=s, end=e)
            if not df.empty and len(df) > 10:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        except Exception:
            pass

    return pd.DataFrame()


@st.cache_data(ttl=900)
def get_stock_info(code: str):
    import yfinance as yf
    for suffix in ['.KS', '.KQ']:
        try:
            raw = yf.Ticker(f'{code}{suffix}').info
            if raw and raw.get('regularMarketPrice'):
                return {
                    'per':        raw.get('trailingPE'),
                    'pbr':        raw.get('priceToBook'),
                    'roe':        raw.get('returnOnEquity'),
                    'market_cap': raw.get('marketCap'),
                    'dividend':   raw.get('dividendYield'),
                    'sector':     raw.get('sector', '-'),
                    '52w_high':   raw.get('fiftyTwoWeekHigh'),
                    '52w_low':    raw.get('fiftyTwoWeekLow'),
                }
        except Exception:
            pass
    return {}


# ── 기술지표 ─────────────────────────────────────────────────────────────────
def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    import ta
    df  = df.copy()
    c   = df['Close']

    for w, col in [(5,'MA5'),(20,'MA20'),(60,'MA60'),(120,'MA120')]:
        df[col] = c.rolling(w).mean()

    bb_mid        = c.rolling(20).mean()
    bb_std        = c.rolling(20).std()
    df['BB_mid']   = bb_mid
    df['BB_upper'] = bb_mid + 2 * bb_std
    df['BB_lower'] = bb_mid - 2 * bb_std

    try:
        df['RSI'] = ta.momentum.RSIIndicator(c, window=14).rsi()
    except Exception:
        d = c.diff()
        g = d.clip(lower=0).rolling(14).mean()
        l = (-d.clip(upper=0)).rolling(14).mean()
        df['RSI'] = 100 - 100 / (1 + g / l.replace(0, np.nan))

    try:
        m = ta.trend.MACD(c)
        df['MACD']        = m.macd()
        df['MACD_signal'] = m.macd_signal()
        df['MACD_hist']   = m.macd_diff()
    except Exception:
        e12 = c.ewm(span=12).mean()
        e26 = c.ewm(span=26).mean()
        df['MACD']        = e12 - e26
        df['MACD_signal'] = df['MACD'].ewm(span=9).mean()
        df['MACD_hist']   = df['MACD'] - df['MACD_signal']

    df['Vol_MA20'] = df['Volume'].rolling(20).mean()
    return df


# ── 매매 구간 계산 ────────────────────────────────────────────────────────────
def calc_zones(df: pd.DataFrame, info: dict) -> dict:
    last      = df['Close'].iloc[-1]
    bb_lower  = df['BB_lower'].iloc[-1]
    bb_upper  = df['BB_upper'].iloc[-1]
    ma20      = df['MA20'].iloc[-1]
    ma60      = df['MA60'].iloc[-1]
    rsi       = df['RSI'].iloc[-1]

    w52_low  = info.get('52w_low')  or df['Low'].min()
    w52_high = info.get('52w_high') or df['High'].max()

    buy_low  = max(bb_lower, w52_low * 1.03)
    buy_high = min(ma20, last * 0.99)
    if buy_high <= buy_low:
        buy_high = buy_low * 1.05
    buy_mid  = (buy_low + buy_high) / 2

    stop     = round(buy_mid * 0.93 / 100) * 100
    tgt1     = round(bb_upper / 100) * 100
    tgt2     = round(w52_high * 0.97 / 100) * 100

    risk     = buy_mid - stop
    rr       = round((tgt1 - buy_mid) / risk, 1) if risk > 0 else 0

    pos_pct  = (last - w52_low) / (w52_high - w52_low) * 100 if w52_high != w52_low else 50
    day_chg  = (last / df['Close'].iloc[-2] - 1) * 100 if len(df) > 1 else 0.0

    return {
        'last':         last,
        'day_chg':      day_chg,
        'buy_low':      round(buy_low  / 100) * 100,
        'buy_high':     round(buy_high / 100) * 100,
        'buy_mid':      round(buy_mid  / 100) * 100,
        'stop':         stop,
        'tgt1':         tgt1,
        'tgt2':         tgt2,
        'rr':           rr,
        'rsi':          round(rsi, 1) if not np.isnan(rsi) else None,
        'pos_pct':      round(pos_pct, 1),
        'w52_low':      w52_low,
        'w52_high':     w52_high,
        'ma20':         ma20,
        'ma60':         ma60,
    }


# ── 종합 신호 점수 ────────────────────────────────────────────────────────────
def calc_signal(df: pd.DataFrame, z: dict) -> dict:
    score   = 50
    reasons = []   # (sentiment, text)

    rsi      = z['rsi']
    last     = z['last']
    pos      = z['pos_pct']
    bb_lower = df['BB_lower'].iloc[-1]
    bb_upper = df['BB_upper'].iloc[-1]
    bb_range = bb_upper - bb_lower
    bb_pct   = (last - bb_lower) / bb_range if bb_range > 0 else 0.5

    macd_v   = df['MACD'].iloc[-1]
    macd_s   = df['MACD_signal'].iloc[-1]
    macd_h   = df['MACD_hist'].iloc[-1]
    macd_hp  = df['MACD_hist'].iloc[-2] if len(df) > 1 else macd_h

    ma5, ma20, ma60 = df['MA5'].iloc[-1], df['MA20'].iloc[-1], df['MA60'].iloc[-1]

    # RSI
    if rsi is not None:
        if rsi < 30:
            score += 22; reasons.append(('pos', f'RSI {rsi:.0f} — 과매도 구간, 반등 가능성 높음'))
        elif rsi < 42:
            score += 10; reasons.append(('pos', f'RSI {rsi:.0f} — 저점 근처'))
        elif rsi > 72:
            score -= 22; reasons.append(('neg', f'RSI {rsi:.0f} — 과매수, 단기 조정 가능'))
        elif rsi > 62:
            score -= 10; reasons.append(('neu', f'RSI {rsi:.0f} — 다소 높은 편'))

    # 볼린저밴드 위치
    if bb_pct < 0.10:
        score += 20; reasons.append(('pos', '볼린저밴드 하단 근처 — 기술적 저점'))
    elif bb_pct < 0.35:
        score += 10; reasons.append(('pos', '볼린저밴드 하단~중간 — 매수 고려 구간'))
    elif bb_pct > 0.90:
        score -= 20; reasons.append(('neg', '볼린저밴드 상단 근처 — 단기 고점 주의'))
    elif bb_pct > 0.70:
        score -= 8

    # MACD
    if macd_v > macd_s and macd_h > macd_hp and macd_h > 0:
        score += 15; reasons.append(('pos', 'MACD 상승 전환 — 매수 신호'))
    elif macd_v > macd_s and macd_h > macd_hp:
        score += 8;  reasons.append(('pos', 'MACD 개선 중 — 매수 신호 준비'))
    elif macd_v < macd_s and macd_h < macd_hp and macd_h < 0:
        score -= 15; reasons.append(('neg', 'MACD 하락 전환 — 매도 압력'))

    # 이동평균 배열
    if ma5 > ma20 > ma60:
        score += 10; reasons.append(('pos', '이동평균 정배열 — 상승 추세 유지'))
    elif ma5 < ma20 < ma60:
        score -= 10; reasons.append(('neg', '이동평균 역배열 — 하락 추세'))

    # 52주 위치
    if pos < 25:
        score += 15; reasons.append(('pos', f'52주 저점 근처 ({pos:.0f}%) — 역사적 저점 구간'))
    elif pos < 40:
        score += 5
    elif pos > 85:
        score -= 15; reasons.append(('neg', f'52주 고점 근처 ({pos:.0f}%) — 신중한 접근 필요'))
    elif pos > 70:
        score -= 5;  reasons.append(('neu', f'52주 상단 ({pos:.0f}%) — 다소 높은 위치'))

    score = max(5, min(95, score))

    if score >= 65:
        emoji, label = '🟢', '매수 고려'
        color, bg    = '#1D9E75', '#E8F8F2'
        desc         = '여러 지표가 매수 적합 신호를 보냅니다'
    elif score >= 45:
        emoji, label = '🟡', '관망'
        color, bg    = '#D4870E', '#FFF8E8'
        desc         = '명확한 신호가 없습니다. 조금 더 지켜보세요'
    else:
        emoji, label = '🔴', '매수 자제'
        color, bg    = '#E24B4A', '#FEF0F0'
        desc         = '고점이거나 하락 추세입니다. 신중하게 접근하세요'

    return dict(score=score, emoji=emoji, label=label,
                color=color, bg=bg, desc=desc, reasons=reasons)


# ── 현재가 위치 메시지 ────────────────────────────────────────────────────────
def price_position(last, z):
    if last < z['stop']:
        return ('🔴', '손절 구간 아래입니다 — 보유 중이라면 손절 고려', '#FEF0F0', '#E24B4A')
    if last <= z['buy_low']:
        return ('🎯', '매수 구간에 접근 중 — 분할 매수 고려', '#E8F8F2', '#1D9E75')
    if last <= z['buy_high']:
        return ('✅', '현재가가 매수 구간 안에 있습니다!', '#E8F8F2', '#1D9E75')
    if last <= z['tgt1']:
        return ('🟡', '매수 구간보다 높습니다 — 눌림목(하락 후 반등) 기다리세요', '#FFF8E8', '#D4870E')
    return ('🏆', '단기 목표가 도달 구간 — 보유 중이라면 분할 익절 고려', '#FFF9E6', '#B8860B')


# ── 차트 ─────────────────────────────────────────────────────────────────────
def build_chart(df: pd.DataFrame, z: dict):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.58, 0.21, 0.21],
        vertical_spacing=0.04,
        subplot_titles=('주가 (캔들차트)', 'RSI', 'MACD'),
    )

    # 캔들스틱
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'],
        low=df['Low'], close=df['Close'], name='주가',
        increasing_line_color='#E24B4A', decreasing_line_color='#185FA5',
        increasing_fillcolor='#E24B4A', decreasing_fillcolor='#185FA5',
    ), row=1, col=1)

    # 이동평균
    for col, color, w in [('MA20','#534AB7',1.5), ('MA60','#1D9E75',1.5)]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col], name=col,
                line=dict(color=color, width=w), opacity=0.9,
            ), row=1, col=1)

    # 볼린저밴드
    fig.add_trace(go.Scatter(
        x=df.index, y=df['BB_upper'], name='BB 상단',
        line=dict(color='#999', width=1, dash='dot'), opacity=0.5,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['BB_lower'], name='BB 하단',
        line=dict(color='#999', width=1, dash='dot'),
        fill='tonexty', fillcolor='rgba(150,150,150,0.07)', opacity=0.5,
    ), row=1, col=1)

    # 매수 구간 음영
    if z['buy_high'] > z['buy_low'] > 0:
        fig.add_hrect(y0=z['buy_low'], y1=z['buy_high'],
                      fillcolor='rgba(29,158,117,0.13)',
                      line=dict(color='rgba(29,158,117,0.35)', width=1),
                      row=1, col=1)

    # 손절 / 목표 수평선
    fig.add_hline(y=z['stop'], row=1, col=1,
                  line=dict(color='#E24B4A', width=1.8, dash='longdash'),
                  annotation_text=f"손절 {int(z['stop']):,}",
                  annotation_font=dict(size=10, color='#C03333'),
                  annotation_position='bottom right')
    fig.add_hline(y=z['tgt1'], row=1, col=1,
                  line=dict(color='#534AB7', width=1.5, dash='dot'),
                  annotation_text=f"목표 {int(z['tgt1']):,}",
                  annotation_font=dict(size=10, color='#3C3489'),
                  annotation_position='top right')

    # RSI
    fig.add_trace(go.Scatter(
        x=df.index, y=df['RSI'], name='RSI',
        line=dict(color='#534AB7', width=1.5),
    ), row=2, col=1)
    fig.add_hline(y=70, row=2, col=1, line=dict(color='#E24B4A', width=1, dash='dot'))
    fig.add_hline(y=30, row=2, col=1, line=dict(color='#1D9E75', width=1, dash='dot'))
    fig.add_hrect(y0=70, y1=100, fillcolor='rgba(226,75,74,0.06)', line_width=0, row=2, col=1)
    fig.add_hrect(y0=0,  y1=30,  fillcolor='rgba(29,158,117,0.06)', line_width=0, row=2, col=1)

    # MACD
    hist_colors = ['#E24B4A' if v >= 0 else '#185FA5' for v in df['MACD_hist'].fillna(0)]
    fig.add_trace(go.Bar(
        x=df.index, y=df['MACD_hist'], name='히스토그램',
        marker_color=hist_colors, opacity=0.55,
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD'], name='MACD',
        line=dict(color='#534AB7', width=1.5),
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD_signal'], name='Signal',
        line=dict(color='#E24B4A', width=1.5),
    ), row=3, col=1)

    fig.update_layout(
        height=580, paper_bgcolor='white', plot_bgcolor='#FAFAF9',
        legend=dict(orientation='h', y=1.02, x=1, xanchor='right', font=dict(size=11)),
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        margin=dict(l=50, r=90, t=36, b=24),
        font=dict(size=11),
    )
    fig.update_xaxes(showgrid=True, gridcolor='#EEE', gridwidth=0.5)
    fig.update_yaxes(showgrid=True, gridcolor='#EEE', tickformat=',')
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    return fig


# ── 지지/저항 탐지 ────────────────────────────────────────────────────────────
def find_sr(df: pd.DataFrame, n: int = 5):
    recent = df.tail(60)
    highs, lows = recent['High'].values, recent['Low'].values
    sup, res = [], []
    for i in range(n, len(lows) - n):
        if all(lows[i] <= lows[i-j] for j in range(1, n+1)) and \
           all(lows[i] <= lows[i+j] for j in range(1, n+1)):
            sup.append(lows[i])
    for i in range(n, len(highs) - n):
        if all(highs[i] >= highs[i-j] for j in range(1, n+1)) and \
           all(highs[i] >= highs[i+j] for j in range(1, n+1)):
            res.append(highs[i])

    def cluster(lvls, pct=0.02):
        if not lvls:
            return []
        lvls = sorted(set(lvls))
        result, grp = [lvls[0]], [lvls[0]]
        for v in lvls[1:]:
            if abs(v - grp[-1]) / grp[-1] < pct:
                grp.append(v); result[-1] = np.mean(grp)
            else:
                grp = [v]; result.append(v)
        return result

    return cluster(sup)[-3:], cluster(res)[:3]


# ── 메인 UI ───────────────────────────────────────────────────────────────────
def main():
    st.markdown("## 📈 한국 주식 분석기")
    st.caption("실시간 데이터 기반 · 매수/손절 구간 자동 계산 · 투자 판단은 본인 책임")
    st.divider()

    # ── 입력 폼 ──────────────────────────────────────────────────
    with st.form("stock_form"):
        col1, col2 = st.columns([3, 2])
        with col1:
            code = st.text_input(
                "종목코드 (6자리 숫자)",
                placeholder="예: 005930",
                max_chars=6,
            )
        with col2:
            period_sel = st.selectbox("조회 기간", ["3개월", "6개월", "1년", "2년"])
        submitted = st.form_submit_button("🔍 분석하기", use_container_width=True, type="primary")

    period_map = {"3개월": 3, "6개월": 6, "1년": 12, "2년": 24}

    if not submitted:
        st.info(
            "종목코드를 입력하고 **분석하기**를 눌러주세요.\n\n"
            "**주요 종목 코드**\n"
            "- `005930` 삼성전자   `000660` SK하이닉스\n"
            "- `035420` NAVER      `005380` 현대차\n"
            "- `086520` 에코프로   `068270` 셀트리온"
        )
        return

    if not code.isdigit() or len(code) != 6:
        st.error("6자리 숫자 종목코드를 입력해주세요. 예: 005930")
        return

    months = period_map[period_sel]
    name   = KNOWN_NAMES.get(code, f'종목 {code}')

    # ── 데이터 로딩 ──────────────────────────────────────────────
    with st.spinner(f'{name} ({code}) 데이터 불러오는 중...'):
        df_raw = get_stock_data(code, months)

    if df_raw is None or df_raw.empty:
        st.error("데이터를 가져올 수 없습니다. 종목코드를 다시 확인해주세요.")
        return

    with st.spinner("지표 계산 중..."):
        info    = get_stock_info(code)
        df      = calc_indicators(df_raw)
        z       = calc_zones(df, info)
        sig     = calc_signal(df, z)
        sup, res = find_sr(df)

    # ── 종목 헤더 ────────────────────────────────────────────────
    chg_col = '#E24B4A' if z['day_chg'] >= 0 else '#185FA5'
    arrow   = '▲' if z['day_chg'] >= 0 else '▼'
    st.markdown(
        f"### {name} "
        f"<span style='color:#999;font-size:15px'>({code})</span><br>"
        f"<span style='font-size:30px;font-weight:900'>{int(z['last']):,}원</span>"
        f"&nbsp;<span style='font-size:16px;color:{chg_col}'>"
        f"{arrow} {abs(z['day_chg']):.2f}%</span>",
        unsafe_allow_html=True,
    )

    # ── 신호 박스 ────────────────────────────────────────────────
    s = sig
    st.markdown(
        f"<div class='signal-box' style='background:{s['bg']};border:2px solid {s['color']}55'>"
        f"<div class='signal-emoji'>{s['emoji']}</div>"
        f"<div class='signal-label' style='color:{s['color']}'>{s['label']}</div>"
        f"<div class='signal-score' style='color:{s['color']}'>종합 점수 {s['score']}/100</div>"
        f"<div class='signal-desc'>{s['desc']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 현재가 위치 메시지 ───────────────────────────────────────
    icon, msg, bg, col = price_position(z['last'], z)
    st.markdown(
        f"<div class='price-bar' style='background:{bg};color:{col};border-left:4px solid {col}'>"
        f"{icon} {msg}</div>",
        unsafe_allow_html=True,
    )

    # ── 핵심 매매 가격 카드 (2×2) ────────────────────────────────
    st.markdown("#### 📌 핵심 매매 가격")

    c1, c2 = st.columns(2)
    with c1:
        buy_diff_pct = round((z['last'] - z['buy_mid']) / z['buy_mid'] * 100, 1)
        buy_diff_str = f"현재가 대비 {buy_diff_pct:+.1f}%"
        st.markdown(
            f"<div class='zone-card' style='border-top:4px solid #1D9E75'>"
            f"<div class='zone-label'>🟢 매수 구간</div>"
            f"<div class='zone-value' style='color:#1D9E75'>{int(z['buy_low']):,} ~ {int(z['buy_high']):,}원</div>"
            f"<div class='zone-sub'>추천 매수가 {int(z['buy_mid']):,}원 · {buy_diff_str}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with c2:
        stop_pct = round((z['stop'] - z['buy_mid']) / z['buy_mid'] * 100, 1)
        st.markdown(
            f"<div class='zone-card' style='border-top:4px solid #E24B4A'>"
            f"<div class='zone-label'>🔴 손절가</div>"
            f"<div class='zone-value' style='color:#E24B4A'>{int(z['stop']):,}원</div>"
            f"<div class='zone-sub'>매수가 대비 {stop_pct:.1f}% · 이 이하면 손절</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.write("")

    c3, c4 = st.columns(2)
    with c3:
        tgt1_pct = round((z['tgt1'] - z['buy_mid']) / z['buy_mid'] * 100, 1)
        st.markdown(
            f"<div class='zone-card' style='border-top:4px solid #534AB7'>"
            f"<div class='zone-label'>🎯 단기 목표가</div>"
            f"<div class='zone-value' style='color:#534AB7'>{int(z['tgt1']):,}원</div>"
            f"<div class='zone-sub'>매수가 대비 +{tgt1_pct:.1f}% · 볼린저 상단</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with c4:
        tgt2_pct = round((z['tgt2'] - z['buy_mid']) / z['buy_mid'] * 100, 1)
        st.markdown(
            f"<div class='zone-card' style='border-top:4px solid #BA7517'>"
            f"<div class='zone-label'>🏆 중기 목표가</div>"
            f"<div class='zone-value' style='color:#BA7517'>{int(z['tgt2']):,}원</div>"
            f"<div class='zone-sub'>매수가 대비 +{tgt2_pct:.1f}% · 52주 고점 부근</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # 리스크/리워드 요약
    rr = z['rr']
    rr_col = '#1D9E75' if rr >= 2 else '#D4870E' if rr >= 1 else '#E24B4A'
    rr_txt = '유리한 비율 👍' if rr >= 2 else '보통' if rr >= 1 else '불리한 비율 — 재검토 필요'
    loss_p  = round((z['buy_mid'] - z['stop'])  / z['buy_mid'] * 100, 1)
    gain_p  = round((z['tgt1']   - z['buy_mid'])/ z['buy_mid'] * 100, 1)
    st.markdown(
        f"<div style='margin:12px 0 4px;font-size:13px;color:#666'>"
        f"리스크:리워드 = <b style='color:{rr_col}'>1:{rr} ({rr_txt})</b>"
        f"&nbsp;·&nbsp; 손절 시 <b>-{loss_p}%</b>"
        f"&nbsp;·&nbsp; 목표 시 <b>+{gain_p}%</b>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 분석 근거 ────────────────────────────────────────────────
    if sig['reasons']:
        st.markdown("#### 📊 분석 근거")
        for sentiment, text in sig['reasons']:
            icon_  = '✅' if sentiment == 'pos' else '⚠️' if sentiment == 'neg' else 'ℹ️'
            border = '#1D9E75' if sentiment == 'pos' else '#E24B4A' if sentiment == 'neg' else '#999'
            st.markdown(
                f"<div class='reason-box' style='border-left-color:{border}'>{icon_} {text}</div>",
                unsafe_allow_html=True,
            )

    # ── 52주 위치 게이지 ─────────────────────────────────────────
    st.markdown("#### 📉 52주 가격 위치")
    lc, rc = st.columns(2)
    lc.caption(f"52주 저가: {int(z['w52_low']):,}원")
    rc.caption(f"52주 고가: {int(z['w52_high']):,}원")
    pos_int = max(0, min(100, int(z['pos_pct'])))
    st.progress(pos_int / 100, text=f"현재가는 52주 범위의 {z['pos_pct']:.0f}% 위치")

    # ── 지지/저항 ────────────────────────────────────────────────
    if sup or res:
        st.markdown("#### 🔲 지지선 / 저항선 (최근 60일)")
        lc2, rc2 = st.columns(2)
        with lc2:
            if sup:
                st.markdown("**지지선** (이 가격대에서 반등 가능)")
                for v in sup:
                    diff = round((z['last'] - v) / z['last'] * 100, 1)
                    st.markdown(f"- `{int(v):,}원` (현재가 대비 {diff:+.1f}%)")
        with rc2:
            if res:
                st.markdown("**저항선** (이 가격대에서 매도 압력)")
                for v in res:
                    diff = round((v - z['last']) / z['last'] * 100, 1)
                    st.markdown(f"- `{int(v):,}원` (현재가 대비 +{diff:.1f}%)")

    # ── 차트 ─────────────────────────────────────────────────────
    st.markdown("#### 📈 주가 차트")
    fig = build_chart(df, z)
    st.plotly_chart(fig, use_container_width=True)

    # ── 상세 기술 분석 (접이식) ──────────────────────────────────
    with st.expander("🔍 상세 기술 분석 보기"):
        rsi_v  = z['rsi']
        ma5_v  = df['MA5'].iloc[-1]
        ma20_v = df['MA20'].iloc[-1]
        ma60_v = df['MA60'].iloc[-1]
        macd_v = df['MACD'].iloc[-1]
        macd_s = df['MACD_signal'].iloc[-1]

        ec1, ec2 = st.columns(2)
        with ec1:
            if rsi_v:
                rsi_label = '과매도 ↗' if rsi_v < 30 else ('과매수 ↘' if rsi_v > 70 else '중립')
                st.metric("RSI (14일)", f"{rsi_v:.1f}", rsi_label)
            st.metric("MACD 신호",
                      "골든크로스 (매수)" if macd_v > macd_s else "데드크로스 (매도)")
        with ec2:
            trend = ('정배열 — 상승 추세' if ma5_v > ma20_v > ma60_v
                     else '역배열 — 하락 추세' if ma5_v < ma20_v < ma60_v
                     else '혼조')
            st.metric("이동평균 배열", trend)
            st.metric("MA20", f"{int(ma20_v):,}원")
            st.metric("MA60", f"{int(ma60_v):,}원")

    # ── 기업 정보 (접이식) ───────────────────────────────────────
    if any([info.get('per'), info.get('pbr'), info.get('market_cap')]):
        with st.expander("🏢 기업 기본 정보 보기"):
            ic1, ic2 = st.columns(2)
            cap = info.get('market_cap')
            with ic1:
                if cap:
                    cap_s = f"{cap/1e12:.1f}조원" if cap >= 1e12 else f"{cap/1e8:.0f}억원"
                    st.metric("시가총액", cap_s)
                if info.get('per'):
                    st.metric("PER", f"{info['per']:.1f}배", help="주가/순이익 — 낮을수록 저평가")
            with ic2:
                if info.get('pbr'):
                    st.metric("PBR", f"{info['pbr']:.2f}배", help="주가/순자산 — 1 이하면 자산 대비 저평가")
                if info.get('roe'):
                    st.metric("ROE", f"{info['roe']*100:.1f}%", help="자기자본이익률 — 높을수록 효율적")
            if info.get('sector') and info['sector'] != '-':
                st.caption(f"섹터: {info['sector']}")
            if info.get('dividend'):
                st.caption(f"배당수익률: {info['dividend']*100:.2f}%")

    # ── 면책 고지 ────────────────────────────────────────────────
    st.divider()
    st.caption(
        "⚠️ **투자 주의사항** — 본 분석은 기술적 지표 기반 참고 정보이며 투자 권유가 아닙니다. "
        "매수/손절 구간은 기계적 계산값으로 절대적 기준이 아닙니다. "
        "모든 투자 판단과 책임은 투자자 본인에게 있습니다."
    )


if __name__ == '__main__':
    main()
