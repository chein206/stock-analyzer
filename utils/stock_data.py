"""
KRX 종목 로드·검색 및 주가/뉴스/수급/실적 데이터 수집.
"""
import json
import os
import time
import warnings

import pandas as pd
import requests
import streamlit as st

warnings.filterwarnings('ignore')

from utils.kis_api import kis_get_token, kis_price, KIS_APP_KEY, KIS_APP_SECRET, _KIS_REAL

# ── 오프라인 fallback 종목명 사전 ─────────────────────────────────────────────
KNOWN_NAMES = {
    '005930': '삼성전자',        '000660': 'SK하이닉스',
    '035420': 'NAVER',           '035720': '카카오',
    '005380': '현대차',          '000270': '기아',
    '051910': 'LG화학',          '006400': '삼성SDI',
    '207940': '삼성바이오로직스','068270': '셀트리온',
    '028260': '삼성물산',        '105560': 'KB금융',
    '055550': '신한지주',        '086790': '하나금융지주',
    '003550': 'LG',              '066570': 'LG전자',
    '096770': 'SK이노베이션',    '017670': 'SK텔레콤',
    '030200': 'KT',              '032830': '삼성생명',
    '373220': 'LG에너지솔루션',  '247540': '에코프로비엠',
    '086520': '에코프로',        '011200': 'HMM',
    '010140': '삼성중공업',      '042660': '한화오션',
    '329180': 'HD현대중공업',    '012330': '현대모비스',
    '000810': '삼성화재',        '090430': '아모레퍼시픽',
    '034730': 'SK',              '005490': 'POSCO홀딩스',
    '003490': '대한항공',        '000100': '유한양행',
    '128940': '한미약품',        '196170': '알테오젠',
    '145020': '휴젤',            '015760': '한국전력',
    '042700': '한미반도체',      '357780': '솔브레인',
    '240810': '원익IPS',         '058470': '리노공업',
    '278280': '천보',            '064760': '티씨케이',
    '326030': 'SK바이오팜',      '302440': 'SK바이오사이언스',
    '185750': '종근당',          '011210': '현대위아',
    '012450': '한화에어로스페이스','047810': '한국항공우주',
    '064350': '현대로템',        '272210': '한화시스템',
    '259960': '크래프톤',        '036570': 'NC소프트',
    '251270': '넷마블',          '263750': '펄어비스',
    '293490': '카카오게임즈',    '041510': 'SM엔터테인먼트',
    '035900': 'JYP Ent.',        '122870': 'YG엔터테인먼트',
    '352820': '하이브',          '316140': '우리금융지주',
    '138930': 'BNK금융지주',     '175330': 'JB금융지주',
    '024110': '기업은행',        '005940': 'NH투자증권',
    '006800': '미래에셋증권',    '039490': '키움증권',
    '071050': '한국금융지주',    '034220': 'LG디스플레이',
    '009150': '삼성전기',        '000990': 'DB하이텍',
    '004020': '현대제철',        '010060': 'OCI',
    '002380': 'KCC',             '032640': 'LG유플러스',
    '139480': '이마트',          '004170': '신세계',
    '000720': '현대건설',        '028050': '삼성엔지니어링',
    '006360': 'GS건설',          '047040': '대우건설',
    '271560': '오리온',          '097950': 'CJ제일제당',
    '003230': '삼양식품',        '007070': 'GS리테일',
    '078930': 'GS',              '010950': 'S-Oil',
    '020560': '아시아나항공',    '000150': '두산',
    '004000': '롯데케미칼',      '011070': 'LG이노텍',
    '036460': '한국가스공사',    '009540': 'HD한국조선해양',
}


