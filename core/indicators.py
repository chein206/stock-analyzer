"""
기술지표 계산 및 신호 판단.
- calc_indicators   : MA/BB/RSI/MACD/볼륨MA 추가
- calc_zones        : 매수구간·손절·목표가 계산
- calc_signal       : 종합 신호 점수 및 이유 생성
- build_signal_detail: 신호 박스용 HTML 생성
- find_sr           : 지지/저항 레벨 탐지
- price_position    : 현재가 위치 분류
"""
import numpy as np


# ── 기술지표 ─────────────────────────────────────────────────────────────────
def calc_indicators(df):
    import ta
    df = df.copy()
    c  = df['Close']

    for w, col in [(5, 'MA5'), (20, 'MA20'), (60, 'MA60'), (120, 'MA120')]:
        df[col] = c.rolling(w).mean()

    bb_mid   = c.rolling(20).mean()
    bb_std   = c.rolling(20).std()
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


# ── 매매 구간 ─────────────────────────────────────────────────────────────────
def calc_zones(df, info):
    last     = df['Close'].iloc[-1]
    bb_lower = df['BB_lower'].iloc[-1]
    bb_upper = df['BB_upper'].iloc[-1]
    ma20     = df['MA20'].iloc[-1]
    ma60     = df['MA60'].iloc[-1]
    rsi      = df['RSI'].iloc[-1]
    w52_low  = info.get('52w_low')  or df['Low'].min()
    w52_high = info.get('52w_high') or df['High'].max()

    buy_low  = max(bb_lower, w52_low * 1.03)
    buy_high = min(ma20, last * 0.99)
    if buy_high <= buy_low:
        buy_high = buy_low * 1.05
    buy_mid = (buy_low + buy_high) / 2
    stop    = round(buy_mid * 0.93 / 100) * 100

    tgt1_raw = round(bb_upper / 100) * 100
    tgt1     = max(tgt1_raw, round(last * 1.08 / 100) * 100)

    tgt2_raw = round(w52_high * 0.97 / 100) * 100
    tgt2     = max(tgt2_raw, round(last * 1.15 / 100) * 100)
    if tgt2 <= tgt1:
        tgt2 = round(tgt1 * 1.07 / 100) * 100

    above_bb_upper = last > bb_upper

    entry_ref = max(buy_mid, last)
    risk      = entry_ref - stop
    rr        = round((tgt1 - entry_ref) / risk, 1) if risk > 0 and tgt1 > entry_ref else 0

    pos_pct = ((last - w52_low) / (w52_high - w52_low) * 100
               if w52_high != w52_low else 50)
    day_chg = (last / df['Close'].iloc[-2] - 1) * 100 if len(df) > 1 else 0.0

    return {
        'last':     last,
        'day_chg':  day_chg,
        'buy_low':  round(buy_low  / 100) * 100,
        'buy_high': round(buy_high / 100) * 100,
        'buy_mid':  round(buy_mid  / 100) * 100,
        'stop':     stop,
        'tgt1':     tgt1,
        'tgt2':     tgt2,
        'rr':       rr,
        'rsi':      round(rsi, 1) if not np.isnan(rsi) else None,
        'pos_pct':  round(pos_pct, 1),
        'w52_low':  w52_low,
        'w52_high': w52_high,
        'ma20':     ma20,
        'ma60':     ma60,
        'above_bb_upper': above_bb_upper,
        'tgt1_raw':       tgt1_raw,
    }


