"""
관심종목 관리.
- init_watchlist        : GitHub → 쿠키 순서로 불러오기
- _save_watchlist       : 쿠키 + GitHub 동기화
- add_to_watchlist      : 추가
- remove_from_watchlist : 삭제
- in_watchlist          : 존재 여부
- _sync_watchlist_to_github / _load_watchlist_from_github
"""
import json
import time

import streamlit as st

from utils.shared      import shared
from utils.github_sync import _gh_put_file, _gh_get_file, _GH_WL_PATH


# ── GitHub 동기화 ──────────────────────────────────────────────────────────────
def _sync_watchlist_to_github(watchlist: list) -> bool:
    pat = st.secrets.get("github_pat", "")
    if not pat:
        return False
    try:
        return _gh_put_file(_GH_WL_PATH, pat, {
            "watchlist":  watchlist,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        })
    except Exception:
        return False


def _load_watchlist_from_github() -> list:
    pat = st.secrets.get("github_pat", "")
    if not pat:
        return []
    try:
        data = _gh_get_file(_GH_WL_PATH, pat)
        if data and isinstance(data, dict):
            wl = data.get("watchlist", [])
            return wl if isinstance(wl, list) else []
        return []
    except Exception:
        return []


# ── 공개 API ──────────────────────────────────────────────────────────────────
def init_watchlist():
    """GitHub(우선) → 쿠키 순서로 관심종목 불러오기.
    쿠키는 첫 렌더링 때 비동기로 늦게 읽히므로 최대 2회 rerun 후 재시도.
    """
    if 'watchlist'    not in st.session_state: st.session_state.watchlist    = []
    if 'wl_loaded'    not in st.session_state: st.session_state.wl_loaded    = False
    if 'wl_rerun_try' not in st.session_state: st.session_state.wl_rerun_try = 0
    if '_wl_debug'    not in st.session_state: st.session_state._wl_debug    = []

    if st.session_state.wl_loaded:
        return

    loaded    = []
    gh_loaded = False
    dbg = st.session_state._wl_debug

    # 1) GitHub 우선 (크로스 기기 동기화)
    pat = st.secrets.get("github_pat", "")
    if pat:
        try:
            gh = _load_watchlist_from_github()
            if gh:
                loaded    = gh
                gh_loaded = True
                dbg.append(f"✅ GitHub 로드 성공: {len(gh)}개")
            else:
                dbg.append("⚠️ GitHub 파일 비어있음")
        except Exception as e:
            dbg.append(f"❌ GitHub 로드 실패: {e}")
    else:
        dbg.append("⚠️ github_pat 미설정")

    # 2) 쿠키 fallback
    ctrl = shared.ctrl
    if not loaded and ctrl is not None:
        try:
            raw = ctrl.get('kr_watchlist')
            if raw:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(parsed, list) and parsed:
                    loaded = parsed
                    dbg.append(f"✅ 쿠키 로드: {len(parsed)}개")
            else:
                dbg.append(f"⚠️ 쿠키 없음 (rerun #{st.session_state.wl_rerun_try})")
        except Exception as e:
            dbg.append(f"❌ 쿠키 로드 실패: {e}")

    if loaded:
        st.session_state.watchlist = loaded
        st.session_state.wl_loaded = True
        if not gh_loaded:
            ok = _sync_watchlist_to_github(loaded)
            dbg.append(f"GitHub 동기화: {'성공' if ok else '실패'}")
    elif st.session_state.wl_rerun_try < 2:
        st.session_state.wl_rerun_try += 1
        st.rerun()
    else:
        st.session_state.wl_loaded = True
        dbg.append("📭 관심종목 없음 (GitHub+쿠키 모두 비어있음)")


def _save_watchlist():
    """관심종목 쿠키 + GitHub 동기화."""
    wl        = st.session_state.watchlist
    saved_any = False

    gh_ok = _sync_watchlist_to_github(wl)
    if gh_ok:
        saved_any = True

    ctrl = shared.ctrl
    if ctrl is not None:
        try:
            ctrl.set(
                'kr_watchlist',
                json.dumps(wl, ensure_ascii=False),
                max_age=60 * 60 * 24 * 365,
            )
            saved_any = True
        except Exception:
            pass

    if not saved_any:
        st.toast("⚠️ 관심종목 저장 실패 — Secrets에 github_pat을 확인하세요", icon="⚠️")


def add_to_watchlist(code: str, name: str):
    if not any(i['code'] == code for i in st.session_state.watchlist):
        st.session_state.watchlist.append({'code': code, 'name': name})
        _save_watchlist()


def remove_from_watchlist(code: str):
    st.session_state.watchlist = [
        i for i in st.session_state.watchlist if i['code'] != code
    ]
    _save_watchlist()


def in_watchlist(code: str) -> bool:
    return any(i['code'] == code for i in st.session_state.watchlist)
