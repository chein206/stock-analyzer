"""
차트 및 시각화.
- build_chart           : 캔들+MA+BB+RSI+MACD+거래량 서브플롯
- render_investor_flow  : 기관/외국인 수급 차트
- render_quarterly_earnings: 분기 실적 차트
- _cached_backtest      : 백테스트 캐시
- _render_backtest      : 백테스트 결과 렌더링
- _render_regime_badge  : KOSPI 시장 상태 배지
- _render_top5          : TOP-5 추천 종목
"""
import streamlit as st
import pandas as pd

from utils.shared    import shared
from utils.stock_data import get_stock_data

_TIER_COLOR = {'상': '#534AB7', '중': '#D4870E', '하': '#1D9E75'}
_TIER_BG    = {
    '상': 'rgba(83,74,183,0.12)',
    '중': 'rgba(212,135,14,0.12)',
    '하': 'rgba(29,158,117,0.12)',
}
_TIER_LABEL = {'상': '상 · 대형주', '중': '중 · 중형주', '하': '하 · 성장주'}


# ── 메인 차트 ─────────────────────────────────────────────────────────────────
def build_chart(df, z):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    has_vol = 'Volume' in df.columns and df['Volume'].sum() > 0
    rows    = 4 if has_vol else 3
    heights = [0.50, 0.17, 0.17, 0.16] if has_vol else [0.58, 0.21, 0.21]
    titles  = (('주가 (캔들차트)', 'RSI', 'MACD', '거래량')
               if has_vol else ('주가 (캔들차트)', 'RSI', 'MACD'))

    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        row_heights=heights, vertical_spacing=0.03,
        subplot_titles=titles)

    # 캔들
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'],
        low=df['Low'], close=df['Close'], name='주가',
        increasing_line_color='#E24B4A', decreasing_line_color='#185FA5',
        increasing_fillcolor='#E24B4A', decreasing_fillcolor='#185FA5'),
        row=1, col=1)

    # MA
    for col, color, w in [('MA20', '#534AB7', 1.5), ('MA60', '#1D9E75', 1.5)]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col], name=col,
                line=dict(color=color, width=w), opacity=0.9), row=1, col=1)

    # 볼린저밴드
    fig.add_trace(go.Scatter(
        x=df.index, y=df['BB_upper'], name='BB 상단',
        line=dict(color='#999', width=1, dash='dot'), opacity=0.5), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['BB_lower'], name='BB 하단',
        line=dict(color='#999', width=1, dash='dot'),
        fill='tonexty', fillcolor='rgba(150,150,150,0.07)', opacity=0.5), row=1, col=1)

    # 매수구간 음영
    if z['buy_high'] > z['buy_low'] > 0:
        fig.add_hrect(y0=z['buy_low'], y1=z['buy_high'],
                      fillcolor='rgba(29,158,117,0.13)',
                      line=dict(color='rgba(29,158,117,0.35)', width=1), row=1, col=1)

    # 손절·목표 라인
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
        line=dict(color='#534AB7', width=1.5)), row=2, col=1)
    fig.add_hline(y=70, row=2, col=1, line=dict(color='#E24B4A', width=1, dash='dot'))
    fig.add_hline(y=30, row=2, col=1, line=dict(color='#1D9E75', width=1, dash='dot'))
    fig.add_hrect(y0=70, y1=100, fillcolor='rgba(226,75,74,0.06)',  line_width=0, row=2, col=1)
    fig.add_hrect(y0=0,  y1=30,  fillcolor='rgba(29,158,117,0.06)', line_width=0, row=2, col=1)

    # MACD
    hist_colors = ['#E24B4A' if v >= 0 else '#185FA5' for v in df['MACD_hist'].fillna(0)]
    fig.add_trace(go.Bar(
        x=df.index, y=df['MACD_hist'], name='히스토그램',
        marker_color=hist_colors, opacity=0.55), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD'], name='MACD',
        line=dict(color='#534AB7', width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD_signal'], name='Signal',
        line=dict(color='#E24B4A', width=1.5)), row=3, col=1)

    # 거래량
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
    fig.update_layout(
        height=chart_h, paper_bgcolor='white', plot_bgcolor='#FAFAF9',
        legend=dict(orientation='h', y=1.02, x=1, xanchor='right', font=dict(size=11)),
        xaxis_rangeslider_visible=False, hovermode='x unified',
        margin=dict(l=50, r=90, t=36, b=24), font=dict(size=11))
    fig.update_xaxes(showgrid=True, gridcolor='#EEE', gridwidth=0.5)
    fig.update_yaxes(showgrid=True, gridcolor='#EEE', tickformat=',')
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    if has_vol:
        fig.update_yaxes(tickformat='.2s', row=4, col=1)
    return fig


