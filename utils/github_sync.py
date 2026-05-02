"""
GitHub Contents API를 통한 파일 R/W.
watchlist.json / price_alerts.json / notify_settings.json 동기화에 사용.
"""
import json
import base64
import requests

_GH_OWNER       = "chein206"
_GH_REPO        = "stock-analyzer"
_GH_ALERTS_PATH = "data/price_alerts.json"
_GH_WL_PATH     = "data/watchlist.json"

_GH_HEADERS = {"Accept": "application/vnd.github.v3+json"}


def _auth_headers(pat: str) -> dict:
    return {"Authorization": f"token {pat}", **_GH_HEADERS}


def _gh_get_sha(path: str, pat: str) -> str:
    """파일 SHA 조회 (업데이트 PUT 요청에 필요)."""
    try:
        r = requests.get(
            f"https://api.github.com/repos/{_GH_OWNER}/{_GH_REPO}/contents/{path}",
            headers=_auth_headers(pat),
            timeout=5,
        )
        return r.json().get("sha", "") if r.status_code == 200 else ""
    except Exception:
        return ""


def _gh_put_file(path: str, pat: str, content_dict: dict) -> bool:
    """JSON dict를 GitHub 파일로 저장 (없으면 생성, 있으면 업데이트)."""
    try:
        payload_str = json.dumps(content_dict, ensure_ascii=False, indent=2)
        b64  = base64.b64encode(payload_str.encode("utf-8")).decode()
        sha  = _gh_get_sha(path, pat)
        body = {"message": f"update {path} [skip ci]", "content": b64}
        if sha:
            body["sha"] = sha
        r = requests.put(
            f"https://api.github.com/repos/{_GH_OWNER}/{_GH_REPO}/contents/{path}",
            headers=_auth_headers(pat),
            json=body,
            timeout=10,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False


def _gh_get_file(path: str, pat: str) -> dict | None:
    """GitHub 파일을 JSON dict로 로드."""
    try:
        r = requests.get(
            f"https://api.github.com/repos/{_GH_OWNER}/{_GH_REPO}/contents/{path}",
            headers=_auth_headers(pat),
            timeout=5,
        )
        if r.status_code == 200:
            content = base64.b64decode(r.json().get("content", "")).decode("utf-8")
            return json.loads(content)
    except Exception:
        pass
    return None
