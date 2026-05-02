"""
AI 투자 상담 + 뉴스 탭.
- ask_ai_advisor  : Claude API 상담 답변
- render_ai_chat  : 채팅 UI
- render_news_tab : 뉴스 + AI 요약
- _clipboard_btn  : 클립보드 복사 버튼
- _kakao_send_btn : 카카오 전송 버튼
- _scenario_card  : 시나리오 카드 렌더링
"""
import streamlit as st

from utils.kakao  import get_valid_kakao_token, send_kakao_message, _clear_kakao_token
from utils.stock_data import get_stock_news


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────
def _clipboard_btn(text: str, key: str):
    """클립보드 복사 버튼 (JavaScript, UTF-8 안전)."""
    import base64
    import streamlit.components.v1 as components

    b64 = base64.b64encode(text.encode('utf-8')).decode()
    components.html(
        f"""
        <button id="btn_{key}" onclick="
            try {{
                const raw = atob('{b64}');
                const bytes = new Uint8Array(raw.length);
                for (let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i);
                const decoded = new TextDecoder('utf-8').decode(bytes);
                navigator.clipboard.writeText(decoded).then(() => {{
                    document.getElementById('btn_{key}').textContent='✅ 복사됨!';
                    setTimeout(() => document.getElementById('btn_{key}').textContent='📋 복사', 2000);
                }});
            }} catch(e) {{
                alert('복사 실패: ' + e);
            }}
        "
        style="width:100%;padding:5px 10px;background:#F5F5F5;border:1px solid #DDD;
               border-radius:7px;cursor:pointer;font-size:13px;font-family:inherit">
        📋 복사
        </button>
        """,
        height=34,
    )


def _kakao_send_btn(text: str, code: str, name: str, z: dict, key: str):
    """카카오톡 전송 버튼."""
    if not st.session_state.get('kakao_token'):
        return
    if st.button("📱 카카오", key=f"kk_{key}", use_container_width=True):
        access_token = get_valid_kakao_token()
        if access_token:
            header   = (f"📈 {name}({code}) AI 분석\n"
                        f"현재가 {int(z['last']):,}원 | 매수가 {int(z['buy_mid']):,}원\n\n")
            full_msg = header + text
            ok, result = send_kakao_message(access_token, full_msg)
            if ok:
                st.toast("카카오톡으로 전송했어요! ✅", icon="📱")
            else:
                err = result.get('msg', str(result))
                if result.get('code') in (-401, -403):
                    _clear_kakao_token()
                    st.warning("카카오 토큰 만료. 사이드바에서 재로그인 해주세요.")
                else:
                    st.error(f"전송 실패: {err}")
        else:
            st.warning("카카오 토큰이 만료됐어요.")


