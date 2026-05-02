"""
종목 스크리너.
- SCREEN_UNIVERSE   : 약 200종목 유니버스
- _scan_one         : 단일 종목 스캔
- run_screen        : 전체 스캔 (1시간 캐시)
- render_screener_tab: 스크리너 UI
"""
import json
import streamlit as st

from utils.shared     import shared
from utils.stock_data import get_stock_data
from core.indicators  import calc_indicators, calc_zones, calc_signal
from ui.chart         import _render_top5, _TIER_COLOR, _TIER_BG, _TIER_LABEL


# ── 스크리너 유니버스 ─────────────────────────────────────────────────────────
# 형식: 'code': ('종목명', '섹터', '등급')
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
    '161390': ('한국타이어앤테크놀로지', '자동차', '중'),
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


# ── 스캔 함수 ─────────────────────────────────────────────────────────────────
def _scan_one(args):
    """단일 종목 스캔 (멀티스레드용)."""
    code, name, sector, tier = args
    try:
        df_raw = get_stock_data(code, 3)
        if df_raw is None or df_raw.empty or len(df_raw) < 20:
            return None
        df  = calc_indicators(df_raw)
        z   = calc_zones(df, {})
        sig = shared.SignalEngine.evaluate(df, z) if shared.QE else calc_signal(df, z)
        return {
            'code':    code,
            'name':    name,
            'sector':  sector,
            'tier':    tier,
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
    """전체 유니버스 병렬 스캔 (1시간 캐시)."""
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


# ── 스크리너 UI ───────────────────────────────────────────────────────────────
def render_screener_tab():
    st.markdown("### 🔍 종목 스크리너")
    n_total = len(SCREEN_UNIVERSE)
    st.caption(f"총 {n_total}개 종목 · 신호 점수 순 정렬 · 1시간 캐시")

    # 저장된 조건 불러오기
    _saved_filter = {}
    ctrl = shared.ctrl
    if ctrl is not None:
        try:
            _raw_f = ctrl.get('kr_screener_filter')
            if _raw_f:
                _saved_filter = json.loads(_raw_f) if isinstance(_raw_f, str) else _raw_f
        except Exception:
            pass

    with st.expander("⚙️ 스캔 조건 설정", expanded=True):
        _sv1, _sv2 = st.columns(2)
        _load_clicked = _sv1.button("📂 조건 불러오기", use_container_width=True,
                                    key="scr_load", disabled=not bool(_saved_filter))

        if _load_clicked and _saved_filter:
            st.session_state['_scr_min_score']   = _saved_filter.get('min_score', 65)
            st.session_state['_scr_max_rsi']     = _saved_filter.get('max_rsi', 60)
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

        st.markdown("**📊 종목 등급**")
        tc1, tc2, tc3 = st.columns(3)
        chk_상 = tc1.checkbox('🔵 상  (대형주)', value=True)
        chk_중 = tc2.checkbox('🟡 중  (중형주)', value=True)
        chk_하 = tc3.checkbox('🟢 하  (성장주)', value=True)
        selected_tiers = [t for t, c in [('상', chk_상), ('중', chk_중), ('하', chk_하)] if c]
        if not selected_tiers:
            selected_tiers = ['상', '중', '하']

        all_sectors = ['반도체', '2차전지', '바이오', '자동차', '조선/방산',
                       'IT', '엔터', '금융', '전기전자', '철강/소재',
                       '화학', '통신', '건설', '유통/소비', '에너지',
                       '항공/물류', '기타']
        selected_sectors = st.multiselect(
            "🏭 섹터 선택 (미선택 시 전체)", all_sectors,
            placeholder="전체 섹터 스캔")
        if not selected_sectors:
            selected_sectors = ['전체']

        if _sv2.button("💾 조건 저장", use_container_width=True, key="scr_save"):
            _filter_data = {
                'min_score': min_score, 'max_rsi': max_rsi,
                'max_pos_pct': max_pos_pct,
            }
            if ctrl is not None:
                try:
                    import datetime as _dt
                    ctrl.set('kr_screener_filter',
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
        loss  = round((r['buy_mid'] - r['stop'])   / r['buy_mid'] * 100, 1) if r['buy_mid'] else 0
        gain  = round((r['tgt1']   - r['buy_mid']) / r['buy_mid'] * 100, 1) if r['buy_mid'] else 0
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
                    st.session_state['auto_code']   = r['code']
                    st.session_state['auto_name']   = r['name']
                    st.session_state['go_analysis'] = True
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            st.divider()

    st.caption("⏱ 결과는 1시간 캐시됩니다. 새로 스캔하려면 버튼을 다시 눌러주세요.")

    # TOP-5 추천 (Recommender)
    if results and shared.QE:
        from utils.stock_data import get_kospi_regime
        st.divider()
        _regime_scr = get_kospi_regime()
        top5 = shared.Recommender.get_top_n(results, _regime_scr, n=5, min_rr=1.5)
        _render_top5(top5, _regime_scr)