# ── 신호 판단 ─────────────────────────────────────────────────────────────────
def calc_signal(df, z, flow_df=None):
    score   = 50
    reasons = []
    rsi  = z['rsi']
    last = z['last']
    pos  = z['pos_pct']

    bb_lower = df['BB_lower'].iloc[-1]
    bb_upper = df['BB_upper'].iloc[-1]
    bb_range = bb_upper - bb_lower
    bb_pct   = (last - bb_lower) / bb_range if bb_range > 0 else 0.5

    macd_v  = df['MACD'].iloc[-1]
    macd_s  = df['MACD_signal'].iloc[-1]
    macd_h  = df['MACD_hist'].iloc[-1]
    macd_hp = df['MACD_hist'].iloc[-2] if len(df) > 1 else macd_h
    ma5, ma20, ma60 = df['MA5'].iloc[-1], df['MA20'].iloc[-1], df['MA60'].iloc[-1]

    if rsi is not None:
        if   rsi < 30: score += 22; reasons.append(('pos', f'RSI {rsi:.0f} — 과매도 구간, 반등 가능성 높음'))
        elif rsi < 42: score += 10; reasons.append(('pos', f'RSI {rsi:.0f} — 저점 근처'))
        elif rsi > 72: score -= 22; reasons.append(('neg', f'RSI {rsi:.0f} — 과매수, 단기 조정 가능'))
        elif rsi > 62: score -= 10; reasons.append(('neu', f'RSI {rsi:.0f} — 다소 높은 편'))

    if   bb_pct < 0.10: score += 20; reasons.append(('pos', '볼린저밴드 하단 근처 — 기술적 저점'))
    elif bb_pct < 0.35: score += 10; reasons.append(('pos', '볼린저밴드 하단~중간 — 매수 고려 구간'))
    elif bb_pct > 1.0:  score -= 28; reasons.append(('neg', '볼린저밴드 상단 돌파 — 추격 매수 고위험 구간'))
    elif bb_pct > 0.90: score -= 20; reasons.append(('neg', '볼린저밴드 상단 근처 — 단기 고점 주의'))
    elif bb_pct > 0.70: score -= 8

    if   macd_v > macd_s and macd_h > macd_hp and macd_h > 0:
        score += 15; reasons.append(('pos', 'MACD 상승 전환 — 매수 신호'))
    elif macd_v > macd_s and macd_h > macd_hp:
        score += 8;  reasons.append(('pos', 'MACD 개선 중 — 매수 신호 준비'))
    elif macd_v < macd_s and macd_h < macd_hp and macd_h < 0:
        score -= 15; reasons.append(('neg', 'MACD 하락 전환 — 매도 압력'))

    if   ma5 > ma20 > ma60: score += 10; reasons.append(('pos', '이동평균 정배열 — 상승 추세 유지'))
    elif ma5 < ma20 < ma60: score -= 10; reasons.append(('neg', '이동평균 역배열 — 하락 추세'))

    if   pos < 25: score += 15; reasons.append(('pos', f'52주 저점 근처 ({pos:.0f}%) — 역사적 저점 구간'))
    elif pos < 40: score += 5
    elif pos > 85: score -= 15; reasons.append(('neg', f'52주 고점 근처 ({pos:.0f}%) — 신중한 접근 필요'))
    elif pos > 70: score -= 5;  reasons.append(('neu', f'52주 상단 ({pos:.0f}%) — 다소 높은 위치'))

    if flow_df is not None and not flow_df.empty:
        foreign_col = next((c for c in flow_df.columns if '외국인' in c), None)
        inst_col    = next((c for c in flow_df.columns if '기관' in c and '합계' in c), None)
        r5 = flow_df.tail(5)
        if foreign_col:
            f5 = r5[foreign_col].sum()
            if   f5 >  5e9: score += 12; reasons.append(('pos', f'외국인 최근 5일 순매수 +{f5/1e8:.0f}억'))
            elif f5 < -5e9: score -= 12; reasons.append(('neg', f'외국인 최근 5일 순매도 -{abs(f5)/1e8:.0f}억'))
        if inst_col:
            i5 = r5[inst_col].sum()
            if   i5 >  5e9: score += 8;  reasons.append(('pos', f'기관 최근 5일 순매수 +{i5/1e8:.0f}억'))
            elif i5 < -5e9: score -= 8;  reasons.append(('neg', f'기관 최근 5일 순매도 -{abs(i5)/1e8:.0f}억'))

    score = max(5, min(95, score))
    if   score >= 65: emoji, label, color, bg = '🟢', '매수 고려',  '#1D9E75', '#E8F8F2'; desc = '여러 지표가 매수 적합 신호를 보냅니다'
    elif score >= 45: emoji, label, color, bg = '🟡', '관망',       '#D4870E', '#FFF8E8'; desc = '명확한 신호가 없습니다. 조금 더 지켜보세요'
    else:             emoji, label, color, bg = '🔴', '매수 자제',  '#E24B4A', '#FEF0F0'; desc = '고점이거나 하락 추세입니다. 신중하게 접근하세요'

    return dict(score=score, emoji=emoji, label=label, color=color,
                bg=bg, desc=desc, reasons=reasons)