# ── KRX 전체 종목 로드 ────────────────────────────────────────────────────────
def load_krx_stocks():
    """FDR → pykrx → 번들 JSON → KNOWN_NAMES 순 fallback 로드."""
    cache = st.session_state.get('_krx_cache', {})
    now   = time.time()
    if cache:
        data = cache.get('data')
        ttl  = 86400 if (data is not None and len(data) > 500) else 300
        if now - cache.get('ts', 0) < ttl:
            return data

    def _normalize(df):
        col_map = {}
        for c in df.columns:
            cl = (c.lower().strip()
                  .replace(' ', '').replace('_', '').replace('-', ''))
            if cl in ('code', 'symbol', '종목코드', '단축코드', 'ticker', 'shortcode'):
                col_map[c] = 'Code'
            elif cl in ('name', '종목명', '회사명', 'corpname', 'shortname', '기업명'):
                col_map[c] = 'Name'
        df = df.rename(columns=col_map)
        if 'Code' not in df.columns or 'Name' not in df.columns:
            return None
        df = df[['Code', 'Name']].copy()
        df['Code'] = df['Code'].astype(str).str.extract(r'(\d{6})')[0]
        df = df.dropna(subset=['Code'])
        return df.drop_duplicates('Code').reset_index(drop=True)

    def _cache_and_return(df):
        st.session_state['_krx_cache'] = {'data': df, 'ts': now}
        return df

    # 1순위: FDR KRX 전체
    try:
        import FinanceDataReader as fdr
        result = _normalize(fdr.StockListing('KRX'))
        if result is not None and len(result) > 200:
            return _cache_and_return(result)
    except Exception:
        pass

    # 2순위: FDR KOSPI + KOSDAQ
    try:
        import FinanceDataReader as fdr
        parts = []
        for market in ('KOSPI', 'KOSDAQ'):
            try:
                r = _normalize(fdr.StockListing(market))
                if r is not None and not r.empty:
                    parts.append(r)
            except Exception:
                pass
        if parts:
            combined = pd.concat(parts, ignore_index=True).drop_duplicates('Code')
            if len(combined) > 200:
                return _cache_and_return(combined.reset_index(drop=True))
    except Exception:
        pass

    # 3순위: pykrx
    try:
        from pykrx import stock as pstock
        from datetime import datetime, timedelta
        tickers = []
        for back in range(5):
            d = (datetime.today() - timedelta(days=back)).strftime('%Y%m%d')
            try:
                t = (pstock.get_market_ticker_list(d, market='KOSPI') +
                     pstock.get_market_ticker_list(d, market='KOSDAQ'))
                if t:
                    tickers = t
                    break
            except Exception:
                pass
        if tickers:
            rows = []
            for t in tickers:
                try:
                    rows.append({'Code': t.zfill(6),
                                 'Name': pstock.get_market_ticker_name(t)})
                except Exception:
                    pass
            if len(rows) > 200:
                return _cache_and_return(
                    pd.DataFrame(rows).drop_duplicates('Code').reset_index(drop=True))
    except Exception:
        pass

    # 4순위: 번들 JSON (data/krx_stocks.json)
    try:
        bundle = os.path.join(os.path.dirname(__file__), '..', 'data', 'krx_stocks.json')
        if os.path.exists(bundle):
            with open(bundle, encoding='utf-8') as f:
                rows = json.load(f)
            result = pd.DataFrame(rows)
            result['Code'] = result['Code'].astype(str).str.zfill(6)
            result = result[['Code', 'Name']].drop_duplicates('Code').reset_index(drop=True)
            if len(result) > 200:
                return _cache_and_return(result)
    except Exception:
        pass

    # 최종 fallback
    result = pd.DataFrame(list(KNOWN_NAMES.items()), columns=['Code', 'Name'])
    st.session_state['_krx_cache'] = {'data': result, 'ts': now}
    return result


def _naver_search(query: str) -> pd.DataFrame:
    """네이버 금융 자동완성 API로 종목 검색."""
    try:
        url = (f"https://ac.finance.naver.com/ac"
               f"?q={requests.utils.quote(query)}&q_enc=UTF-8&target=stock")
        r = requests.get(url, timeout=5,
                         headers={"User-Agent": "Mozilla/5.0",
                                  "Referer": "https://finance.naver.com"})
        if r.status_code != 200:
            return pd.DataFrame(columns=['Code', 'Name'])
        data  = r.json()
        items = data.get("items", []) or data.get("result", {}).get("items", [])
        rows  = []
        for item in items[:12]:
            if isinstance(item, list) and len(item) >= 2:
                rows.append({'Code': str(item[0]).zfill(6), 'Name': str(item[1])})
            elif isinstance(item, dict):
                code = str(item.get('code', item.get('cd', ''))).zfill(6)
                name = str(item.get('name', item.get('nm', '')))
                if code and name:
                    rows.append({'Code': code, 'Name': name})
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['Code', 'Name'])
    except Exception:
        return pd.DataFrame(columns=['Code', 'Name'])


def search_stocks(krx, query):
    q = query.strip()
    if not q:
        return pd.DataFrame(columns=['Code', 'Name'])
    mask    = (krx['Name'].str.contains(q, na=False, case=False, regex=False) |
               krx['Code'].str.contains(q, na=False, regex=False))
    results = krx[mask].head(12)
    if results.empty or len(krx) < 500:
        naver = _naver_search(q)
        if not naver.empty:
            results = (naver if results.empty
                       else pd.concat([results, naver]).drop_duplicates('Code').head(12))
    return results


# ── 주가 데이터 수집 ──────────────────────────────────────────────────────────
@st.cache_data(ttl=900)
def get_stock_data(code, months):
    from datetime import datetime, timedelta
    import FinanceDataReader as fdr
    import yfinance as yf

    end = datetime.today()
    start = end - timedelta(days=months * 31)
    s, e  = start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')

    try:
        df = fdr.DataReader(code, s, e)
        if not df.empty and len(df) > 10:
            df.index   = pd.to_datetime(df.index)
            df.columns = [c.capitalize() for c in df.columns]
            if 'Volume' not in df.columns:
                df['Volume'] = 0
            return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except Exception:
        pass

    for suffix in ['.KS', '.KQ']:
        try:
            df = yf.Ticker(f'{code}{suffix}').history(start=s, end=e)
            if not df.empty and len(df) > 10:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        except Exception:
            pass
    return pd.DataFrame()