# ── 수급 차트 ─────────────────────────────────────────────────────────────────
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

    foreign_col = next((c for c in flow_df.columns if '외국인' in c), None)
    inst_col    = next((c for c in flow_df.columns
                        if '기관' in c and ('합계' in c or c == '기관')), None)
    indiv_col   = next((c for c in flow_df.columns if '개인' in c), None)

    if not foreign_col and not inst_col:
        st.caption(f"수급 컬럼을 인식할 수 없습니다. (컬럼: {list(flow_df.columns)})")
        return

    r5    = flow_df.tail(5)
    cards = [(n, c) for n, c in [('외국인', foreign_col), ('기관', inst_col), ('개인', indiv_col)] if c]
    cols  = st.columns(len(cards))
    for i, (name, col) in enumerate(cards):
        val    = r5[col].sum()
        color  = '#1D9E75' if val >= 0 else '#E24B4A'
        trend  = '▲ 순매수' if val >= 0 else '▼ 순매도'
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
        bar_colors = ['#1D9E75' if v >= 0 else '#E24B4A' for v in flow_df[foreign_col]]
        fig.add_trace(go.Bar(
            x=flow_df.index, y=flow_df[foreign_col] / 1e8,
            name='외국인', marker_color=bar_colors, opacity=0.85))
    if inst_col:
        inst_colors = ['#534AB7' if v >= 0 else '#A090D0' for v in flow_df[inst_col]]
        fig.add_trace(go.Bar(
            x=flow_df.index, y=flow_df[inst_col] / 1e8,
            name='기관', marker_color=inst_colors, opacity=0.6))

    fig.add_hline(y=0, line_color='#888', line_width=1)
    fig.update_layout(
        height=240, barmode='group', plot_bgcolor='#FAFAF9', paper_bgcolor='white',
        margin=dict(l=50, r=20, t=16, b=24), yaxis_title='순매수 (억원)',
        legend=dict(orientation='h', y=1.1, x=1, xanchor='right'), font=dict(size=11))
    fig.update_xaxes(showgrid=True, gridcolor='#EEE')
    fig.update_yaxes(showgrid=True, gridcolor='#EEE')
    st.plotly_chart(fig, use_container_width=True)
    st.caption("※ KRX 기준 / 양수=순매수(사는 중) / 음수=순매도(파는 중)")


# ── 실적 차트 ─────────────────────────────────────────────────────────────────
def render_quarterly_earnings(earnings):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if earnings is None or earnings.empty:
        st.caption("실적 데이터를 가져올 수 없습니다.")
        return

    rev_data = next((earnings.loc[k] for k in ['Total Revenue', 'Revenue', 'TotalRevenue']
                     if k in earnings.index), None)
    op_data  = next((earnings.loc[k] for k in ['Operating Income', 'EBIT', 'OperatingIncome']
                     if k in earnings.index), None)
    net_data = next((earnings.loc[k] for k in ['Net Income', 'NetIncome']
                     if k in earnings.index), None)

    if rev_data is None and op_data is None:
        st.caption("실적 데이터 형식을 확인할 수 없습니다.")
        return

    cols  = sorted(earnings.columns)[-4:]
    dates = [str(c)[:7] for c in cols]

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=('매출/영업이익 (억원)', '순이익 (억원)'))
    if rev_data is not None:
        vals = [rev_data[c] / 1e8 if pd.notna(rev_data[c]) else 0 for c in cols]
        fig.add_trace(go.Bar(x=dates, y=vals, name='매출',
                             marker_color='#534AB7', opacity=0.5), row=1, col=1)
    if op_data is not None:
        vals = [op_data[c] / 1e8 if pd.notna(op_data[c]) else 0 for c in cols]
        fig.add_trace(go.Bar(x=dates, y=vals, name='영업이익',
                             marker_color=['#1D9E75' if v >= 0 else '#E24B4A' for v in vals],
                             opacity=0.85), row=1, col=1)
    if net_data is not None:
        vals = [net_data[c] / 1e8 if pd.notna(net_data[c]) else 0 for c in cols]
        fig.add_trace(go.Bar(x=dates, y=vals, name='순이익',
                             marker_color=['#1D9E75' if v >= 0 else '#E24B4A' for v in vals],
                             opacity=0.85), row=1, col=2)

    fig.update_layout(
        height=280, plot_bgcolor='#FAFAF9', paper_bgcolor='white',
        margin=dict(l=40, r=20, t=36, b=24), showlegend=True, font=dict(size=11))
    fig.update_xaxes(showgrid=True, gridcolor='#EEE')
    fig.update_yaxes(showgrid=True, gridcolor='#EEE', tickformat=',')
    st.plotly_chart(fig, use_container_width=True)
    st.caption("※ Yahoo Finance 기준 · 단위: 억원 · 음수=적자")