# ── 신호 상세 HTML ──────────────────────────────────────────────────────────────
def build_signal_detail(z: dict, sig: dict, df) -> str:
    """신호 박스용 수치 기반 상세 설명 HTML 생성."""
    rsi      = z.get('rsi')
    pos      = z.get('pos_pct', 50)
    last     = z['last']
    score    = sig['score']
    buy_low  = z['buy_low']
    buy_high = z['buy_high']
    buy_mid  = z['buy_mid']
    stop     = z['stop']
    tgt1     = z['tgt1']
    ma20     = z['ma20']
    ma60     = z['ma60']

    chips = []
    if rsi is not None:
        if   rsi < 30: chips.append(('pos', f'RSI {rsi:.0f} 과매도'))
        elif rsi < 45: chips.append(('pos', f'RSI {rsi:.0f} 저점권'))
        elif rsi > 70: chips.append(('neg', f'RSI {rsi:.0f} 과매수'))
        elif rsi > 60: chips.append(('neu', f'RSI {rsi:.0f} 다소 높음'))
        else:          chips.append(('neu', f'RSI {rsi:.0f} 중립'))

    if   pos < 25: chips.append(('pos', f'52주 {pos:.0f}% 저점권'))
    elif pos < 40: chips.append(('pos', f'52주 {pos:.0f}%'))
    elif pos > 85: chips.append(('neg', f'52주 {pos:.0f}% 고점권'))
    else:          chips.append(('neu', f'52주 {pos:.0f}%'))

    bb_lower = df['BB_lower'].iloc[-1]
    bb_upper = df['BB_upper'].iloc[-1]
    bb_range = bb_upper - bb_lower
    if bb_range > 0:
        bb_pct = (last - bb_lower) / bb_range
        if   bb_pct < 0.15: chips.append(('pos', f'볼린저 하단 ({bb_pct*100:.0f}%)'))
        elif bb_pct < 0.40: chips.append(('pos', f'볼린저 하단~중단 ({bb_pct*100:.0f}%)'))
        elif bb_pct > 0.85: chips.append(('neg', f'볼린저 상단 ({bb_pct*100:.0f}%)'))
        else:               chips.append(('neu', f'볼린저 중단 ({bb_pct*100:.0f}%)'))

    macd_v  = df['MACD'].iloc[-1]
    macd_s  = df['MACD_signal'].iloc[-1]
    macd_h  = df['MACD_hist'].iloc[-1]
    macd_hp = df['MACD_hist'].iloc[-2] if len(df) > 1 else macd_h
    if   macd_v > macd_s and macd_h > macd_hp: chips.append(('pos', 'MACD 상승전환'))
    elif macd_v < macd_s and macd_h < macd_hp: chips.append(('neg', 'MACD 하락전환'))
    else:                                        chips.append(('neu', 'MACD 혼조'))

    ma5 = df['MA5'].iloc[-1]
    if   ma5 > ma20 > ma60: chips.append(('pos', '이평 정배열'))
    elif ma5 < ma20 < ma60: chips.append(('neg', '이평 역배열'))
    else:                    chips.append(('neu', '이평 혼조'))

    chip_colors = {'pos': '#1D9E75', 'neg': '#E24B4A', 'neu': '#888'}
    chip_bg     = {
        'pos': 'rgba(29,158,117,0.12)',
        'neg': 'rgba(226,75,74,0.12)',
        'neu': 'rgba(136,136,136,0.10)',
    }
    chip_html = ''.join(
        f"<span style='display:inline-block;margin:2px 3px;"
        f"padding:2px 8px;border-radius:20px;font-size:12px;font-weight:600;"
        f"color:{chip_colors[s]};background:{chip_bg[s]}'>{t}</span>"
        for s, t in chips[:5]
    )

    above_bb    = z.get('above_bb_upper', False)
    tgt1_raw    = z.get('tgt1_raw', tgt1)
    dist_to_buy = (last - buy_high) / buy_high * 100
    dist_pct    = abs(dist_to_buy)

    if above_bb and last > tgt1_raw:
        over_pct = round((last - tgt1_raw) / tgt1_raw * 100, 1)
        pullback = round(tgt1_raw / 100) * 100
        action = (f"볼린저 상단(<b>{int(tgt1_raw):,}원</b>)을 <b>{over_pct}%</b> 초과한 강세 구간이에요. "
                  f"보유 중이라면 <b>분할 익절</b>(현재 +{over_pct}%)을 고려하고, "
                  f"신규 매수는 <b>{int(pullback):,}원</b> 부근 눌림목을 기다리세요. "
                  f"상단 돌파 직후 추격 매수는 고위험입니다.")
    elif score >= 65:
        if last <= buy_high:
            action = (f"현재가 <b>{int(last):,}원</b>이 매수 구간 "
                      f"<b>{int(buy_low):,}~{int(buy_high):,}원</b> 안에 있어요. "
                      f"손절 <b>{int(stop):,}원</b> / 목표 <b>{int(tgt1):,}원</b> 기준으로 분할 매수를 고려해보세요.")
        elif dist_pct <= 3:
            action = (f"매수 구간 <b>{int(buy_low):,}~{int(buy_high):,}원</b>보다 "
                      f"<b>{dist_pct:.1f}%</b> 위에 있어요. 소폭 눌림목 후 진입 고려.")
        else:
            action = (f"현재가 <b>{int(last):,}원</b>이 매수 구간 <b>{int(buy_high):,}원</b>보다 "
                      f"<b>{dist_pct:.1f}%</b> 높아요. 충분한 눌림목 후 분할 진입 전략 권장.")
    elif score >= 45:
        action = (f"뚜렷한 방향성이 없어요. MA20 <b>{int(ma20):,}원</b> · MA60 <b>{int(ma60):,}원</b> "
                  f"지지 여부를 확인 후, 매수 구간 <b>{int(buy_low):,}~{int(buy_high):,}원</b> 진입 시 재판단 권장.")
    else:
        action = (f"현재 하락 추세 또는 고점 신호 다수. "
                  f"매수 구간 <b>{int(buy_low):,}원</b> 이하로 충분히 내려올 때까지 관망을 권장해요. "
                  f"무리한 매수 보류.")

    return (
        f"<div style='margin-top:4px'>{chip_html}</div>"
        f"<div style='margin-top:10px;font-size:13px;line-height:1.7;opacity:0.9'>{action}</div>"
    )