@st.cache_data(ttl=900)
def get_stock_info(code):
    import yfinance as yf
    for suffix in ['.KS', '.KQ']:
        try:
            raw = yf.Ticker(f'{code}{suffix}').info
            if raw and raw.get('regularMarketPrice'):
                return {
                    'per':            raw.get('trailingPE'),
                    'pbr':            raw.get('priceToBook'),
                    'roe':            raw.get('returnOnEquity'),
                    'market_cap':     raw.get('marketCap'),
                    'dividend':       raw.get('dividendYield'),
                    'sector':         raw.get('sector', '-'),
                    '52w_high':       raw.get('fiftyTwoWeekHigh'),
                    '52w_low':        raw.get('fiftyTwoWeekLow'),
                    'eps':            raw.get('trailingEps'),
                    'dividend_rate':  raw.get('dividendRate'),
                    'ex_dividend_date': raw.get('exDividendDate'),
                }
        except Exception:
            pass
    return {}


@st.cache_data(ttl=600)
def get_stock_news(name: str) -> list:
    """Google News RSS로 종목 관련 뉴스 5건 반환."""
    import urllib.parse
    import xml.etree.ElementTree as ET
    try:
        rss_url = (f"https://news.google.com/rss/search?"
                   f"q={urllib.parse.quote(name)}&hl=ko&gl=KR&ceid=KR:ko")
        r = requests.get(rss_url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        root  = ET.fromstring(r.content)
        items = root.findall('.//item')[:5]
        news  = []
        for it in items:
            title = (it.findtext('title') or '').strip()
            link  = (it.findtext('link')  or '').strip()
            pub   = (it.findtext('pubDate') or '').strip()
            desc  = (it.findtext('description') or '').strip()
            try:
                from email.utils import parsedate_to_datetime
                pub_fmt = parsedate_to_datetime(pub).strftime('%m/%d %H:%M')
            except Exception:
                pub_fmt = pub[:16]
            news.append({'title': title, 'link': link, 'pub': pub_fmt, 'desc': desc})
        return news
    except Exception:
        return []


@st.cache_data(ttl=3600)
def get_investor_flow(code, days=20):
    """기관/외국인 수급 — pykrx 우선, KIS fallback."""
    from datetime import datetime, timedelta

    try:
        from pykrx import stock as pstock
        end   = datetime.today()
        start = end - timedelta(days=days * 3)
        df = pstock.get_market_trading_value_by_date(
            start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), code)
        if df is not None and not df.empty:
            df = df[df.abs().sum(axis=1) > 0]
            if len(df) >= 2:
                return df.tail(days)
    except Exception:
        pass

    try:
        token = kis_get_token()
        if not token:
            return None
        base = st.session_state.get('_kis_base_url', _KIS_REAL)
        r = requests.get(
            f"{base}/uapi/domestic-stock/v1/quotations/inquire-investor",
            headers={
                "Authorization": f"Bearer {token}",
                "appkey":       KIS_APP_KEY,
                "appsecret":    KIS_APP_SECRET,
                "tr_id":        "FHKST01010900",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
            timeout=10,
        )
        if r.status_code == 200:
            out = r.json().get('output', [])
            if out:
                rows = []
                for item in out[:days]:
                    try:
                        date = pd.to_datetime(item.get('stck_bsop_date', ''), format='%Y%m%d')
                        rows.append({
                            'date':    date,
                            '외국인':  float(item.get('frgn_ntby_qty', 0)) * 1000,
                            '기관합계': float(item.get('orgn_ntby_qty', 0)) * 1000,
                            '개인':    float(item.get('indv_ntby_qty', 0)) * 1000,
                        })
                    except Exception:
                        pass
                if rows:
                    return pd.DataFrame(rows).set_index('date').sort_index()
    except Exception:
        pass
    return None


@st.cache_data(ttl=86400)
def get_quarterly_earnings(code):
    import yfinance as yf
    for suffix in ['.KS', '.KQ']:
        try:
            fin = yf.Ticker(f'{code}{suffix}').quarterly_financials
            if fin is not None and not fin.empty and len(fin.columns) >= 2:
                return fin
        except Exception:
            pass
    return None


@st.cache_data(ttl=900)
def get_kospi_regime() -> dict | None:
    """KOSPI 시장 상태 감지 (quant_engine 필요)."""
    from utils.shared import shared
    if not shared.QE:
        return None
    try:
        import FinanceDataReader as fdr
        from datetime import datetime, timedelta
        end   = datetime.today()
        start = end - timedelta(days=420)
        df = fdr.DataReader('KS11', start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
        if df is None or df.empty or len(df) < 60:
            return None
        df.columns = [c.capitalize() for c in df.columns]
        return shared.MarketRegime.detect(df)
    except Exception:
        return None