def _scenario_card(text: str, code: str, name: str, z: dict, key: str):
    """AI 응답을 시각적 카드로 렌더링 (스크린샷용)."""
    arrow   = '▲' if z['day_chg'] >= 0 else '▼'
    chg_col = '#C0392B' if z['day_chg'] >= 0 else '#1A5FAC'
    st.markdown(
        f"""
        <div style='border:2px solid #534AB7;border-radius:14px;padding:20px 22px;
                    background:linear-gradient(135deg,#F8F8FF 0%,#EEF0FF 100%);
                    margin:4px 0'>
          <div style='font-size:13px;color:#888;margin-bottom:6px'>
            📸 시나리오 카드 — 스크린샷 후 공유하세요
          </div>
          <div style='font-size:17px;font-weight:800;color:#222;margin-bottom:2px'>
            📈 {name} <span style='color:#888;font-size:13px'>({code})</span>
          </div>
          <div style='font-size:14px;color:{chg_col};margin-bottom:12px'>
            현재가 {int(z['last']):,}원 {arrow}{abs(z['day_chg']):.2f}% &nbsp;|&nbsp;
            매수가 {int(z['buy_mid']):,}원 &nbsp;|&nbsp;
            손절 {int(z['stop']):,}원 &nbsp;|&nbsp;
            목표 {int(z['tgt1']):,}원
          </div>
          <hr style='border:none;border-top:1px solid #DDD;margin:8px 0'>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(text)
    st.caption("📱 위 내용을 스크린샷해서 카카오톡으로 공유하세요")


# ── AI 상담 ───────────────────────────────────────────────────────────────────
def ask_ai_advisor(question: str, code: str, name: str, z: dict, sig: dict,
                   history: list) -> str:
    """Claude API로 맞춤 투자 상담 답변 생성."""
    api_key = st.secrets.get("anthropic_api_key", "")
    if not api_key:
        return "⚠️ Streamlit Secrets에 `anthropic_api_key`를 추가해 주세요."

    import anthropic

    reasons_txt = "\n".join(
        f"  {'✅' if s=='pos' else '⚠️' if s=='neg' else 'ℹ️'} {t}"
        for s, t in sig['reasons']
    )

    system = f"""당신은 친근하고 실용적인 한국 주식 투자 상담 AI입니다.
사용자는 주린이(초보 투자자)일 수 있으니 어려운 용어는 쉽게 풀어서 설명하세요.

━━━ 현재 분석 중인 종목 ━━━
종목: {name} ({code})
현재가: {int(z['last']):,}원  (전일 대비 {z['day_chg']:+.2f}%)
종합 신호: {sig['emoji']} {sig['label']}  (점수 {sig['score']}/100)

📌 매매 가격대
  매수 구간: {int(z['buy_low']):,} ~ {int(z['buy_high']):,}원
  추천 매수가: {int(z['buy_mid']):,}원
  손절가: {int(z['stop']):,}원
  단기 목표가: {int(z['tgt1']):,}원
  중기 목표가: {int(z['tgt2']):,}원
  리스크:리워드 = 1:{z['rr']}

📊 기술 지표
  RSI: {z['rsi']}  (30 이하=과매도, 70 이상=과매수)
  52주 위치: {z['pos_pct']:.0f}%  (0%=52주 저점, 100%=52주 고점)
  MA20: {int(z['ma20']):,}원  /  MA60: {int(z['ma60']):,}원

📋 분석 근거
{reasons_txt}
━━━━━━━━━━━━━━━━━━━━━━━━━

답변 규칙:
1. 위 데이터를 적극 활용해 구체적으로 답변하세요 (가격, % 수치 포함).
2. 사용자가 보유 수량·평균 단가를 알려주면 수익률·손익 계산도 해주세요.
3. 분할 매수/매도 전략은 2~3단계로 나눠 설명하세요.
4. 시나리오 요청 시 반드시 마크다운 표(| 컬럼 | 값 |)로 단계별 정리하세요.
   표 예시: 단계 | 조건 | 수량 | 가격 | 예상 손익
4. 마지막에 항상 "⚠️ 투자 결정과 책임은 본인에게 있습니다" 한 줄 추가.
5. 절대 수익 보장 표현 금지. 한국어로만 답변."""

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": question})

    client = anthropic.Anthropic(api_key=api_key)
    resp   = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1200,
        system=system,
        messages=messages,
    )
    return resp.content[0].text


# ── 채팅 UI ───────────────────────────────────────────────────────────────────
def render_ai_chat(code: str, name: str, z: dict, sig: dict):
    """AI 투자 상담 채팅 UI."""
    st.markdown("#### 🤖 AI 투자 상담")
    st.caption("보유 수량·단가를 알려주면 맞춤 매매 전략을 제안해드려요")

    chat_key = f"chat_{code}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    # 빠른 질문 버튼
    quick = [
        "지금 매수해도 괜찮을까요?",
        "손절 기준을 어떻게 잡아야 할까요?",
        "분할 매수 전략을 알려주세요",
        "지금 고점인가요, 저점인가요?",
    ]
    st.markdown(
        "<div style='margin-bottom:6px;font-size:13px;color:var(--text-label)'>💡 빠른 질문</div>",
        unsafe_allow_html=True)
    cols = st.columns(2)
    for i, q in enumerate(quick):
        if cols[i % 2].button(q, key=f"quick_{code}_{i}", use_container_width=True):
            st.session_state[chat_key].append({"role": "user", "content": q})
            with st.spinner("AI 분석 중..."):
                answer = ask_ai_advisor(q, code, name, z, sig,
                                        st.session_state[chat_key][:-1])
            st.session_state[chat_key].append({"role": "assistant", "content": answer})
            st.rerun()

    # 시나리오 버튼
    scenario_q = (
        f"10주 기준으로 매수·매도·손절 전체 시나리오를 세워주세요. "
        f"현재가 {int(z['last']):,}원 기준으로 "
        f"① 언제/어떻게 매수할지 (분할 단계 포함) "
        f"② 1차·2차 익절 시점과 수량 "
        f"③ 손절 조건과 예상 손실금액 "
        f"④ 전체 투자금 대비 기대 수익/손실 요약을 표로 정리해주세요."
    )
    if st.button("📋 매수·매도·손절 시나리오 (10주 기준)",
                 key=f"quick_{code}_scenario",
                 use_container_width=True, type="primary"):
        st.session_state[chat_key].append({"role": "user", "content": scenario_q})
        with st.spinner("AI가 시나리오를 작성 중... (10~20초)"):
            answer = ask_ai_advisor(scenario_q, code, name, z, sig,
                                    st.session_state[chat_key][:-1])
        st.session_state[chat_key].append({"role": "assistant", "content": answer})
        st.rerun()

    # 대화 기록
    for idx, msg in enumerate(st.session_state[chat_key]):
        with st.chat_message(msg["role"],
                             avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

        if msg["role"] == "assistant":
            btn_key = f"{code}_{idx}"
            content = msg["content"]
            ab1, ab2, ab3, ab4 = st.columns([1.4, 1.4, 1.4, 5])
            with ab1:
                _clipboard_btn(content, btn_key)
            with ab2:
                _kakao_send_btn(content, code, name, z, btn_key)
            with ab3:
                if st.button("📸 카드", key=f"card_{btn_key}",
                             use_container_width=True,
                             help="스크린샷용 시나리오 카드 보기"):
                    st.session_state[f"show_card_{btn_key}"] = \
                        not st.session_state.get(f"show_card_{btn_key}", False)
            if st.session_state.get(f"show_card_{btn_key}", False):
                _scenario_card(content, code, name, z, btn_key)

    # 입력창
    placeholder = f"예: {int(z['last']*0.9):,}원에 100주 보유 중인데 매도 계획 어떻게 잡을까요?"
    if prompt := st.chat_input(placeholder, key=f"chat_input_{code}"):
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.spinner("AI 분석 중..."):
            answer = ask_ai_advisor(prompt, code, name, z, sig,
                                    st.session_state[chat_key][:-1])
        st.session_state[chat_key].append({"role": "assistant", "content": answer})
        st.rerun()

    # 초기화 버튼
    if st.session_state[chat_key]:
        if st.button("🗑️ 대화 초기화", key=f"chat_clear_{code}"):
            st.session_state[chat_key] = []
            st.rerun()


# ── 뉴스 탭 ───────────────────────────────────────────────────────────────────
def render_news_tab(name: str, code: str, z: dict, sig: dict):
    """뉴스 탭 — Google News RSS 5건 + AI 요약 버튼."""
    with st.spinner("뉴스 가져오는 중..."):
        news = get_stock_news(name)

    if not news:
        st.info("뉴스를 가져올 수 없습니다. 잠시 후 다시 시도해주세요.")
        return

    for n in news:
        title = n['title']
        link  = n['link']
        pub   = n['pub']
        st.markdown(
            f"<div style='background:var(--card-bg);border-radius:10px;"
            f"padding:10px 14px;margin-bottom:8px;border:1px solid var(--card-border)'>"
            f"<div style='font-size:14px;font-weight:700;word-break:keep-all;line-height:1.5'>"
            f"<a href='{link}' target='_blank' style='text-decoration:none;color:inherit'>{title}</a>"
            f"</div>"
            f"<div style='font-size:12px;color:var(--text-muted);margin-top:4px'>{pub}</div>"
            f"</div>",
            unsafe_allow_html=True)

    st.divider()
    if st.button("🤖 AI 뉴스 요약", key=f"news_ai_{code}", use_container_width=True):
        headlines     = "\n".join(f"{i+1}. {n['title']}" for i, n in enumerate(news))
        summary_prompt = (
            f"다음은 '{name}' 관련 최신 뉴스 헤드라인입니다:\n{headlines}\n\n"
            f"위 뉴스를 3줄로 요약하고, 주가에 미칠 영향을 짧게 평가해주세요. "
            f"한국어로, 간결하게 답변하세요.")
        with st.spinner("AI가 뉴스를 분석 중..."):
            summary = ask_ai_advisor(summary_prompt, code, name, z, sig, [])
        st.markdown(f"**📰 AI 뉴스 요약**\n\n{summary}")
