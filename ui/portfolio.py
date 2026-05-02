"""
포트폴리오 탭.
- init_portfolio      : 쿠키에서 보유 데이터 로드
- save_portfolio      : 쿠키 저장
- render_portfolio_tab: 종목별 수익률 UI
"""
import json
import streamlit as st

from utils.shared  import shared
from core.alerts   import get_quick_price


def init_portfolio():
    """쿠키에서 포트폴리오 보유 데이터 로드."""
    if 'portfolio'        not in st.session_state: st.session_state.portfolio        = {}
    if 'portfolio_loaded' not in st.session_state: st.session_state.portfolio_loaded = False

    if not st.session_state.portfolio_loaded:
        ctrl = shared.ctrl
        if ctrl is not None:
            try:
                raw = ctrl.get('kr_portfolio')
                if raw:
                    loaded = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(loaded, dict):
                        st.session_state.portfolio = loaded
            except Exception:
                pass
        st.session_state.portfolio_loaded = True


def save_portfolio():
    """포트폴리오 쿠키 저장 (1년)."""
    ctrl = shared.ctrl
    if ctrl is not None:
        try:
            ctrl.set('kr_portfolio',
                     json.dumps(st.session_state.portfolio, ensure_ascii=False),
                     max_age=60 * 60 * 24 * 365)
        except Exception:
            pass


def render_portfolio_tab():
    wl = st.session_state.get('watchlist', [])
    if not wl:
        st.info("관심종목이 없어요.\n종목 분석 후 ⭐ 버튼으로 추가하면 여기서 수익률을 확인할 수 있어요.")
        return

    holdings = st.session_state.portfolio

    # 현재가 수집
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

    # 요약 카드
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
            unsafe_allow_html=True)

    # 종목별 카드
    for r in rows:
        code, name = r['code'], r['name']
        cur_p, chg = r['cur_p'], r['chg']
        h = holdings.get(code, {})

        with st.container():
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
                    st.session_state['auto_code']   = code
                    st.session_state['auto_name']   = name
                    st.session_state['go_analysis'] = True
                    st.rerun()

            ic1, ic2, ic3, ic4 = st.columns([2, 2, 3, 1])
            with ic1:
                avg_input = st.number_input(
                    "평균단가 (원)", min_value=0, step=100, format="%d",
                    value=h.get('avg_price', 0), key=f"pt_avg_{code}")
            with ic2:
                qty_input = st.number_input(
                    "수량 (주)", min_value=0, step=1, format="%d",
                    value=h.get('qty', 0), key=f"pt_qty_{code}")
            with ic3:
                if avg_input > 0 and qty_input > 0 and cur_p:
                    invested = avg_input * qty_input
                    cur_val  = cur_p    * qty_input
                    pnl      = cur_val - invested
                    pnl_pct  = pnl / invested * 100
                    pc       = '#C0392B' if pnl >= 0 else '#1A5FAC'
                    arr      = '▲' if pnl >= 0 else '▼'
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
