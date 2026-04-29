"""
quant_engine.py — 실전 트레이딩 시스템 핵심 엔진
═══════════════════════════════════════════════════════════════════
Senior Quant 수준 구현 · UI 완전 분리 · 주식앱.py 와 호환

모듈 구성
─────────
1. MarketRegime   시장 상태 감지 (상승 / 하락 / 횡보)
2. SignalEngine   4단계 매매 신호 (기존 calc_signal 대체)
3. Backtester     Walk-Forward 백테스트 + 성과 지표
4. Recommender    TOP-N 종목 추천 (스크리너 결과 재활용)
5. AlertMonitor   조건 기반 알림 감시

과적합 방지 원칙
───────────────
· Walk-Forward : IS(학습) 70% → OOS(검증) 30% 슬라이딩 윈도우
· Look-ahead   : 신호 shift(1) → 다음 봉 진입 (재료 공유 차단)
· 거래비용     : 수수료 0.15% + 슬리피지 0.1% 반드시 차감
· 파라미터     : 6개 고정값만 사용, 구간별 최적화 금지
· 다수결 투표  : 단일 지표 의존 금지, 복수 지표 합의
═══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
# 0. 내부 지표 계산 유틸 (ta 라이브러리 없이도 동작)
# ═══════════════════════════════════════════════════════════════════

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def _macd(close: pd.Series):
    e12  = _ema(close, 12)
    e26  = _ema(close, 26)
    macd = e12 - e26
    sig  = _ema(macd, 9)
    return macd, sig, macd - sig

def _bollinger(close: pd.Series, period: int = 20, std: float = 2.0):
    mid   = close.rolling(period).mean()
    sigma = close.rolling(period).std()
    return mid, mid + std * sigma, mid - std * sigma

def _adx(high: pd.Series, low: pd.Series, close: pd.Series,
         period: int = 14) -> pd.Series:
    tr   = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    dm_p = (high - high.shift()).clip(lower=0)
    dm_m = (low.shift() - low).clip(lower=0)
    dm_p = dm_p.where(dm_p > dm_m, 0)
    dm_m = dm_m.where(dm_m > dm_p, 0)
    atr  = _ema(tr, period)
    di_p = _ema(dm_p, period) / atr.replace(0, np.nan) * 100
    di_m = _ema(dm_m, period) / atr.replace(0, np.nan) * 100
    dx   = ((di_p - di_m).abs() / (di_p + di_m).replace(0, np.nan) * 100)
    return _ema(dx.fillna(0), period)

def _calc_indicators_minimal(df: pd.DataFrame) -> pd.DataFrame:
    """quant_engine 내부용 지표 계산 (ta 불필요)"""
    df = df.copy()
    c  = df['Close']
    for w, col in [(5, 'MA5'), (20, 'MA20'), (60, 'MA60'), (120, 'MA120')]:
        df[col] = c.rolling(w).mean()
    df['BB_mid'], df['BB_upper'], df['BB_lower'] = _bollinger(c)
    df['RSI']                                     = _rsi(c)
    df['MACD'], df['MACD_signal'], df['MACD_hist'] = _macd(c)
    df['Vol_MA20'] = df['Volume'].rolling(20).mean() if 'Volume' in df.columns else 0
    if 'High' in df.columns and 'Low' in df.columns:
        df['ADX'] = _adx(df['High'], df['Low'], c)
    return df


# ═══════════════════════════════════════════════════════════════════
# 1. Market Regime Detection
# ═══════════════════════════════════════════════════════════════════

class MarketRegime:
    """
    KOSPI 지수 기반 시장 상태 감지.

    판단 지표 (5개 다수결 투표):
      ① MA200 대비 현재가 위치   — 장기 추세
      ② MA50 20일 기울기         — 중기 방향성
      ③ ADX                      — 추세 강도
      ④ 최근 20일 수익률         — 단기 모멘텀
      ⑤ 52주 위치                — 상대적 고저

    결과: bull / bear / sideways
    """

    @staticmethod
    def detect(kospi_df: pd.DataFrame) -> dict:
        """
        Args:
            kospi_df : KOSPI OHLCV DataFrame (최소 60일, 권장 252일)
        Returns:
            {'regime', 'strength', 'label', 'emoji', 'color', 'details'}
        """
        if kospi_df is None or len(kospi_df) < 60:
            return MarketRegime._default()

        df  = kospi_df.copy()
        c   = df['Close']
        n   = len(c)
        last = float(c.iloc[-1])

        votes: list[int] = []   # +1 강세, -1 약세, 0 중립

        # ① MA200 위치
        ma200 = float(c.rolling(min(200, n)).mean().iloc[-1])
        if   last > ma200 * 1.02: votes.append(1)
        elif last < ma200 * 0.97: votes.append(-1)
        else:                      votes.append(0)

        # ② MA50 기울기 (20일 변화)
        ma50 = c.rolling(min(50, n)).mean()
        if len(ma50.dropna()) >= 22:
            slope = (float(ma50.iloc[-1]) - float(ma50.iloc[-21])) / float(ma50.iloc[-21]) * 100
            if   slope >  1.5: votes.append(1)
            elif slope < -1.5: votes.append(-1)
            else:               votes.append(0)
        else:
            votes.append(0)

        # ③ ADX (추세 강도 — 방향 없음, 보조 가중)
        if 'High' in df.columns and 'Low' in df.columns and n >= 30:
            adx_val = float(_adx(df['High'], df['Low'], c).iloc[-1])
        else:
            adx_val = 20.0
        # ADX ≥ 25 = 강한 추세 → 현재 추세 방향을 강화
        adx_boost = 1 if adx_val >= 25 else 0

        # ④ 20일 모멘텀
        if n >= 22:
            ret20 = (last / float(c.iloc[-22]) - 1) * 100
            if   ret20 >  3: votes.append(1 + adx_boost)
            elif ret20 < -3: votes.append(-1 - adx_boost)
            else:             votes.append(0)
        else:
            votes.append(0)

        # ⑤ 52주 위치
        if n >= 120:
            h52 = float(c.rolling(min(252, n)).max().iloc[-1])
            l52 = float(c.rolling(min(252, n)).min().iloc[-1])
            pos = (last - l52) / (h52 - l52) * 100 if h52 != l52 else 50
            if   pos > 65: votes.append(1)
            elif pos < 30: votes.append(-1)
            else:           votes.append(0)
        else:
            pos = 50
            votes.append(0)

        # 집계
        bull = sum(v for v in votes if v > 0)
        bear = abs(sum(v for v in votes if v < 0))
        total_weight = max(bull + bear, 1)

        bull_ratio = bull / total_weight
        bear_ratio = bear / total_weight

        if   bull_ratio >= 0.60: regime, label, emoji, color = 'bull',     '상승장', '🚀', '#1D9E75'
        elif bear_ratio >= 0.60: regime, label, emoji, color = 'bear',     '하락장', '🐻', '#E24B4A'
        else:                     regime, label, emoji, color = 'sideways', '횡보장', '↔️', '#D4870E'

        strength = int(max(bull_ratio, bear_ratio) * 100)

        return {
            'regime':   regime,
            'strength': strength,
            'label':    label,
            'emoji':    emoji,
            'color':    color,
            'details': {
                'last':      last,
                'ma200':     ma200,
                'ma200_gap': round((last / ma200 - 1) * 100, 2),
                'adx':       round(adx_val, 1),
                'ret_20d':   round((last / float(c.iloc[max(-22, -n)]) - 1) * 100, 2),
                'w52_pos':   round(pos, 1),
            }
        }

    @staticmethod
    def _default() -> dict:
        return {
            'regime': 'sideways', 'strength': 50,
            'label': '데이터 부족', 'emoji': '❓', 'color': '#888888',
            'details': {'last': 0, 'ma200': 0, 'ma200_gap': 0,
                        'adx': 20, 'ret_20d': 0, 'w52_pos': 50}
        }


# ═══════════════════════════════════════════════════════════════════
# 2. Signal Engine — 4단계 매매 신호
# ═══════════════════════════════════════════════════════════════════

class SignalEngine:
    """
    기존 calc_signal (3단계) 대체 — 하위 호환 유지.

    신호 레벨:
      🟢 적극매수  score ≥ 68 + bull 시장
      🔵 분할매수  score ≥ 60
      ⚪ 관망      score ≥ 42
      🔴 매도/위험 score <  42

    시장 상태(regime)는 ±보정치로 반영 (단순 필터링 대신)
    → 개별 종목 신호가 시장에 종속되지 않도록 설계
    """

    LEVELS: dict[str, dict] = {
        'strong_buy': {
            'emoji': '🟢', 'label': '적극 매수',
            'color': '#0D7C4A', 'bg': '#E0F7EE',
        },
        'buy': {
            'emoji': '🔵', 'label': '분할 매수',
            'color': '#1A5FAC', 'bg': '#EAF2FF',
        },
        'neutral': {
            'emoji': '⚪', 'label': '관망',
            'color': '#666666', 'bg': '#F5F5F5',
        },
        'sell': {
            'emoji': '🔴', 'label': '매도 / 위험',
            'color': '#C0392B', 'bg': '#FEECEC',
        },
    }

    @classmethod
    def evaluate(cls, df: pd.DataFrame, z: dict,
                 flow_df=None, regime: dict = None) -> dict:
        """
        기존 calc_signal() 과 동일한 반환 구조 + 추가 필드.

        Returns:
            score, emoji, label, color, bg, desc, reasons  ← 기존 호환
            level, raw_score, regime_adj, regime_label     ← 신규
        """
        raw_score, reasons = cls._score(df, z, flow_df)
        regime_adj         = cls._regime_adj(regime)
        adj_score          = int(np.clip(raw_score + regime_adj, 5, 95))
        level              = cls._classify(adj_score, regime)
        info               = cls.LEVELS[level]
        desc               = cls._desc(adj_score, level, z, regime)

        return {
            # ── 기존 calc_signal 호환 필드 ──────────────────────────
            'score':   adj_score,
            'emoji':   info['emoji'],
            'label':   info['label'],
            'color':   info['color'],
            'bg':      info['bg'],
            'desc':    desc,
            'reasons': reasons,
            # ── 신규 필드 ────────────────────────────────────────────
            'level':        level,
            'raw_score':    raw_score,
            'regime_adj':   regime_adj,
            'regime_label': regime['label'] if regime else '미감지',
        }

    # ── 내부 메서드 ──────────────────────────────────────────────────

    @staticmethod
    def _score(df: pd.DataFrame, z: dict, flow_df) -> tuple[int, list]:
        """멀티팩터 점수 산출 (50점 기준 가감)"""
        score   = 50
        reasons = []
        rsi     = z.get('rsi')
        last    = z['last']
        pos     = z.get('pos_pct', 50)

        bb_l  = df['BB_lower'].iloc[-1]
        bb_u  = df['BB_upper'].iloc[-1]
        bb_r  = bb_u - bb_l
        bb_p  = (last - bb_l) / bb_r if bb_r > 0 else 0.5

        mv    = df['MACD'].iloc[-1];        ms = df['MACD_signal'].iloc[-1]
        mh    = df['MACD_hist'].iloc[-1];   mhp = df['MACD_hist'].iloc[-2] if len(df) > 1 else mh
        ma5, ma20, ma60 = df['MA5'].iloc[-1], df['MA20'].iloc[-1], df['MA60'].iloc[-1]

        # ─ RSI ─
        if rsi is not None:
            if   rsi < 25:  score += 25; reasons.append(('pos', f'RSI {rsi:.0f} — 극과매도, 강한 반등 구간'))
            elif rsi < 35:  score += 18; reasons.append(('pos', f'RSI {rsi:.0f} — 과매도'))
            elif rsi < 45:  score += 8;  reasons.append(('pos', f'RSI {rsi:.0f} — 저점 근처'))
            elif rsi > 75:  score -= 25; reasons.append(('neg', f'RSI {rsi:.0f} — 극과매수, 조정 위험'))
            elif rsi > 68:  score -= 18; reasons.append(('neg', f'RSI {rsi:.0f} — 과매수'))
            elif rsi > 58:  score -= 8;  reasons.append(('neu', f'RSI {rsi:.0f} — 다소 높음'))

        # ─ 볼린저밴드 ─
        if   bb_p < 0.05: score += 22; reasons.append(('pos', '볼린저 하단 돌파 — 강한 기술적 저점'))
        elif bb_p < 0.20: score += 14; reasons.append(('pos', '볼린저 하단 근처 — 매수 구간'))
        elif bb_p < 0.40: score += 6;  reasons.append(('pos', '볼린저 하단~중단'))
        elif bb_p > 0.95: score -= 22; reasons.append(('neg', '볼린저 상단 돌파 — 단기 고점 신호'))
        elif bb_p > 0.80: score -= 14; reasons.append(('neg', '볼린저 상단 근처 — 매도 압력'))

        # ─ MACD (연속성으로 신뢰도 향상) ─
        if   mv > ms and mh > mhp and mh > 0:  score += 16; reasons.append(('pos', 'MACD 골든크로스 + 히스토그램 확대'))
        elif mv > ms and mh > mhp:               score += 9;  reasons.append(('pos', 'MACD 상승 전환 중'))
        elif mv < ms and mh < mhp and mh < 0:  score -= 16; reasons.append(('neg', 'MACD 데드크로스 + 히스토그램 확대'))
        elif mv < ms and mh < mhp:               score -= 9;  reasons.append(('neg', 'MACD 하락 전환 중'))

        # ─ 이동평균 배열 ─
        if   ma5 > ma20 > ma60: score += 12; reasons.append(('pos', '이평 정배열 — 상승 추세'))
        elif ma5 < ma20 < ma60: score -= 12; reasons.append(('neg', '이평 역배열 — 하락 추세'))

        # ─ 52주 위치 ─
        if   pos < 15: score += 18; reasons.append(('pos', f'52주 극저점 ({pos:.0f}%) — 역발상 구간'))
        elif pos < 30: score += 12; reasons.append(('pos', f'52주 저점권 ({pos:.0f}%)'))
        elif pos < 45: score += 5
        elif pos > 90: score -= 18; reasons.append(('neg', f'52주 고점 근처 ({pos:.0f}%)'))
        elif pos > 75: score -= 8;  reasons.append(('neu', f'52주 상단 ({pos:.0f}%)'))

        # ─ 거래량 (방향성 확인) ─
        vol_ma = df.get('Vol_MA20', pd.Series([1])).iloc[-1]
        vol    = df.get('Volume',   pd.Series([1])).iloc[-1] if 'Volume' in df.columns else 1
        if vol_ma and vol_ma > 0:
            vr = vol / vol_ma
            if   vr > 2.0 and mv > ms: score += 8;  reasons.append(('pos', f'거래량 {vr:.1f}배 + 매수 신호'))
            elif vr > 2.0 and mv < ms: score -= 8;  reasons.append(('neg', f'거래량 {vr:.1f}배 + 매도 신호'))

        # ─ ADX (추세 강도 반영) ─
        if 'ADX' in df.columns:
            adx_v = df['ADX'].iloc[-1]
            if adx_v > 30 and ma5 > ma20:  score += 6;  reasons.append(('pos', f'ADX {adx_v:.0f} 강한 상승 추세'))
            elif adx_v > 30 and ma5 < ma20: score -= 6;  reasons.append(('neg', f'ADX {adx_v:.0f} 강한 하락 추세'))

        # ─ 수급 ─
        if flow_df is not None and not flow_df.empty:
            foreign_col = next((c for c in flow_df.columns if '외국인' in c), None)
            inst_col    = next((c for c in flow_df.columns if '기관' in c), None)
            r5 = flow_df.tail(5)
            if foreign_col:
                f5 = r5[foreign_col].sum()
                if   f5 >  5e9: score += 12; reasons.append(('pos', f'외국인 5일 순매수 +{f5/1e8:.0f}억'))
                elif f5 < -5e9: score -= 12; reasons.append(('neg', f'외국인 5일 순매도 {f5/1e8:.0f}억'))
            if inst_col:
                i5 = r5[inst_col].sum()
                if   i5 >  5e9: score += 8;  reasons.append(('pos', f'기관 5일 순매수 +{i5/1e8:.0f}억'))
                elif i5 < -5e9: score -= 8;  reasons.append(('neg', f'기관 5일 순매도 {i5/1e8:.0f}억'))

        return int(np.clip(score, 5, 95)), reasons

    @staticmethod
    def _regime_adj(regime: dict) -> int:
        """시장 상태 보정 (개별 신호를 대체하지 않고 보조)"""
        if not regime:
            return 0
        return {'bull': +5, 'sideways': 0, 'bear': -8}.get(regime.get('regime', ''), 0)

    @staticmethod
    def _classify(score: int, regime: dict) -> str:
        r = regime.get('regime', 'sideways') if regime else 'sideways'
        if score >= 68 and r == 'bull': return 'strong_buy'
        if score >= 60:                  return 'buy'
        if score >= 42:                  return 'neutral'
        return 'sell'

    @staticmethod
    def _desc(score: int, level: str, z: dict, regime: dict) -> str:
        r_lbl = regime['label'] if regime else '시장 미감지'
        buy_l, buy_h = int(z.get('buy_low', 0)), int(z.get('buy_high', 0))
        stop         = int(z.get('stop', 0))
        tgt1         = int(z.get('tgt1', 0))
        last         = int(z.get('last', 0))

        if level == 'strong_buy':
            return (f"[{r_lbl}] 복수 지표 강한 매수 신호. "
                    f"매수 구간 {buy_l:,}~{buy_h:,}원 · 손절 {stop:,}원 · 목표 {tgt1:,}원")
        if level == 'buy':
            return (f"[{r_lbl}] 긍정적 신호. "
                    f"한 번에 전량 매수보다 2~3회 분할 진입 권장. "
                    f"매수 구간 {buy_l:,}~{buy_h:,}원")
        if level == 'neutral':
            return f"[{r_lbl}] 방향성 불명확. 매수 구간 {buy_l:,}원 진입 전 관망 권장."
        return (f"[{r_lbl}] 약세 신호 다수. 신규 진입 자제. "
                f"보유 중이면 손절 {stop:,}원 이하 시 매도 고려.")


# ═══════════════════════════════════════════════════════════════════
# 3. Backtester — Walk-Forward 백테스트
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Trade:
    entry_date:  object
    exit_date:   object
    entry_price: float
    exit_price:  float
    shares:      int
    pnl_pct:     float
    exit_type:   str       # stop_loss / tp1 / tp2 / forced

@dataclass
class BacktestResult:
    trades:       list[Trade]       = field(default_factory=list)
    equity_curve: pd.Series         = field(default_factory=pd.Series)
    params:       dict              = field(default_factory=dict)
    period:       str               = ''

    # ── 성과 지표 ────────────────────────────────────────────────────

    @property
    def total_return(self) -> float:
        if len(self.equity_curve) < 2: return 0.0
        return (self.equity_curve.iloc[-1] / self.equity_curve.iloc[0] - 1) * 100

    @property
    def win_rate(self) -> float:
        if not self.trades: return 0.0
        return sum(1 for t in self.trades if t.pnl_pct > 0) / len(self.trades) * 100

    @property
    def mdd(self) -> float:
        """Maximum Drawdown (%)"""
        if len(self.equity_curve) < 2: return 0.0
        roll_max = self.equity_curve.cummax()
        dd = (self.equity_curve - roll_max) / roll_max * 100
        return float(dd.min())

    @property
    def sharpe(self) -> float:
        """연환산 Sharpe Ratio (무위험 수익률 3.5% 가정)"""
        if len(self.equity_curve) < 30: return 0.0
        daily_ret = self.equity_curve.pct_change().dropna()
        std = daily_ret.std()
        if std == 0: return 0.0
        rf  = 0.035 / 252
        return float((daily_ret.mean() - rf) / std * np.sqrt(252))

    @property
    def avg_win(self) -> float:
        wins = [t.pnl_pct for t in self.trades if t.pnl_pct > 0]
        return float(np.mean(wins)) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [t.pnl_pct for t in self.trades if t.pnl_pct <= 0]
        return float(np.mean(losses)) if losses else 0.0

    @property
    def profit_factor(self) -> float:
        gross_win  = sum(t.pnl_pct for t in self.trades if t.pnl_pct > 0)
        gross_loss = abs(sum(t.pnl_pct for t in self.trades if t.pnl_pct <= 0))
        return round(gross_win / gross_loss, 2) if gross_loss > 0 else 999.0

    @property
    def expectancy(self) -> float:
        """기댓값 = 승률 × 평균수익 + 패률 × 평균손실"""
        wr = self.win_rate / 100
        return round(wr * self.avg_win + (1 - wr) * self.avg_loss, 2)

    def summary(self) -> dict:
        return {
            '총 수익률 (%)':       round(self.total_return, 2),
            '승률 (%)':           round(self.win_rate,     1),
            'MDD (%)':            round(self.mdd,          2),
            'Sharpe Ratio':       round(self.sharpe,       2),
            '거래 횟수':          len(self.trades),
            '평균 수익 (%)':      round(self.avg_win,      2),
            '평균 손실 (%)':      round(self.avg_loss,     2),
            'Profit Factor':      round(self.profit_factor, 2),
            '기댓값 (%)':         round(self.expectancy,   2),
            '검증 기간':          self.period,
        }

    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                '진입일':   t.entry_date,
                '청산일':   t.exit_date,
                '진입가':   int(t.entry_price),
                '청산가':   int(t.exit_price),
                '수량':     t.shares,
                '수익률(%)': round(t.pnl_pct, 2),
                '유형':     t.exit_type,
            }
            for t in self.trades
        ])


class Backtester:
    """
    Walk-Forward 백테스트 엔진.

    파라미터 (6개 고정 — 구간별 최적화 금지):
      commission    수수료 0.15%
      slippage      슬리피지 0.1%
      stop_loss_pct 손절 7%
      take_profit1  1차 목표 12%
      take_profit2  2차 목표 20%
      partial_exit  1차 도달 시 50% 익절

    Look-ahead bias 방지:
      - 신호는 전일 종가 기준으로 계산
      - 진입은 다음 봉 시가 기준 (Close 사용 시 slippage 가산)
      - 지표 계산 창(window) 이전 데이터는 신호 생성 제외
    """

    PARAMS = {
        'commission':    0.0015,
        'slippage':      0.001,
        'stop_loss_pct': 0.07,
        'take_profit1':  0.12,
        'take_profit2':  0.20,
        'partial_exit':  0.5,
        'min_score':     60,
        'invest_ratio':  0.2,    # 보유 자본의 20% 투자 (포지션 사이징)
    }

    @classmethod
    def run(cls,
            df_raw:          pd.DataFrame,
            initial_capital: float = 10_000_000,
            walk_forward:    bool  = True,
            oos_ratio:       float = 0.3) -> BacktestResult:
        """
        Args:
            df_raw          OHLCV DataFrame (최소 60일)
            initial_capital 초기 자본 (원)
            walk_forward    True = Walk-Forward (권장), False = 단순 백테스트
            oos_ratio       Out-of-sample 비율
        """
        if df_raw is None or len(df_raw) < 60:
            return BacktestResult()

        p = cls.PARAMS.copy()

        if walk_forward and len(df_raw) >= 120:
            return cls._walk_forward(df_raw, p, initial_capital, oos_ratio)
        return cls._run_period(df_raw, p, initial_capital)

    # ── Walk-Forward ────────────────────────────────────────────────

    @classmethod
    def _walk_forward(cls, df_raw, p, capital, oos_ratio) -> BacktestResult:
        n       = len(df_raw)
        oos_len = max(30, int(n * oos_ratio))
        is_len  = n - oos_len
        step    = max(15, oos_len // 4)

        all_trades:    list[Trade]   = []
        equity_chunks: list[pd.Series] = []
        cur_capital = capital

        # 슬라이딩 윈도우 생성
        windows = []
        s = 0
        while s + is_len < n:
            oos_s = s + is_len
            oos_e = min(oos_s + step, n)
            windows.append((s, oos_s, oos_e))
            s += step

        if not windows:
            windows = [(0, is_len, n)]

        start_date = str(df_raw.index[0])[:10]
        end_date   = str(df_raw.index[-1])[:10]

        for _, oos_s, oos_e in windows:
            chunk = df_raw.iloc[oos_s:oos_e]
            if len(chunk) < 10:
                continue
            res = cls._run_period(chunk, p, cur_capital)
            if res.trades:
                all_trades.extend(res.trades)
            if len(res.equity_curve) > 0:
                equity_chunks.append(res.equity_curve)
                cur_capital = float(res.equity_curve.iloc[-1])

        equity = pd.concat(equity_chunks) if equity_chunks else pd.Series([capital], dtype=float)

        r = BacktestResult(all_trades, equity, p, f'{start_date} ~ {end_date} (Walk-Forward OOS)')
        return r

    # ── 단일 구간 백테스트 ──────────────────────────────────────────

    @classmethod
    def _run_period(cls, df_raw: pd.DataFrame, p: dict,
                    initial_capital: float) -> BacktestResult:
        """
        Look-ahead bias 방지:
          1. 지표는 i번째 행까지만 사용 (미래 정보 차단)
          2. 신호는 i-1 봉 종가 기준
          3. 진입/청산은 i 봉 종가 (slippage 가산)
        """
        df = _calc_indicators_minimal(df_raw.copy())
        if len(df) < 25:
            return BacktestResult()

        cost = p['commission'] + p['slippage']

        capital  = float(initial_capital)
        position = 0       # 보유 주수
        entry_px = 0.0
        partial  = False   # 1차 익절 여부
        entry_dt = None

        trades: list[Trade] = []
        equity: list        = []

        for i in range(25, len(df)):
            row  = df.iloc[i]
            close = float(row['Close'])
            dt    = df.index[i]

            equity.append({'date': dt,
                           'value': capital + position * close})

            # ── 청산 로직 (진입 중일 때) ──────────────────────────
            if position > 0:
                pnl = (close / entry_px - 1) * 100

                # 손절
                if close <= entry_px * (1 - p['stop_loss_pct']):
                    proceeds = close * position * (1 - cost)
                    capital += proceeds
                    trades.append(Trade(entry_dt, dt, entry_px, close,
                                        position, pnl, 'stop_loss'))
                    position = 0

                # 1차 목표 (부분 익절)
                elif not partial and close >= entry_px * (1 + p['take_profit1']):
                    exit_n = max(1, int(position * p['partial_exit']))
                    proceeds = close * exit_n * (1 - cost)
                    capital += proceeds
                    trades.append(Trade(entry_dt, dt, entry_px, close,
                                        exit_n, pnl, 'tp1_partial'))
                    position -= exit_n
                    partial   = True

                # 2차 목표 (전량 익절)
                elif partial and close >= entry_px * (1 + p['take_profit2']):
                    proceeds = close * position * (1 - cost)
                    capital += proceeds
                    trades.append(Trade(entry_dt, dt, entry_px, close,
                                        position, pnl, 'tp2_full'))
                    position = 0

            # ── 진입 로직 (포지션 없을 때) ────────────────────────
            if position == 0:
                score = cls._score_at(df, i)
                if score >= p['min_score']:
                    invest = capital * p['invest_ratio']
                    shares = int(invest / (close * (1 + cost)))
                    if shares > 0 and invest <= capital:
                        entry_px = close * (1 + cost)
                        capital -= entry_px * shares
                        position = shares
                        partial  = False
                        entry_dt = dt

        # 기간 종료 시 잔여 포지션 강제 청산
        if position > 0:
            close = float(df['Close'].iloc[-1])
            pnl   = (close / entry_px - 1) * 100
            proceeds = close * position * (1 - cost)
            capital += proceeds
            trades.append(Trade(entry_dt, df.index[-1], entry_px, close,
                                position, pnl, 'forced'))
            position = 0

        equity_s = pd.Series(
            [e['value'] for e in equity],
            index=[e['date'] for e in equity],
            dtype=float,
        )

        start = str(df_raw.index[0])[:10]
        end   = str(df_raw.index[-1])[:10]
        return BacktestResult(trades, equity_s, p, f'{start} ~ {end}')

    @staticmethod
    def _score_at(df: pd.DataFrame, i: int) -> int:
        """i번째 봉 기준 빠른 신호 점수 (look-ahead 없음)"""
        score = 50
        try:
            rsi  = float(df['RSI'].iloc[i - 1])        # 전일 신호
            macd = float(df['MACD'].iloc[i - 1])
            macs = float(df['MACD_signal'].iloc[i - 1])
            bb_l = float(df['BB_lower'].iloc[i - 1])
            bb_u = float(df['BB_upper'].iloc[i - 1])
            ma5  = float(df['MA5'].iloc[i - 1])
            ma20 = float(df['MA20'].iloc[i - 1])
            ma60 = float(df['MA60'].iloc[i - 1])
            close = float(df['Close'].iloc[i - 1])
            bb_r = bb_u - bb_l

            if rsi < 30:   score += 22
            elif rsi < 45: score += 10
            elif rsi > 70: score -= 22
            elif rsi > 60: score -= 10

            bb_p = (close - bb_l) / bb_r if bb_r > 0 else 0.5
            if   bb_p < 0.15: score += 16
            elif bb_p < 0.35: score += 8
            elif bb_p > 0.85: score -= 16

            if   macd > macs: score += 10
            else:              score -= 10

            if   ma5 > ma20 > ma60: score += 10
            elif ma5 < ma20 < ma60: score -= 10
        except Exception:
            pass
        return int(np.clip(score, 0, 100))


# ═══════════════════════════════════════════════════════════════════
# 4. Recommender — TOP-N 종목 자동 추천
# ═══════════════════════════════════════════════════════════════════

class Recommender:
    """
    스크리너 결과를 기반으로 당일 추천 종목 선별.

    추가 필터 (과적합 방지 — 단순 score 순위만 사용하지 않음):
      · 리스크:리워드(R:R) ≥ min_rr
      · 시장 하락장 시 상 등급(대형주)만 선별
      · 복합 랭킹: score 60% + R:R 비율 30% + 52주 위치 역수 10%
    """

    @staticmethod
    def get_top_n(screen_results: list,
                  regime: dict   = None,
                  n:      int    = 5,
                  min_rr: float  = 1.5) -> list:
        """
        Args:
            screen_results : run_screen() 반환 리스트
            regime         : MarketRegime.detect() 결과
            n              : 추천 종목 수
            min_rr         : 최소 R:R 비율
        Returns:
            추천 종목 리스트 (복합 랭킹 순)
        """
        if not screen_results:
            return []

        # 기본 필터
        cands = [r for r in screen_results if r.get('rr', 0) >= min_rr]

        # 시장 하락장 → 안전 자산(상 등급)만
        if regime and regime.get('regime') == 'bear':
            safe = [r for r in cands if r.get('tier', '') == '상']
            cands = safe if safe else cands[:max(1, n // 2)]

        # 복합 랭킹
        def composite(r: dict) -> float:
            score_norm = r.get('score', 50) / 100
            rr_norm    = min(r.get('rr', 1), 4) / 4
            pos_norm   = 1 - r.get('pos_pct', 50) / 100   # 저점일수록 높게
            return score_norm * 0.6 + rr_norm * 0.3 + pos_norm * 0.1

        ranked = sorted(cands, key=composite, reverse=True)
        return ranked[:n]

    @staticmethod
    def reason(r: dict, regime: dict = None) -> str:
        """추천 이유 한 줄 요약"""
        parts = []
        if r.get('rsi') and r['rsi'] < 40:    parts.append(f"RSI {r['rsi']:.0f} 과매도")
        if r.get('pos_pct', 100) < 30:         parts.append(f"52주 저점권 {r['pos_pct']:.0f}%")
        if r.get('rr', 0) >= 2:                parts.append(f"R:R 1:{r['rr']}")
        if regime:                              parts.append(regime['label'])
        if not parts:                           parts.append(f"점수 {r.get('score', 0)}위")
        return ' · '.join(parts[:3])


# ═══════════════════════════════════════════════════════════════════
# 5. Alert Monitor — 조건 기반 알림
# ═══════════════════════════════════════════════════════════════════

class AlertMonitor:
    """
    관심종목 조건 감시.
    주식앱.py 에서 30초 주기로 호출 → 앱이 열려있는 동안 작동.
    """

    COND_BUY_ZONE       = 'buy_zone'
    COND_TARGET1        = 'target1'
    COND_TARGET2        = 'target2'
    COND_STOP_LOSS      = 'stop_loss'
    COND_RSI_OVERSOLD   = 'rsi_oversold'
    COND_RSI_OVERBOUGHT = 'rsi_overbought'

    @staticmethod
    def check(watchlist: list,
              get_price_fn,          # callable(code) -> dict|None
              cache: dict) -> list:  # session_state 기반 중복 방지
        """
        Args:
            watchlist    : [{'code': str, 'name': str}, ...]
            get_price_fn : 가격 조회 함수 (get_quick_price 등)
            cache        : 이미 발송된 알림 캐시 {'code:cond': timestamp}
        Returns:
            알림 리스트 [{code, name, cond, msg, level, emoji}, ...]
        """
        import time
        now    = time.time()
        alerts = []

        for item in watchlist:
            code = item['code']
            name = item['name']
            z    = item.get('z', {})   # 이미 계산된 zones 사전에서 참조

            pinfo = get_price_fn(code)
            if not pinfo or not z:
                continue

            price = pinfo['price']
            rsi   = z.get('rsi')

            def _add(cond: str, msg: str, level: str, emoji: str):
                key = f'{code}:{cond}'
                # 동일 알림 1시간 내 재발송 방지
                if now - cache.get(key, 0) < 3600:
                    return
                cache[key] = now
                alerts.append({'code': code, 'name': name,
                                'cond': cond, 'msg': msg,
                                'level': level, 'emoji': emoji})

            buy_l = z.get('buy_low', 0)
            buy_h = z.get('buy_high', float('inf'))
            stop  = z.get('stop', 0)
            tgt1  = z.get('tgt1', float('inf'))
            tgt2  = z.get('tgt2', float('inf'))

            if buy_l > 0 and buy_l <= price <= buy_h:
                _add(AlertMonitor.COND_BUY_ZONE,
                     f"{name} 매수 구간 진입 ({int(price):,}원)",
                     'info', '🎯')

            if tgt1 < float('inf') and price >= tgt1:
                _add(AlertMonitor.COND_TARGET1,
                     f"{name} 1차 목표가 도달! {int(price):,}원 ≥ {int(tgt1):,}원",
                     'success', '🏆')

            if tgt2 < float('inf') and price >= tgt2:
                _add(AlertMonitor.COND_TARGET2,
                     f"{name} 2차 목표가 도달! {int(price):,}원 ≥ {int(tgt2):,}원",
                     'success', '🎉')

            if stop > 0 and price <= stop:
                _add(AlertMonitor.COND_STOP_LOSS,
                     f"⚠️ {name} 손절가 이탈! {int(price):,}원 ≤ {int(stop):,}원",
                     'error', '🚨')

            if rsi is not None:
                if rsi < 28:
                    _add(AlertMonitor.COND_RSI_OVERSOLD,
                         f"{name} RSI {rsi:.0f} 극과매도 진입",
                         'info', '📉')
                elif rsi > 72:
                    _add(AlertMonitor.COND_RSI_OVERBOUGHT,
                         f"{name} RSI {rsi:.0f} 과매수 진입",
                         'warning', '📈')

        return alerts


# ═══════════════════════════════════════════════════════════════════
# 예제 실행
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    print('=' * 60)
    print('quant_engine.py — 예제 실행')
    print('=' * 60)

    # ── 1. 시장 상태 감지 ────────────────────────────────────────────
    print('\n[1] 시장 상태 감지 (KOSPI)')
    kospi = fdr.DataReader('KS11',
                            (datetime.today() - timedelta(days=400)).strftime('%Y-%m-%d'))
    kospi.columns = [c.capitalize() for c in kospi.columns]
    regime = MarketRegime.detect(kospi)
    print(f"  {regime['emoji']} {regime['label']}  강도 {regime['strength']}%")
    for k, v in regime['details'].items():
        print(f"     {k}: {v}")

    # ── 2. 개선된 신호 평가 ──────────────────────────────────────────
    print('\n[2] 신호 평가 — 삼성전자')
    df_ss = fdr.DataReader('005930',
                            (datetime.today() - timedelta(days=200)).strftime('%Y-%m-%d'))
    df_ss.columns = [c.capitalize() for c in df_ss.columns]
    df_ind = _calc_indicators_minimal(df_ss)

    last = float(df_ind['Close'].iloc[-1])
    bb_l = float(df_ind['BB_lower'].iloc[-1])
    bb_u = float(df_ind['BB_upper'].iloc[-1])
    ma20 = float(df_ind['MA20'].iloc[-1])
    ma60 = float(df_ind['MA60'].iloc[-1])
    rsi  = float(df_ind['RSI'].iloc[-1])
    w52h = float(df_ss['Close'].max())
    w52l = float(df_ss['Close'].min())

    pos_pct = (last - w52l) / (w52h - w52l) * 100 if w52h != w52l else 50
    buy_mid = (max(bb_l, w52l * 1.03) + min(ma20, last * 0.99)) / 2
    stop    = round(buy_mid * 0.93 / 100) * 100
    tgt1    = round(bb_u / 100) * 100

    z_sample = {
        'last': last, 'day_chg': 0.5, 'rsi': rsi,
        'pos_pct': pos_pct, 'buy_low': round(bb_l / 100) * 100,
        'buy_high': round(min(ma20, last) / 100) * 100,
        'buy_mid': round(buy_mid / 100) * 100,
        'stop': stop, 'tgt1': tgt1, 'tgt2': round(w52h * 0.97 / 100) * 100,
        'rr': 1.5, 'ma20': ma20, 'ma60': ma60, 'w52_high': w52h, 'w52_low': w52l,
    }

    sig = SignalEngine.evaluate(df_ind, z_sample, regime=regime)
    print(f"  {sig['emoji']} {sig['label']}  점수 {sig['score']}/100"
          f"  (원점수 {sig['raw_score']} + 시장보정 {sig['regime_adj']:+})")
    print(f"  {sig['desc']}")
    print(f"  근거:")
    for s, t in sig['reasons'][:5]:
        icon = '✅' if s == 'pos' else '⚠️' if s == 'neg' else 'ℹ️'
        print(f"    {icon} {t}")

    # ── 3. 백테스트 ──────────────────────────────────────────────────
    print('\n[3] Walk-Forward 백테스트 — 삼성전자 2년')
    df_bt = fdr.DataReader('005930',
                            (datetime.today() - timedelta(days=730)).strftime('%Y-%m-%d'))
    df_bt.columns = [c.capitalize() for c in df_bt.columns]

    result = Backtester.run(df_bt, initial_capital=10_000_000,
                            walk_forward=True, oos_ratio=0.3)
    s = result.summary()
    print(f"  검증기간  : {s['검증 기간']}")
    print(f"  총 수익률 : {s['총 수익률 (%)']:+.2f}%")
    print(f"  승률      : {s['승률 (%)']:.1f}%  ({s['거래 횟수']}건)")
    print(f"  MDD       : {s['MDD (%)']:.2f}%")
    print(f"  Sharpe    : {s['Sharpe Ratio']:.2f}")
    print(f"  PF        : {s['Profit Factor']}")
    print(f"  기댓값    : {s['기댓값 (%)']:+.2f}%")
    if result.trades:
        print('\n  최근 5건 거래:')
        print(result.trades_df().tail(5).to_string(index=False))

    # ── 4. TOP-5 추천 (스크리너 모의) ───────────────────────────────
    print('\n[4] TOP-5 추천 — 모의 스크리너 결과 기반')
    mock_results = [
        {'code': '005930', 'name': '삼성전자', 'sector': '반도체', 'tier': '상',
         'score': 72, 'rsi': 38, 'pos_pct': 22, 'rr': 2.1,
         'emoji': '🟢', 'label': '매수고려', 'price': 75000, 'day_chg': 1.2,
         'buy_mid': 72000, 'stop': 67000, 'tgt1': 85000},
        {'code': '000660', 'name': 'SK하이닉스', 'sector': '반도체', 'tier': '상',
         'score': 68, 'rsi': 42, 'pos_pct': 31, 'rr': 1.8,
         'emoji': '🟢', 'label': '매수고려', 'price': 180000, 'day_chg': 0.5,
         'buy_mid': 175000, 'stop': 163000, 'tgt1': 203000},
        {'code': '247540', 'name': '에코프로비엠', 'sector': '2차전지', 'tier': '중',
         'score': 65, 'rsi': 35, 'pos_pct': 18, 'rr': 2.5,
         'emoji': '🟢', 'label': '매수고려', 'price': 120000, 'day_chg': 2.1,
         'buy_mid': 115000, 'stop': 107000, 'tgt1': 140000},
    ]
    top5 = Recommender.get_top_n(mock_results, regime=regime, n=5, min_rr=1.5)
    for i, r in enumerate(top5, 1):
        print(f"  {i}위 {r['name']} ({r['code']})  점수:{r['score']}  "
              f"이유: {Recommender.reason(r, regime)}")

    print('\n✅ 예제 완료')
