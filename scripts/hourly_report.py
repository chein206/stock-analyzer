#!/usr/bin/env python3
"""
관심종목 정기 현재가 보고 스크립트
GitHub Actions에서 30분마다 실행 → 설정 파일 기준으로 발송 여부 판단.

필요한 GitHub Secrets:
  KAKAO_ACCESS_TOKEN  — 카카오 액세스 토큰
"""
import os
import json
import requests
from datetime import datetime

try:
    import pytz
    KST = pytz.timezone("Asia/Seoul")
    now_kst = datetime.now(KST)
except ImportError:
    from datetime import timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)

KAKAO_TOKEN      = os.environ.get("KAKAO_ACCESS_TOKEN", "")
WATCHLIST_FILE   = "data/watchlist.json"
NOTIFY_FILE      = "data/notify_settings.json"
LAST_SENT_FILE   = "data/last_report_sent.json"
APP_URL          = "https://stock-analyzer-egqwnt22pkfgzdgxuapppyw.streamlit.app"


def get_price(code: str) -> dict | None:
    try:
        import FinanceDataReader as fdr
        df = fdr.DataReader(code)
        if df is not None and not df.empty and len(df) >= 2:
            last = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2])
            chg  = (last / prev - 1) * 100
            return {"price": last, "chg": chg}
    except Exception as e:
        print(f"  FDR 실패({code}): {e}")
    try:
        import yfinance as yf
        for suffix in [".KS", ".KQ"]:
            hist = yf.Ticker(f"{code}{suffix}").history(period="5d")
            if hist is not None and not hist.empty and len(hist) >= 2:
                last = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2])
                chg  = (last / prev - 1) * 100
                return {"price": last, "chg": chg}
    except Exception as e:
        print(f"  yfinance 실패({code}): {e}")
    return None


def send_kakao(message: str) -> bool:
    if not KAKAO_TOKEN:
        print("  KAKAO_ACCESS_TOKEN 없음")
        return False
    template = {
        "object_type": "text",
        "text": message[:2000],
        "link": {"web_url": APP_URL, "mobile_web_url": APP_URL},
        "button_title": "앱에서 자세히 보기",
    }
    try:
        r = requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization": f"Bearer {KAKAO_TOKEN}"},
            data={"template_object": json.dumps(template, ensure_ascii=False)},
            timeout=10,
        )
        body = r.json()
        ok = r.status_code == 200 and body.get("result_code", -1) == 0
        print(f"  카카오톡 {'성공' if ok else '실패'}: {body}")
        return ok
    except Exception as e:
        print(f"  카카오톡 오류: {e}")
        return False


def should_send_now(settings: dict, last_sent: dict) -> bool:
    """현재 시각과 마지막 전송 시각 비교 → 발송 여부 판단"""
    if not settings.get("enabled", False):
        return False

    h = now_kst.hour
    start = settings.get("start_hour", 8)
    end   = settings.get("end_hour",   20)
    if not (start <= h < end):
        return False

    # 주말 제외
    if now_kst.weekday() >= 5:
        return False

    interval_hours = settings.get("interval_hours", 1)
    interval_min   = int(interval_hours * 60)

    last_ts = last_sent.get("sent_at")
    if not last_ts:
        return True  # 한 번도 안 보냈으면 보내기

    try:
        # last_ts 파싱
        from datetime import datetime as dt
        try:
            last_dt = dt.fromisoformat(last_ts)
        except Exception:
            return True

        diff_min = (now_kst.replace(tzinfo=None) - last_dt.replace(tzinfo=None)).total_seconds() / 60
        return diff_min >= interval_min
    except Exception:
        return True


def main():
    print(f"\n{'='*50}")
    print(f"[{now_kst.strftime('%Y-%m-%d %H:%M:%S')} KST] 정기 보고 체크")
    print(f"{'='*50}")

    # 설정 로드
    if not os.path.exists(NOTIFY_FILE):
        print("설정 파일 없음 — 건너뜀")
        return
    with open(NOTIFY_FILE, encoding="utf-8") as f:
        settings = json.load(f)

    # 마지막 전송 시각 로드
    last_sent = {}
    if os.path.exists(LAST_SENT_FILE):
        with open(LAST_SENT_FILE, encoding="utf-8") as f:
            last_sent = json.load(f)

    if not should_send_now(settings, last_sent):
        print(f"발송 조건 미충족 (enabled={settings.get('enabled')}, "
              f"interval={settings.get('interval_hours')}h, "
              f"last_sent={last_sent.get('sent_at', '없음')})")
        return

    # 관심종목 로드
    if not os.path.exists(WATCHLIST_FILE):
        print("관심종목 파일 없음")
        return
    with open(WATCHLIST_FILE, encoding="utf-8") as f:
        wl_data = json.load(f)
    watchlist = wl_data.get("watchlist", [])
    if not watchlist:
        print("관심종목 없음")
        return

    print(f"관심종목 {len(watchlist)}개 가격 조회 중...")

    lines = [f"📊 관심종목 현재가 [{now_kst.strftime('%m/%d %H:%M')} KST]\n"]
    for item in watchlist:
        code = item.get("code", "")
        name = item.get("name", code)
        info = get_price(code)
        if info:
            price = info["price"]
            chg   = info["chg"]
            arrow = "▲" if chg >= 0 else "▼"
            color = "+" if chg >= 0 else ""
            lines.append(f"{arrow} {name}  {int(price):,}원  ({color}{chg:.2f}%)")
        else:
            lines.append(f"• {name}  조회 실패")

    lines.append(f"\n🔗 자세히 보기\n{APP_URL}")
    message = "\n".join(lines)
    print(message)

    if send_kakao(message):
        # 전송 시각 저장
        last_sent = {"sent_at": now_kst.strftime("%Y-%m-%dT%H:%M:%S")}
        with open(LAST_SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(last_sent, f, ensure_ascii=False, indent=2)
        print("✅ 전송 완료, 시각 저장됨")


if __name__ == "__main__":
    main()
