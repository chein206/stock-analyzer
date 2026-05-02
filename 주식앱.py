"""
주식 분석기 v4.0 — 모듈형 분리 버전
실행: streamlit run 주식앱.py

기능별 파일 구조:
  utils/shared.py       공유 상태 (CookieController, QE 플래그)
  utils/kis_api.py      KIS Developers API
  utils/github_sync.py  GitHub Contents API (관심종목·알림 동기화)
  utils/kakao.py        카카오톡 OAuth + 메시지 전송
  utils/stock_data.py   주가 데이터 수집 (FDR / yfinance / pykrx)
  core/watchlist.py     관심종목 관리
  core/alerts.py        가격 알림 관리
  core/indicators.py    기술지표 계산 + 신호 판단
  ui/styles.py          CSS 주입
  ui/sidebar.py         사이드바 렌더링
  ui/chart.py           차트 + 백테스트 + KOSPI 배지
  ui/ai_chat.py         AI 상담 채팅
  ui/analysis.py        종목 분석 결과 렌더링
  ui/portfolio.py       포트폴리오 탭
  ui/screener.py        종목 스크리너 탭
"""
import streamlit as st
import warnings
warnings.filterwarnings('ignore')

# ── 페이지 설정 (반드시 최상단) ────────────────────────────────────────────────
st.set_page_config(
    page_title="📈 주식 분석기",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── CSS 주입 ───────────────────────────────────────────────────────────────────
from ui.styles import inject_styles
inject_styles()

# ── 카카오 콜백 파라미터 조기 캡처 ────────────────────────────────────────────
# CookieController 초기화가 query_params를 지우기 전에 먼저 저장
_qp_now = st.query_params.to_dict()
if 'code' in _qp_now:
    st.session_state.setdefault('_kakao_pending_code', _qp_now['code'])
elif 'error' in _qp_now:
    st.session_state.setdefault('_kakao_pending_error', _qp_now)

# ── 공유 상태 + CookieController ─────────────────────────────────────────────
from utils.shared import shared
try:
    from streamlit_cookies_controller import CookieController
    shared.ctrl = CookieController()   # 매 rerun마다 1번만 생성
except Exception:
    shared.ctrl = None

# ── 모듈 import ────────────────────────────────────────────────────────────────
from utils.kakao     import init_kakao, handle_kakao_callback
from utils.stock_data import load_krx_stocks, search_stocks, KNOWN_NAMES, get_kospi_regime
from core.watchlist  import init_watchlist
from ui.sidebar      import render_sidebar
from ui.analysis     import render_analysis
from ui.portfolio    import init_portfolio, render_portfolio_tab
from ui.screener     import render_screener_tab
from ui.chart        import _render_regime_badge


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    # 초기화
    init_watchlist()
    init_portfolio()
    init_kakao()
    handle_kakao_callback()
    render_sidebar()

    st.markdown("## 📈 한국 주식 분석기")
    st.caption("실시간 데이터 기반 · 기술지표 + 수급 분석 · 투자 판단은 본인 책임")

    # KOSPI 시장 상태 배지
    if shared.QE:
        _regime_main = get_kospi_regime()
        if _regime_main:
            _render_regime_badge(_regime_main)

    st.divider()

    go_analysis = st.session_state.pop('go_analysis', False)
    tab_analysis, tab_portfolio, tab_screen = st.tabs(
        ["📊 종목 분석", "💼 포트폴리오", "🔍 스크리너"])

    # 스크리너/포트폴리오 버튼 → 종목 분석 탭 자동 전환
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
        krx       = load_krx_stocks()
        auto_code = st.session_state.pop('auto_code', None)
        auto_name = st.session_state.pop('auto_name', None)

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
                row           = krx[krx['Code'] == q]
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
                period_sel = st.selectbox(
                    "조회 기간", ["3개월", "6개월", "1년", "2년"],
                    index=2, key="period_sel")
            with col_b:
                st.write("")
                analyze = st.button("📊 분석하기", use_container_width=True, type="primary")

            if analyze or auto_code:
                st.session_state['cur_analysis'] = {
                    'code':   selected_code,
                    'name':   selected_name,
                    'months': period_map[period_sel],
                }
                cur = st.session_state['cur_analysis']

        if cur:
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