# ── 지지/저항 ─────────────────────────────────────────────────────────────────
def find_sr(df, n=5):
    recent = df.tail(60)
    highs, lows = recent['High'].values, recent['Low'].values
    sup, res = [], []
    for i in range(n, len(lows) - n):
        if (all(lows[i] <= lows[i - j] for j in range(1, n + 1))
                and all(lows[i] <= lows[i + j] for j in range(1, n + 1))):
            sup.append(lows[i])
    for i in range(n, len(highs) - n):
        if (all(highs[i] >= highs[i - j] for j in range(1, n + 1))
                and all(highs[i] >= highs[i + j] for j in range(1, n + 1))):
            res.append(highs[i])

    def cluster(lvls, pct=0.02):
        if not lvls:
            return []
        lvls = sorted(set(lvls))
        result, grp = [lvls[0]], [lvls[0]]
        for v in lvls[1:]:
            if abs(v - grp[-1]) / grp[-1] < pct:
                grp.append(v)
                result[-1] = np.mean(grp)
            else:
                grp = [v]
                result.append(v)
        return result

    return cluster(sup)[-3:], cluster(res)[:3]


# ── 현재가 위치 분류 ──────────────────────────────────────────────────────────
def price_position(last, z):
    above_bb = z.get('above_bb_upper', False)
    tgt1_raw = z.get('tgt1_raw', z['tgt1'])

    if last < z['stop']:
        return ('🔴', '손절 구간 아래입니다 — 보유 중이라면 손절 고려',              '#FEF0F0', '#E24B4A')
    if last <= z['buy_low']:
        return ('🎯', '매수 구간에 접근 중 — 분할 매수 고려',                        '#E8F8F2', '#1D9E75')
    if last <= z['buy_high']:
        return ('✅', '현재가가 매수 구간 안에 있습니다!',                             '#E8F8F2', '#1D9E75')
    if above_bb and last > tgt1_raw:
        over_pct = round((last - tgt1_raw) / tgt1_raw * 100, 1)
        return ('🔥', f'볼린저 상단을 {over_pct}% 돌파 중 — 보유자는 분할 익절, 신규 매수는 눌림목 대기',
                '#FFF3E0', '#E65100')
    if last <= z['tgt1']:
        return ('🟡', '매수 구간보다 높습니다 — 눌림목(하락 후 반등) 기다리세요',      '#FFF8E8', '#D4870E')
    return     ('🏆', '단기 목표가 도달 구간 — 보유 중이라면 분할 익절 고려',          '#FFF9E6', '#B8860B')
