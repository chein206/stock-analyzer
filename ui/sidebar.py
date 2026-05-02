"""
사이드바 렌더링.
- render_sidebar(): 관심종목 미니 신호판, 가격 알림, 정기 알림, 카카오, KIS 상태
"""
import time
import streamlit as st

from utils.shared    import shared
from utils.kis_api   import kis_available, kis_get_token
from utils.kakao     import (get_valid_kakao_token, send_kakao_message,
                              _clear_kakao_token, _apply_kakao_auth_code,
                              kakao_auth_url, KAKAO_REST_KEY, REDIRECT_URI)
from utils.github_sync import _gh_put_file, _gh_get_file
from core.watchlist  import remove_from_watchlist
from core.alerts     import (get_quick_price, _check_price_alerts,
                              _sync_alerts_to_github, _load_alerts_from_github)


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

        # 동기화 디버그 expander
        dbg_msgs = st.session_state.get('_wl_debug', [])
        if dbg_msgs:
            with st.expander("🔧 동기화 상태", expanded=False):
                for m in dbg_msgs[-5:]:
                    st.caption(m)
                if st.button("🔄 GitHub 재동기화", key="wl_force_sync",
                             use_container_width=True):
                    st.session_state.wl_loaded    = False
                    st.session_state.wl_rerun_try = 0
                    st.session_state._wl_debug    = []
                    st.rerun()

        if not wl:
            st.markdown(
                "<div style='color:var(--text-sub);font-size:13px;padding:8px 0'>"
                "아직 추가된 종목이 없어요.<br>"
                "분석 후 ☆ 버튼으로 추가하세요.</div>",
                unsafe_allow_html=True)
        else:
            if 'price_alerts' not in st.session_state:
                st.session_state['price_alerts'] = _load_alerts_from_github()

            for item in wl:
                code  = item['code']
                name  = item['name']
                pinfo = get_quick_price(code)

                if pinfo:
                    price     = pinfo['price']
                    chg       = pinfo['chg_pct']
                    up        = chg >= 0
                    arrow     = '▲' if up else '▼'
                    dot       = '🟢' if up else '🔴'
                    p_color   = '#C0392B' if up else '#1A5FAC'
                    price_str = f"{int(price):,}원 {arrow}{abs(chg):.2f}%"
                else:
                    price     = 0
                    dot       = '⚪'
                    p_color   = '#888'
                    price_str = '데이터 없음'

                st.markdown(
                    f"<div class='mini-card'>"
                    f"<span style='font-size:14px;font-weight:700'>{dot} {name}</span>"
                    f"<br><span style='font-size:12px;color:{p_color};padding-left:4px'>{price_str}</span>"
                    f"</div>",
                    unsafe_allow_html=True)

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

                # 알림 설정 (종목별)
                _al = st.session_state['price_alerts'].get(code, {})
                _al_label = "🔔" if not _al else "🔔✅"
                with st.expander(_al_label, expanded=False):
                    _c1, _c2 = st.columns(2)
                    with _c1:
                        _tgt = st.number_input(
                            "🎯목표", min_value=0,
                            value=int(_al.get('target') or (price * 1.10 if price else 0)),
                            step=100, key=f"al_tgt_{code}", label_visibility="collapsed",
                            placeholder="목표가")
                    with _c2:
                        _stp = st.number_input(
                            "🛑손절", min_value=0,
                            value=int(_al.get('stop') or (price * 0.93 if price else 0)),
                            step=100, key=f"al_stp_{code}", label_visibility="collapsed",
                            placeholder="손절가")
                    st.caption("🎯목표가   🛑손절가")
                    _b1, _b2 = st.columns(2)
                    with _b1:
                        if st.button("저장", key=f"al_save_{code}", use_container_width=True):
                            st.session_state['price_alerts'][code] = {
                                'target':        float(_tgt) if _tgt > 0 else None,
                                'stop':          float(_stp) if _stp > 0 else None,
                                'name':          name,
                                'enabled':       True,
                                'last_triggered': '',
                            }
                            synced = _sync_alerts_to_github(st.session_state['price_alerts'])
                            st.toast(f"🔔 {name} 알림 저장{'+동기화' if synced else ''}", icon="✅")
                    with _b2:
                        if st.button("삭제", key=f"al_del_{code}", use_container_width=True):
                            st.session_state['price_alerts'].pop(code, None)
                            _sync_alerts_to_github(st.session_state['price_alerts'])
                            st.rerun()

                    if st.button("🔔 알림 테스트", key=f"al_test_{code}", use_container_width=True):
                        tok   = get_valid_kakao_token()
                        tgt_v = int(_al.get('target') or 0)
                        stp_v = int(_al.get('stop')   or 0)
                        test_msg = (
                            f"🔔 [{name}] 알림 테스트\n"
                            f"현재가 {int(price):,}원\n"
                            f"🎯 목표가: {tgt_v:,}원\n"
                            f"🛑 손절가: {stp_v:,}원\n"
                            f"✅ 알림이 정상 작동하면 이 메시지가 카카오톡으로 옵니다!"
                        )
                        if tok:
                            ok, res = send_kakao_message(tok, test_msg)
                            if ok:
                                st.toast("✅ 카카오톡 테스트 전송 성공!", icon="📱")
                            else:
                                st.error(f"전송 실패: {res.get('msg', str(res))}")
                        else:
                            st.warning("카카오톡 미연결 — 사이드바에서 연결 후 사용하세요")

        # ── 정기 알림 설정 ─────────────────────────────────────
        st.divider()
        st.markdown("### 🕐 정기 알림")
        _ns_key = '_notify_settings'
        if _ns_key not in st.session_state:
            _ns_data = _gh_get_file("data/notify_settings.json",
                                    st.secrets.get("github_pat", "")) or {}
            st.session_state[_ns_key] = {
                'enabled':        _ns_data.get('enabled', False),
                'interval_hours': _ns_data.get('interval_hours', 1),
                'start_hour':     _ns_data.get('start_hour', 8),
                'end_hour':       _ns_data.get('end_hour', 20),
            }
        _ns = st.session_state[_ns_key]

        _ns_enabled = st.toggle("관심종목 정기 현재가 전송", value=_ns['enabled'],
                                key="ns_toggle")
        if _ns_enabled:
            _c1, _c2 = st.columns(2)
            with _c1:
                _ns_start = st.number_input("시작", min_value=0, max_value=23,
                                            value=_ns['start_hour'], step=1,
                                            key="ns_start", format="%d시")
            with _c2:
                _ns_end = st.number_input("종료", min_value=0, max_value=23,
                                          value=_ns['end_hour'], step=1,
                                          key="ns_end", format="%d시")
            _ns_interval = st.select_slider(
                "전송 간격", options=[0.5, 1, 2, 3, 6],
                value=_ns['interval_hours'], key="ns_interval",
                format_func=lambda x: f"{'30분' if x == 0.5 else f'{int(x)}시간'}")
            if st.button("💾 저장", key="ns_save", use_container_width=True):
                new_ns = {
                    'enabled':        True,
                    'interval_hours': _ns_interval,
                    'start_hour':     int(_ns_start),
                    'end_hour':       int(_ns_end),
                    'updated_at':     time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                }
                st.session_state[_ns_key] = new_ns
                pat = st.secrets.get("github_pat", "")
                if pat:
                    _gh_put_file("data/notify_settings.json", pat, new_ns)
                    st.toast("✅ 정기 알림 설정 저장됨", icon="🕐")
                else:
                    st.warning("github_pat 없음 — 앱 재시작 시 초기화됩니다")
        else:
            if _ns['enabled']:
                new_ns = {**_ns, 'enabled': False,
                          'updated_at': time.strftime("%Y-%m-%dT%H:%M:%S+09:00")}
                st.session_state[_ns_key] = new_ns
                pat = st.secrets.get("github_pat", "")
                if pat:
                    _gh_put_file("data/notify_settings.json", pat, new_ns)

        # ── 카카오톡 연결 ─────────────────────────────────────
        st.divider()
        st.markdown("### 📱 카카오톡")

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
            is_static = kakao_token.get('static', False)
            src_label = 'Secrets/수동' if is_static else 'OAuth'
            st.success(f"✅ 카카오 연결됨 ({src_label})")

            tc1, tc2 = st.columns(2)
            with tc1:
                if st.button("🔔 테스트", key="kakao_test", use_container_width=True):
                    tok = get_valid_kakao_token()
                    if tok:
                        ok, res = send_kakao_message(
                            tok, "📈 주식 분석기 연결 테스트\n카카오톡 전송이 정상 작동합니다! ✅")
                        result_code = res.get('result_code', -1) if ok else -1
                        if ok and result_code == 0:
                            st.toast("카카오톡 전송 성공! 📱", icon="✅")
                        else:
                            err_code = res.get('code', result_code)
                            err_msg  = res.get('msg', str(res))
                            st.error(f"전송 실패 ({err_code}): {err_msg}")
                            st.code(str(res), language=None)
                            if err_code in (-401, -403):
                                st.caption("토큰 만료됨. 연결 해제 후 재연결해주세요.")
                    else:
                        st.warning("토큰 없음")
            with tc2:
                if st.button("연결 해제", key="kakao_disconnect", use_container_width=True):
                    _clear_kakao_token()
                    st.rerun()

        else:
            if not KAKAO_REST_KEY:
                st.warning("Streamlit Secrets에 `kakao_rest_key`를 추가하세요.")
            else:
                auth_url = kakao_auth_url()
                st.link_button("🔑 카카오 로그인", auth_url,
                               use_container_width=True)
                st.caption(
                    "로그인 후 열리는 새 탭에서\n"
                    "연결이 자동으로 완료돼요.\n\n"
                    "완료 후 **이 페이지를 새로고침(F5)**\n"
                    "하면 연결 상태가 반영됩니다."
                )

        # ── KIS API 상태 ──────────────────────────────────────
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

        # ── AlertMonitor (quant_engine) ──────────────────────
        if shared.QE and st.session_state.get('watchlist'):
            zones_cache = st.session_state.get('zones_cache', {})
            wl_with_z   = [
                {**item, 'z': zones_cache[item['code']]}
                for item in st.session_state['watchlist']
                if item['code'] in zones_cache
            ]
            if wl_with_z:
                if 'alert_cache' not in st.session_state:
                    st.session_state['alert_cache'] = {}
                alerts = shared.AlertMonitor.check(
                    wl_with_z, get_quick_price,
                    st.session_state['alert_cache'])
                for al in alerts:
                    lvl = al['level']
                    if   lvl == 'success': st.success(f"{al['emoji']} {al['msg']}")
                    elif lvl == 'error':   st.error(f"{al['emoji']} {al['msg']}")
                    elif lvl == 'warning': st.warning(f"{al['emoji']} {al['msg']}")
                    else:                  st.info(f"{al['emoji']} {al['msg']}")

        st.caption("💡 사이드바가 안 보이면\n화면 왼쪽 **>** 버튼을 누르세요")
