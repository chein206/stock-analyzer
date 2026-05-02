"""
페이지 설정 + CSS 주입.
inject_styles() 를 앱 최상단에서 한 번 호출.
"""
import streamlit as st


def inject_styles():
    st.markdown("""
<style>
/* ── CSS 변수: 라이트/다크 자동 전환 ─────────────────────────────────────── */
:root {
    --card-bg:      #F8F8F8;
    --card-bg2:     #F4F4F4;
    --card-bg3:     #F6F6F6;
    --card-border:  #E8E8E8;
    --text-muted:   #888888;
    --text-sub:     #999999;
    --text-label:   #666666;
    --divider:      #DDDDDD;
    --summary-bg:   #F8F8F8;
}
[data-theme="dark"] {
    --card-bg:      #262730;
    --card-bg2:     #1E1E2E;
    --card-bg3:     #2D2D3D;
    --card-border:  #3A3A4A;
    --text-muted:   #AAAAAA;
    --text-sub:     #888888;
    --text-label:   #BBBBBB;
    --divider:      #444455;
    --summary-bg:   #262730;
}

html, body, [class*="css"] {
    font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}

/* ── 신호 박스 ────────────────────────────────────────────────────────────── */
.signal-box {
    border-radius: 16px; padding: 22px 16px;
    text-align: center; margin: 8px 0 12px;
}
.signal-emoji  { font-size: 44px; line-height: 1.2; }
.signal-label  { font-size: 24px; font-weight: 800; margin: 6px 0 3px; }
.signal-score  { font-size: 13px; opacity: 0.75; }
.signal-desc   { font-size: 14px; margin-top: 8px; word-break: keep-all; line-height: 1.7; }

/* ── 가격 바 ──────────────────────────────────────────────────────────────── */
.price-bar {
    border-radius: 10px; padding: 11px 14px;
    margin: 6px 0 14px; font-size: 15px; font-weight: 600;
}

/* ── 분석 근거 ────────────────────────────────────────────────────────────── */
.reason-box {
    border-left: 4px solid var(--divider);
    border-radius: 0 8px 8px 0;
    padding: 7px 12px; margin: 4px 0;
    font-size: 14px;
    background: var(--card-bg3);
    color: inherit;
    word-break: keep-all; line-height: 1.6;
}

/* ── 매매 가격 카드 ───────────────────────────────────────────────────────── */
.zone-card {
    background: var(--card-bg); border-radius: 12px;
    padding: 14px 12px; text-align: center;
    word-break: keep-all;
}
.zone-label { font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
.zone-value { font-size: 19px; font-weight: 800; }
.zone-sub   { font-size: 12px; color: var(--text-sub);   margin-top: 2px; }

/* ── 수급 카드 ────────────────────────────────────────────────────────────── */
.flow-card {
    border-radius: 10px; padding: 12px;
    text-align: center; margin-bottom: 4px;
    background: var(--card-bg);
}

/* ── 사이드바 미니 카드 ───────────────────────────────────────────────────── */
.mini-card {
    background: var(--card-bg2); border-radius: 10px;
    padding: 8px 10px; margin: 4px 0 2px;
}

/* ── 공통 카드 (포트폴리오·스크리너) ─────────────────────────────────────── */
.app-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 14px; padding: 16px 20px; margin-bottom: 10px;
}
.app-label { font-size: 12px; color: var(--text-muted); }
.app-sub   { font-size: 12px; color: var(--text-sub); }
.app-muted { color: var(--text-muted); font-size: 13px; }

/* ── 헤더 영역 작은 버튼 ─────────────────────────────────────────────────── */
.small-btn-area .stButton > button {
    padding: 4px 8px !important;
    font-size: 12px !important;
    min-height: 0 !important;
    height: 32px !important;
    line-height: 1.2 !important;
}

@media (max-width: 640px) {
    .signal-label { font-size: 20px; }
    .signal-emoji { font-size: 36px; }
    .zone-value   { font-size: 15px; }
    .small-btn-area .stButton > button {
        font-size: 11px !important;
        padding: 3px 6px !important;
        height: 28px !important;
    }
}
</style>
""", unsafe_allow_html=True)