# ── 백테스트 ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def _cached_backtest(code: str, months: int):
    """백테스트 연산 캐시 (1시간). expander 열 때마다 재실행 방지."""
    if not shared.QE:
        return None
    df_raw = get_stock_data(code, months)
    if df_raw is None or df_raw.empty or len(df_raw) < 60:
        return None
    return shared.Backtester.run(
        df_raw, initial_capital=10_000_000,
        walk_forward=len(df_raw) >= 120, oos_ratio=0.3)


def _render_backtest(code: str, months: int):
    """백테스트 결과 렌더링 (expander 안에서 호출)."""
    if not shared.QE:
        st.caption("quant_engine이 설치되지 않았습니다.")
        return

    result = _cached_backtest(code, months)
    if result is None:
        st.caption("데이터 부족으로 백테스트를 실행할 수 없습니다.")
        return

    s = result.summary()
    if not result.trades:
        st.caption("백테스트 기간 내 신호가 발생하지 않았습니다.")
        return

    m1, m2, m3, m4 = st.columns(4)
    ret = s['총 수익률 (%)']
    m1.metric("총 수익률",   f"{ret:+.1f}%")
    m2.metric("승률",        f"{s['승률 (%)']:.0f}%")
    m3.metric("MDD",         f"{s['MDD (%)']:.1f}%")
    m4.metric("Sharpe",      f"{s['Sharpe Ratio']:.2f}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("거래 횟수",   f"{s['거래 횟수']}건")
    c2.metric("Profit Factor", f"{s['Profit Factor']}")
    c3.metric("평균 수익",   f"{s['평균 수익 (%)']:+.1f}%")
    c4.metric("기댓값",      f"{s['기댓값 (%)']:+.2f}%")
    st.caption(f"📅 검증 기간: {s['검증 기간']}")

    st.info(
        "⚠️ **백테스트 주의사항** — 과거 성과가 미래를 보장하지 않습니다. "
        "Walk-Forward(OOS 30%) 방식으로 과적합을 최소화했으나 실전 수익률은 다를 수 있습니다. "
        "수수료 0.15% + 슬리피지 0.1% 포함 계산.",
        icon="ℹ️")

    if result.trades:
        with st.expander(f"📋 거래 내역 ({len(result.trades)}건)"):
            st.dataframe(result.trades_df(), use_container_width=True, hide_index=True)

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


# ── KOSPI 배지 ────────────────────────────────────────────────────────────────
def _render_regime_badge(regime: dict):
    """KOSPI 시장 상태 배지."""
    if not regime:
        return
    c        = regime['color']
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
        unsafe_allow_html=True)


# ── TOP-5 추천 ────────────────────────────────────────────────────────────────
def _render_top5(top5: list, regime: dict):
    """TOP-5 추천 종목 렌더링."""
    if not top5 or not shared.QE:
        return

    r_lbl   = regime['label']  if regime else '시장 미감지'
    r_emoji = regime['emoji']  if regime else '❓'

    st.markdown(
        f"### 🏆 AI 추천 TOP-5  "
        f"<span style='font-size:14px;color:var(--text-muted)'>({r_emoji} {r_lbl} 기준)</span>",
        unsafe_allow_html=True)
    st.caption("복합 랭킹: 신호 점수 60% + R:R 30% + 52주 위치 역수 10%")

    for i, r in enumerate(top5, 1):
        reason = shared.Recommender.reason(r, regime)
        tier   = r.get('tier', '중')
        tc     = _TIER_COLOR.get(tier, '#888')
        tbg    = _TIER_BG.get(tier, 'rgba(0,0,0,0.05)')
        tlbl   = _TIER_LABEL.get(tier, tier)
        loss   = round((r['buy_mid'] - r['stop'])   / r['buy_mid'] * 100, 1) if r['buy_mid'] else 0
        gain   = round((r['tgt1']   - r['buy_mid']) / r['buy_mid'] * 100, 1) if r['buy_mid'] else 0

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
                st.session_state['auto_code']    = r['code']
                st.session_state['auto_name']    = r['name']
                st.session_state['go_analysis']  = True
                st.rerun()
        st.divider()
