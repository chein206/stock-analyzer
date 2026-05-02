"""
종목 분석 결과 렌더링.
- render_analysis(code, name, months)
"""
import streamlit as st

from utils.shared     import shared
from utils.kis_api    import kis_get_token, kis_price
from utils.kakao      import (get_valid_kakao_token, send_kakao_message,
                               format_kakao_message, _clear_kakao_token)
from utils.stock_data import (get_stock_data, get_stock_info, get_investor_flow,
                               get_quarterly_earnings, get_kospi_regime)
from core.indicators  import (calc_indicators, calc_zones, calc_signal,
                               build_signal_detail, find_sr, price_position)
from core.watchlist   import in_watchlist, add_to_watchlist, remove_from_watchlist
from ui.chart         import (build_chart, render_investor_flow,
                               render_quarterly_earnings, _render_backtest,
                               _render_regime_badge)
from ui.ai_chat       import render_ai_chat, render_news_tab

_KIS_REAL = "https://openapi.koreainvestment.com:9443"


def render_analysis(code: str, name: str, months: int):
    with st.spinner(f'{name} 데이터 수집 중...'):
        df_raw   = get_stock_data(code, months)
        info     = get_stock_info(code)
        flow_df  = get_investor_flow(code)
        earnings = get_quarterly_earnings(code)

        # KIS 실시간 데이터로 info 보강
        _kis_data  = None
        _kis_token = kis_get_token()
        if _kis_token:
            _kis_base = st.session_state.get('_kis_base_url', _KIS_REAL)
            _kis_data = kis_price(code, _kis_token, _kis_base)
            if _kis_data:
                if _kis_data.get('per'):    info['per']      = _kis_data['per']
                if _kis_data.get('pbr'):    info['pbr']      = _kis_data['pbr']
                if _kis_data.get('w52_high'): info['52w_high'] = _kis_data['w52_high']
                if _kis_data.get('w52_low'):  info['52w_low']  = _kis_data['w52_low']
                if _kis_data.get('market_cap') and not info.get('market_cap'):
                    info['market_cap'] = _kis_data['market_cap']

    if df_raw is None or df_raw.empty:
        st.error("데이터를 가져올 수 없습니다. 종목코드를 다시 확인해주세요.")
        return

    df = calc_indicators(df_raw)
    z  = calc_zones(df, info)

    # KIS 실시간 현재가로 last·day_chg 교체
    if _kis_data and _kis_data.get('price'):
        kis_last     = _kis_data['price']
        kis_chg      = _kis_data.get('chg_pct', z['day_chg'])
        z['last']    = kis_last
        z['day_chg'] = kis_chg
        wh, wl = z['w52_high'], z['w52_low']
        if wh != wl:
            z['pos_pct'] = round((kis_last - wl) / (wh - wl) * 100, 1)

    # zones_cache 저장 (AlertMonitor용)
    if 'zones_cache' not in st.session_state:
        st.session_state['zones_cache'] = {}
    st.session_state['zones_cache'][code] = z

    # 신호 평가
    if shared.QE:
        regime = get_kospi_regime()
        sig    = shared.SignalEngine.evaluate(df, z, flow_df, regime)
    else:
        regime = None
        sig    = calc_signal(df, z, flow_df)

    sup, res = find_sr(df)

    # ── 헤더: 종목명 + 현재가 + 버튼 ─────────────────────────────────────────
    chg_col = '#E24B4A' if z['day_chg'] >= 0 else '#185FA5'
    arrow   = '▲' if z['day_chg'] >= 0 else '▼'

    data_badge = (
        "<span style='font-size:11px;background:#E8F8F2;color:#1D9E75;"
        "border-radius:4px;padding:2px 7px;margin-left:8px;font-weight:700'>"
        "🟢 실시간</span>"
        if _kis_data else
        "<span style='font-size:11px;background:var(--card-bg2);color:var(--text-muted);"
        "border-radius:4px;padding:2px 7px;margin-left:8px;'>⏱ 지연</span>"
    )

    h_col, btn_col = st.columns([5, 2])
    with h_col:
        st.markdown(
            f"### {name} <span style='color:var(--text-sub);font-size:15px'>({code})</span>"
            f"{data_badge}<br>"
            f"<span style='font-size:30px;font-weight:900'>{int(z['last']):,}원</span>"
            f"&nbsp;<span style='font-size:16px;color:{chg_col}'>{arrow} {abs(z['day_chg']):.2f}%</span>",
            unsafe_allow_html=True)
    with btn_col:
        st.markdown("<div class='small-btn-area'>", unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        with b1:
            if in_watchlist(code):
                if st.button("⭐저장됨", use_container_width=True, help="관심종목 해제"):
                    remove_from_watchlist(code)
                    st.rerun()
            else:
                if st.button("☆관심", use_container_width=True):
                    add_to_watchlist(code, name)
                    st.rerun()
        with b2:
            kakao_token = st.session_state.get('kakao_token')
            if kakao_token:
                if st.button("📱전송", use_container_width=True, type="primary"):
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
                                st.warning("카카오 토큰 만료. 사이드바에서 재연결해주세요.")
                            else:
                                st.error(f"전송 실패: {err}")
                    else:
                        st.warning("카카오 토큰 만료. 사이드바에서 재연결해주세요.")
            else:
                st.button("📱전송", use_container_width=True, disabled=True,
                          help="사이드바에서 카카오 로그인 후 사용 가능")
        st.markdown("</div>", unsafe_allow_html=True)

    # KOSPI 배지
    if regime:
        _render_regime_badge(regime)

    # ── 신호 박스 ──────────────────────────────────────────────────────────────
    sig_detail = build_signal_detail(z, sig, df)
    st.markdown(
        f"<div class='signal-box' style='background:{sig['bg']}'>"
        f"<div class='signal-emoji'>{sig['emoji']}</div>"
        f"<div class='signal-label' style='color:{sig['color']}'>{sig['label']}</div>"
        f"<div class='signal-score'>{sig['score']}/100점</div>"
        f"<div class='signal-desc'>{sig['desc']}</div>"
        f"{sig_detail}"
        f"</div>",
        unsafe_allow_html=True)

    # ── 현재가 위치 ────────────────────────────────────────────────────────────
    pos_icon, pos_msg, pos_bg, pos_color = price_position(z['last'], z)
    st.markdown(
        f"<div class='price-bar' style='background:{pos_bg};color:{pos_color}'>"
        f"{pos_icon} {pos_msg}</div>",
        unsafe_allow_html=True)

    # ── 매매 가격 카드 ─────────────────────────────────────────────────────────
    zc1, zc2, zc3, zc4, zc5 = st.columns(5)
    loss_p = round((z['buy_mid'] - z['stop'])   / z['buy_mid'] * 100, 1)
    gain_p = round((z['tgt1']   - z['buy_mid']) / z['buy_mid'] * 100, 1)

    for col, lbl, val, sub, color in [
        (zc1, '매수 구간',    f"{int(z['buy_low']):,}~{int(z['buy_high']):,}",  '원',          '#1D9E75'),
        (zc2, '추천 매수가',  f"{int(z['buy_mid']):,}",                          '원',          '#1D9E75'),
        (zc3, '손절가',       f"{int(z['stop']):,}",                             f"-{loss_p}%", '#E24B4A'),
        (zc4, '단기 목표',    f"{int(z['tgt1']):,}",                             f"+{gain_p}%", '#534AB7'),
        (zc5, 'R:R',          f"1:{z['rr']}",                                    '',             '#D4870E'),
    ]:
        with col:
            st.markdown(
                f"<div class='zone-card'>"
                f"<div class='zone-label'>{lbl}</div>"
                f"<div class='zone-value' style='color:{color}'>{val}</div>"
                f"<div class='zone-sub'>{sub}</div>"
                f"</div>",
                unsafe_allow_html=True)

    # ── 분석 근거 ──────────────────────────────────────────────────────────────
    with st.expander("📋 분석 근거 상세", expanded=False):
        for sentiment, text in sig['reasons']:
            color = ('#1D9E75' if sentiment == 'pos'
                     else '#E24B4A' if sentiment == 'neg' else '#888')
            icon  = '✅' if sentiment == 'pos' else '⚠️' if sentiment == 'neg' else 'ℹ️'
            st.markdown(
                f"<div class='reason-box' style='border-left-color:{color}'>"
                f"{icon} {text}</div>",
                unsafe_allow_html=True)

        # 지지·저항
        if sup or res:
            st.markdown("**📍 지지·저항 레벨**")
            sr_cols = st.columns(2)
            with sr_cols[0]:
                for v in reversed(sup):
                    st.markdown(
                        f"<div class='reason-box' style='border-left-color:#1D9E75'>"
                        f"🟢 지지 {int(v):,}원</div>",
                        unsafe_allow_html=True)
            with sr_cols[1]:
                for v in res:
                    st.markdown(
                        f"<div class='reason-box' style='border-left-color:#E24B4A'>"
                        f"🔴 저항 {int(v):,}원</div>",
                        unsafe_allow_html=True)

    # ── 재무 지표 ──────────────────────────────────────────────────────────────
    _per = info.get('per'); _pbr = info.get('pbr')
    _roe = info.get('roe'); _cap = info.get('market_cap')
    _div = info.get('dividend'); _div_rate = info.get('dividend_rate')
    _ex_date = info.get('ex_dividend_date'); _eps = info.get('eps')
    _has_metrics = any([_per, _pbr, _roe, _cap])
    _has_div     = any([_div, _div_rate, _ex_date])

    if _has_metrics or _has_div:
        with st.expander("🏢 기업 기본 정보 · 재무 지표 · 배당", expanded=False):
            if _has_metrics:
                st.markdown("**📊 재무 지표**")
                _fm_cols = st.columns(4)
                with _fm_cols[0]:
                    if _cap:
                        st.metric("시가총액",
                                  f"{_cap/1e12:.1f}조" if _cap >= 1e12 else f"{_cap/1e8:.0f}억")
                with _fm_cols[1]:
                    if _per:
                        _per_delta = '저평가' if _per < 10 else '적정' if _per < 20 else '고평가'
                        st.metric("PER", f"{_per:.1f}배", _per_delta,
                                  delta_color="normal" if _per < 20 else "inverse")
                with _fm_cols[2]:
                    if _pbr:
                        _pbr_delta = '저평가' if _pbr < 1 else '적정' if _pbr < 2 else '고평가'
                        st.metric("PBR", f"{_pbr:.2f}배", _pbr_delta,
                                  delta_color="normal" if _pbr < 2 else "inverse")
                with _fm_cols[3]:
                    if _roe:
                        _roe_pct   = _roe * 100
                        _roe_delta = '우수' if _roe_pct >= 15 else '양호' if _roe_pct >= 8 else '저조'
                        st.metric("ROE", f"{_roe_pct:.1f}%", _roe_delta)
                if _eps:
                    st.caption(f"EPS (주당순이익): {int(_eps):,}원")
                if info.get('sector') and info['sector'] != '-':
                    st.caption(f"섹터: {info['sector']}")

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

    # ── 탭: 차트·수급·실적·뉴스 ──────────────────────────────────────────────
    st.divider()
    _tab_chart, _tab_flow, _tab_earn, _tab_news = st.tabs(
        ["📈 차트", "💰 수급", "📊 실적", "📰 뉴스"])

    with _tab_chart:
        st.plotly_chart(build_chart(df, z), use_container_width=True)
        with st.expander("🔍 상세 기술 분석"):
            rsi_v  = z['rsi']
            ma5_v  = df['MA5'].iloc[-1]
            ma20_v = df['MA20'].iloc[-1]
            ma60_v = df['MA60'].iloc[-1]
            macd_v = df['MACD'].iloc[-1]
            macd_s = df['MACD_signal'].iloc[-1]
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
        if shared.QE:
            with st.expander("🔬 Walk-Forward 백테스트 (과거 성과 시뮬레이션)"):
                _render_backtest(code, months)

    with _tab_news:
        render_news_tab(name, code, z, sig)

    # ── AI 투자 상담 ───────────────────────────────────────────────────────────
    st.divider()
    render_ai_chat(code, name, z, sig)

    st.divider()
    st.caption("⚠️ **투자 주의사항** — 본 분석은 기술적 지표 기반 참고 정보이며 투자 권유가 아닙니다. "
               "모든 투자 판단과 책임은 투자자 본인에게 있습니다.")
