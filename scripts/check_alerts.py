#!/usr/bin/env python3
"""
주가 알림 체크 스크립트
GitHub Actions에서 평일 장중(9:00~15:30 KST) 15분마다 실행.

필요한 GitHub Secrets:
  KAKAO_ACCESS_TOKEN  — 카카오 액세스 토큰 (나에게 보내기)
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

KAKAO_TOKEN = os.environ.get("KAKAO_ACCESS_TOKEN", "")
ALERTS_FILE = "data/price_alerts.json"
APP_URL     = "https://stock-analyzer-egqwnt22pkfgzdgxuapppyw.streamlit.app"


# ── 거래 시간 확인 ──────────────────────────────────────────────────────────────
def is_trading_hours() -> bool:
    if now_kst.weekday() >= 5:          # 토·일
        return False
    h, m = now_kst.hour, now_kst.minute
    return (9, 0) <= (h, m) <= (15, 35)


# ── 현재가 조회 ─────────────────────────────────────────────────────────────────
def get_price(code: str) -> float | None:
    # 1) FinanceDataReader
    try:
        import FinanceDataReader as fdr
        df = fdr.DataReader(code)
        if df is not None and not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception as e:
        print(f"    FDR 실패({code}): {e}")

    # 2) yfinance fallback
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{code}.KS")
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"    yfinance 실패({code}): {e}")

    return None


# ── 카카오톡 전송 ───────────────────────────────────────────────────────────────
def send_kakao(message: str) -> bool:
    if not KAKAO_TOKEN:
        print("  ⚠️  KAKAO_ACCESS_TOKEN 없음 — 카톡 전송 건너뜀")
        return False

    template = {
        "object_type": "text",
        "text": message[:2000],
        "link": {
            "web_url":        APP_URL,
            "mobile_web_url": APP_URL,
        },
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
        if r.status_code == 200 and body.get("result_code", -1) == 0:
            print("  ✅ 카카오톡 전송 성공")
            return True
        else:
            print(f"  ❌ 카카오톡 전송 실패: {body}")
            return False
    except Exception as e:
        print(f"  ❌ 카카오톡 전송 오류: {e}")
        return False


# ── 메인 ───────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"[{now_kst.strftime('%Y-%m-%d %H:%M:%S')} KST] 주가 알림 체크 시작")
    print(f"{'='*50}")

    if not is_trading_hours():
        print("⏸  장외 시간 — 체크 건너뜀")
        return

    if not os.path.exists(ALERTS_FILE):
        print(f"⚠️  알림 파일 없음: {ALERTS_FILE}")
        return

    with open(ALERTS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    alerts = data.get("alerts", {})
    if not alerts:
        print("📭 설정된 알림 없음")
        return

    print(f"📋 알림 종목: {len(alerts)}개")
    changed = False
    today_str = now_kst.strftime("%Y%m%d")

    for code, cfg in alerts.items():
        if not cfg.get("enabled", True):
            continue

        target = cfg.get("target")
        stop   = cfg.get("stop")
        if not target and not stop:
            continue

        name = cfg.get("name", code)
        print(f"\n  [{name} {code}] 가격 조회 중...")
        price = get_price(code)
        if price is None:
            print(f"  ⚠️  가격 조회 실패 — 건너뜀")
            continue

        tgt_str  = f"{int(target):,}원" if target else "-"
        stop_str = f"{int(stop):,}원"   if stop   else "-"
        print(f"  현재가: {price:,.0f}원  |  목표: {tgt_str}  |  손절: {stop_str}")

        last_triggered = cfg.get("last_triggered", "")

        # 목표가 도달
        if target and price >= target:
            key = f"target_{int(target)}_{today_str}"
            if last_triggered != key:
                msg = (
                    f"🎯 [{name}] 목표가 도달!\n"
                    f"현재가 {price:,.0f}원 ≥ 목표가 {int(target):,}원\n"
                    f"⏰ {now_kst.strftime('%m/%d %H:%M')} KST\n"
                    f"앱 바로가기 → {APP_URL}"
                )
                print(f"  🎯 목표가 알림 발송")
                send_kakao(msg)
                cfg["last_triggered"] = key
                changed = True

        # 손절가 도달
        elif stop and price <= stop:
            key = f"stop_{int(stop)}_{today_str}"
            if last_triggered != key:
                msg = (
                    f"🚨 [{name}] 손절가 도달!\n"
                    f"현재가 {price:,.0f}원 ≤ 손절가 {int(stop):,}원\n"
                    f"⏰ {now_kst.strftime('%m/%d %H:%M')} KST\n"
                    f"앱 바로가기 → {APP_URL}"
                )
                print(f"  🚨 손절가 알림 발송")
                send_kakao(msg)
                cfg["last_triggered"] = key
                changed = True

        # 두 경계 사이로 회복 → 트리거 리셋
        elif target and stop and stop < price < target and last_triggered:
            cfg["last_triggered"] = ""
            changed = True
            print(f"  🔄 가격 회복 — 알림 리셋")

    # 상태 파일 업데이트
    if changed:
        data["alerts"]       = alerts
        data["last_checked"] = now_kst.isoformat()
        with open(ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n💾 알림 상태 파일 업데이트 완료")
    else:
        print(f"\n✅ 조건 충족 종목 없음 — 변경 없음")

    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
